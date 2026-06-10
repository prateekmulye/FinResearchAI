"""Client identity for rate limiting and demo quotas — ONE shared implementation.

Moved out of ``src/api/main.py`` (WP-5) so the per-minute limiter and the daily
demo guard key on exactly the same notion of "client IP".
"""
from __future__ import annotations

import os

from fastapi import Request


def trust_proxy() -> bool:
    return os.getenv("TRUST_PROXY", "").lower() in {"1", "true", "yes"}


def client_key(request: Request) -> str:
    # X-Forwarded-For is client-spoofable, so only honor it when TRUST_PROXY is set
    # (i.e. we are knowingly behind a trusted proxy such as the HF Spaces edge). When
    # trusted, take the LAST hop the proxy appended, not the client-controlled first.
    # Otherwise key on the real socket peer so the limiter can't be trivially bypassed.
    if trust_proxy():
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            hops = [h.strip() for h in fwd.split(",") if h.strip()]
            if hops:
                return hops[-1]
    return request.client.host if request.client else "unknown"
