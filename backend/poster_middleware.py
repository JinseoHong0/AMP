"""Limit the multipart body BEFORE Starlette spools files to disk."""

import ipaddress

from starlette.requests import Request

from backend.config import Settings
from backend.errors import error_response
from backend.services.poster_uploads import MAX_FILE_BYTES


class PosterRequestGuard:
    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["path"].rstrip("/") != "/api/posters/parse"
            or scope["method"] != "POST"
        ):
            return await self.app(scope, receive, send)
        request = Request(scope)
        try:
            local = (
                ipaddress.ip_address(request.client.host).is_loopback if request.client else False
            )
        except ValueError:
            local = False
        # No public admin authentication is implemented in this slice. Fail closed.
        origin = request.headers.get("origin")
        if (
            not self.settings.local_demo
            or not local
            or request.url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or (origin is not None and origin not in self.settings.allowed_origins)
        ):
            response = error_response(
                403, "FORBIDDEN", "포스터 추출은 로컬 데모에서만 사용할 수 있습니다."
            )
            return await response(scope, receive, send)
        max_body = (
            MAX_FILE_BYTES + 64 * 1024
        )  # Bounded multipart envelope, plus exact file check later.
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            response = error_response(400, "INVALID_QUERY", "잘못된 요청 길이입니다.")
            return await response(scope, receive, send)
        if length > max_body:
            response = error_response(
                413, "FILE_TOO_LARGE", "포스터는 최대 5MB까지 업로드할 수 있습니다."
            )
            return await response(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > max_body:
                response = error_response(
                    413, "FILE_TOO_LARGE", "포스터는 최대 5MB까지 업로드할 수 있습니다."
                )
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def limited_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, limited_receive, send)
