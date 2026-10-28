from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class IngestCorsMiddleware:
    """Browser support for the ingest routes only (everything under `path_prefix`).

    Customer websites run on their own domains, so browsers must be allowed to call ingest from
    any origin. Which websites may actually send data is checked per project
    (projects.allowed_origins) by the ingest service, not here. The rest of the API keeps the
    normal, stricter CORS settings from main.py.

    It also:
    - answers the browser's preflight (OPTIONS) request itself;
    - accepts `Content-Type: text/plain` bodies (sendBeacon sends those when a tab closes) by
      treating them as JSON;
    - rejects bodies over `max_body_bytes` before they are read.
    """

    CORS_HEADERS = {
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-API-Key",
        "Access-Control-Max-Age": "86400",  # browsers may cache the preflight for a day
        "Vary": "Origin",
    }

    def __init__(self, app: ASGIApp, path_prefix: str, max_body_bytes: int = 1_000_000) -> None:
        self.app = app
        self.path_prefix = path_prefix
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        cors = self._cors_headers(headers.get("origin"))

        if scope["method"] == "OPTIONS":
            await Response(status_code=204, headers=cors)(scope, receive, send)
            return

        if int(headers.get("content-length") or 0) > self.max_body_bytes:
            body = {"status": 413, "error": f"Request body is larger than {self.max_body_bytes} bytes"}
            await JSONResponse(body, status_code=413, headers=cors)(scope, receive, send)
            return

        if headers.get("content-type", "").startswith("text/plain"):
            scope = self._as_json(scope)

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in cors.items():
                    response_headers[name] = value
                # Ingest never uses cookies; drop the flag the main CORS middleware may add.
                if "access-control-allow-credentials" in response_headers:
                    del response_headers["access-control-allow-credentials"]
            await send(message)

        await self.app(scope, receive, send_with_cors)

    def _cors_headers(self, origin: str | None) -> dict[str, str]:
        # Echo the caller's origin (rather than "*") so it also works for sendBeacon, which
        # sends cookies; we never read them.
        return {"Access-Control-Allow-Origin": origin or "*", **self.CORS_HEADERS}

    @staticmethod
    def _as_json(scope: Scope) -> Scope:
        raw = [(k, v) for k, v in scope["headers"] if k != b"content-type"]
        return {**scope, "headers": [*raw, (b"content-type", b"application/json")]}
