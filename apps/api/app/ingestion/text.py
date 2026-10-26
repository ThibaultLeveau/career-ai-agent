from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

import tiktoken
from pypdf import PdfReader


class IngestionError(Exception):
    def __init__(self, message: str, retryable: bool = False, delay: float = 0):
        super().__init__(message)
        self.retryable = retryable
        self.delay = delay


@lru_cache
def tokenizer():
    return tiktoken.get_encoding("cl100k_base")


def normalize(text: str) -> str:
    return "\n".join(
        line.rstrip() for line in text.replace("\x00", "").splitlines()
    ).strip()


def extract_pdf(content: bytes) -> list[tuple[int, str]]:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise IngestionError("This PDF is encrypted. Upload an unencrypted PDF.")
        if len(reader.pages) > 500:
            raise IngestionError("This PDF exceeds the 500-page extraction limit.")
        pages = []
        for number, page in enumerate(reader.pages, 1):
            stream = page.get_contents()
            if stream and len(stream.get_data()) > 20 * 1024 * 1024:
                raise IngestionError("A PDF page is too complex. Upload a smaller PDF.")
            pages.append((number, normalize(page.extract_text() or "")))
        if not any(text for _, text in pages):
            raise IngestionError(
                "No selectable text was found. "
                "Upload a text PDF; scanned PDFs need OCR."
            )
        return pages
    except IngestionError:
        raise
    except Exception:
        raise IngestionError(
            "Could not read this PDF. Replace it with a valid text PDF."
        ) from None


@dataclass
class TextChunk:
    text: str
    token_count: int
    page_start: int | None
    page_end: int | None


def chunk_text(pages: list[tuple[int | None, str]], size: int, overlap: int):
    if not 0 <= overlap < size:
        raise ValueError("Overlap must be smaller than chunk size")
    encoding = tokenizer()
    text = ""
    spans = []
    for page, value in pages:
        if not value:
            continue
        start = len(text.encode())
        text += value + "\n\n"
        spans.append((start, len(text.encode()), page))
    text = text.rstrip()
    if not text:
        raise IngestionError("No text is available to embed.")
    tokens = encoding.encode(text, disallowed_special=())
    raw = text.encode()
    offsets = [0]
    for token in tokens:
        offsets.append(offsets[-1] + len(encoding.decode_single_token_bytes(token)))

    def boundary(index):
        return index == len(tokens) or raw[offsets[index]] & 0xC0 != 0x80

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + size, len(tokens))
        while end > start and not boundary(end):
            end -= 1
        value = raw[offsets[start] : offsets[end]].decode()
        count = len(encoding.encode(value, disallowed_special=()))
        # Re-tokenizing a substring can change tokens at its boundaries.
        while count > size and end > start:
            end -= 1
            while end > start and not boundary(end):
                end -= 1
            value = raw[offsets[start] : offsets[end]].decode()
            count = len(encoding.encode(value, disallowed_special=()))
        if end <= start:
            raise IngestionError(
                "Chunk size cannot represent a character in this text."
            )
        refs = [p for a, b, p in spans if a < offsets[end] and b > offsets[start] and p]
        if value.strip():
            chunks.append(
                TextChunk(
                    value,
                    count,
                    min(refs) if refs else None,
                    max(refs) if refs else None,
                )
            )
        if end == len(tokens):
            break
        next_start = max(start + 1, end - overlap)
        while next_start < end and not boundary(next_start):
            next_start += 1
        start = next_start
    return text, chunks
