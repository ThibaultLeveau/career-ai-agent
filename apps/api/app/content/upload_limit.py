from starlette.responses import JSONResponse

MAX_UPLOAD_REQUEST = 11 * 1024 * 1024


class UploadLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        chat = scope["type"] == "http" and (
            scope["path"] == "/chat" or scope["path"].startswith("/chat/")
        )
        if (
            scope["type"] != "http"
            or (not chat and not scope["path"].startswith("/admin/documents"))
            or scope["method"] not in {"POST", "PUT"}
        ):
            return await self.app(scope, receive, send)
        # Bound bodies before parsing, including requests without Content-Length.
        limit = 65536 if chat else MAX_UPLOAD_REQUEST
        if chat and scope["path"] == "/chat/components/page":
            limit = 256 * 1024
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > limit:
                response = JSONResponse(
                    {
                        "detail": "Chat request is too large"
                        if chat
                        else "Upload is too large (maximum PDF size: 10 MiB)"
                    },
                    status_code=413,
                    headers={"Cache-Control": "no-store"},
                )
                return await response(scope, receive, send)
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, bounded_receive, send)
