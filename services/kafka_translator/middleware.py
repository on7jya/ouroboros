"""Middleware — authentication, logging, error handling."""

from fastapi import Request, FastAPI, HTTPException
from fastapi.responses import JSONResponse
import time
import hashlib


def setup_basic_auth(app: FastAPI, username: str, password_hash: str):
    """Register basic auth middleware on app."""

    async def basic_auth_middleware(request: Request, call_next):
        # Skip auth for health checks and metrics
        if request.url.path in ["/", "/status", "/health", "/ready", "/live", "/metrics"]:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Authorization header missing")

        if not auth_header.startswith("Basic "):
            raise HTTPException(status_code=401, detail="Invalid auth scheme")

        # Decode Basic Auth
        import base64
        try:
            encoded = auth_header[6:]
            decoded = base64.b64decode(encoded).decode("utf-8")
        except Exception:
            raise HTTPException(status_code=401, detail="Malformed Basic Auth header")

        parts = decoded.split(":", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=401, detail="Bad credentials format")

        user, pwd = parts
        if user != username:
            raise HTTPException(status_code=401, detail="Invalid username")

        pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
        if pwd_hash != password_hash:
            raise HTTPException(status_code=401, detail="Invalid password")

        return await call_next(request)

    app.add_middleware(basic_auth_middleware)


async def request_timing_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    # Log in JSON for structured logging compatibility
    import json
    log_entry = {
        "event": "request_complete",
        "method": request.method,
        "path": str(request.url.path),
        "status_code": response.status_code,
        "duration_ms": round(duration_ms, 2),
    }
    print(json.dumps(log_entry))
    return response


def setup_timing_middleware(app: FastAPI):
    """Register timing middleware on app."""
    app.add_middleware(request_timing_middleware)