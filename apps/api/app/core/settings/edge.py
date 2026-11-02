"""The HTTP edge: CORS, client IPs behind the proxy, rate limits, body caps, chat sockets."""

from pydantic import BaseModel


class EdgeSettings(BaseModel):
    cors_origins: str = ""
    # Only trust X-Forwarded-For when deployed behind a known reverse proxy (Fly, etc.).
    trust_x_forwarded_for: bool = False
    # Peer CIDRs allowed to append X-Forwarded-For (private/LB ranges by default).
    # Include Fly 6PN (fdaa::/16) so IPv6 mesh peers are trusted when XFF is on.
    trusted_proxy_cidrs: str = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.1/32,fdaa::/16"

    # Per-user/IP REST requests per minute (health + webhooks excluded).
    rest_rate_limit_per_minute: int = 240
    # Chat WebSockets per machine (modules/chat/ws_limits.py): open sockets per
    # user, and seconds idle between turns before a close. 0 disables either.
    ws_max_sockets_per_user: int = 5
    ws_idle_timeout_seconds: float = 300.0
    # Seconds a new chat socket has to send its auth frame before it is dropped.
    ws_auth_timeout_seconds: float = 10.0
    # Request body caps (core/body_limit.py). A declared Content-Length over
    # the cap is refused before any byte is read; a chunked body is counted as
    # it streams. JSON routes stay far below 1 MiB (chat text is 32k chars).
    # Photo/audio routes (scan read ~10.7 MB, transcribe ~6.7 MB, local
    # attachment upload 10 MiB) get the upload cap. 0 disables a cap.
    max_request_body_bytes: int = 1_048_576
    max_upload_request_body_bytes: int = 12 * 1024 * 1024
    support_email: str = ""  # contact on the /legal pages; boot warns while empty
