"""Bound PDF parsing separately from the durable worker process."""

import json
import subprocess
import sys

from app.ingestion.text import IngestionError, extract_pdf


def extract(content: bytes):
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.ingestion.pdf"],
            input=content,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise ValueError
        data = json.loads(result.stdout)
        if "error" in data:
            raise IngestionError(data["error"])
        return data["pages"]
    except subprocess.TimeoutExpired, ValueError, KeyError:
        raise IngestionError(
            "PDF extraction exceeded its resource limits. Upload a simpler text PDF."
        ) from None


if __name__ == "__main__":
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    try:
        print(json.dumps({"pages": extract_pdf(sys.stdin.buffer.read())}))
    except IngestionError as error:
        print(json.dumps({"error": str(error)}))
