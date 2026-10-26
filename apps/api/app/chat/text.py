from app.chat.schemas import ChatRequest
from app.ingestion.text import tokenizer

QUERY_TOKENS = 2000
CONTEXT_TOKENS = 12000
HISTORY_TOKENS = 6000


def tokens(text: str) -> list[int]:
    return tokenizer().encode(text, disallowed_special=())


def truncate(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    return tokenizer().decode(tokens(text)[:limit], errors="ignore")


def retrieval_query(data: ChatRequest) -> str:
    question = truncate(data.message, 1500 if data.history else QUERY_TOKENS)
    if not data.history:
        return question
    previous = data.history[-2:]
    context = (
        f"user: {truncate(previous[0].content, 150)}\n"
        f"assistant: {truncate(previous[1].content, 300)}"
    )
    return truncate(
        f"Question: {question}\nPrevious exchange: {context}",
        QUERY_TOKENS,
    )


def bounded_history(data: ChatRequest) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    remaining = HISTORY_TOKENS
    for start in range(len(data.history) - 2, -1, -2):
        pair = data.history[start : start + 2]
        size = sum(len(tokens(item.content)) for item in pair)
        if size > remaining:
            if not result:
                result = [
                    {
                        "role": item.role,
                        "content": truncate(item.content, remaining // 2),
                    }
                    for item in pair
                ]
            break
        result[0:0] = [item.model_dump() for item in pair]
        remaining -= size
    return result
