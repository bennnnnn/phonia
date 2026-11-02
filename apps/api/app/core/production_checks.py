"""Production boot rules on single values: service URLs and proxy CIDRs.

``config.validate_production_settings`` collects these; they live here so the
rules stay testable on their own and ``Settings`` keeps to its fields.
"""

import ipaddress
from urllib.parse import urlsplit

# Hosts that mean "this machine": a Settings default (redis://localhost:6379,
# postgres on localhost) or a dev .env leaking into a production boot.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # noqa: S104 - a check, not a bind


def _points_at_this_machine(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOCAL_HOSTS or host.endswith(".localhost")


def service_url_errors(database_url: str, redis_url: str) -> list[str]:
    """What is wrong with the database and Redis URLs for a production boot.

    Both defaults point at localhost, so an unset or mistyped secret used to
    pass every check: the API booted, /health/ready answered 200 with
    ``"redis": "degraded"``, and every authenticated request failed with 503.
    """
    errors: list[str] = []
    if not database_url.strip():
        errors.append("DATABASE_URL is required in production")
    elif _points_at_this_machine(database_url):
        errors.append("DATABASE_URL points at localhost in production (is the secret set?)")
    if not redis_url.strip():
        errors.append("REDIS_URL is required in production")
    elif _points_at_this_machine(redis_url):
        errors.append("REDIS_URL points at localhost in production (is the secret set?)")
    elif urlsplit(redis_url).scheme != "rediss":
        errors.append("REDIS_URL must use TLS (rediss://) in production")
    return errors


def trusted_proxy_cidrs_ipv4_only(cidrs: str) -> bool:
    """True when every non-empty CIDR parses as IPv4 (Fly 6PN would be ignored)."""
    parsed: list[bool] = []
    for raw in cidrs.split(","):
        piece = raw.strip()
        if not piece:
            continue
        try:
            net = ipaddress.ip_network(piece, strict=False)
        except ValueError:
            continue
        parsed.append(isinstance(net, ipaddress.IPv4Network))
    return bool(parsed) and all(parsed)
