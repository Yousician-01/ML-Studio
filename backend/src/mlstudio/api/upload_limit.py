"""Bound request bytes before multipart parsing can spool an unlimited upload."""

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse


class UploadLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH"}:
            return await self.app(scope, receive, send)
        received = 0
        exceeded = False

        async def limited_receive():
            nonlocal received, exceeded
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                exceeded = True
                # Starlette closes partially spooled files for this exception.
                raise MultiPartException("Upload request exceeds the configured size limit.")
            return message

        async def limited_send(message):
            if not exceeded:
                await send(message)

        await self.app(scope, limited_receive, limited_send)
        if exceeded:
            await JSONResponse(
                {"detail": "Upload request exceeds the configured size limit."}, status_code=413
            )(scope, receive, send)
