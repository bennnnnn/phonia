from unittest.mock import MagicMock

from app.core.client_ip import client_ip
from app.core.config import Settings


def test_client_ip_uses_forwarded_header_when_trusted():
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
    settings = Settings(trust_x_forwarded_for=True)

    assert client_ip(request, settings) == "203.0.113.5"


def test_client_ip_ignores_forwarded_header_when_untrusted():
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
    settings = Settings(trust_x_forwarded_for=False)

    assert client_ip(request, settings) == "10.0.0.1"


def test_client_ip_falls_back_when_client_missing():
    request = MagicMock()
    request.client = None
    request.headers = {}

    assert client_ip(request, Settings(trust_x_forwarded_for=False)) == "unknown"


def test_client_ip_uses_host_when_forwarded_header_blank():
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {"x-forwarded-for": "   "}

    assert client_ip(request, Settings(trust_x_forwarded_for=True)) == "10.0.0.1"


def test_client_ip_ignores_spoofed_forwarded_from_untrusted_peer():
    request = MagicMock()
    request.client.host = "203.0.113.5"
    request.headers = {"x-forwarded-for": "1.2.3.4"}
    settings = Settings(trust_x_forwarded_for=True)

    assert client_ip(request, settings) == "203.0.113.5"


def test_client_ip_uses_forwarded_only_from_trusted_proxy():
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
    settings = Settings(trust_x_forwarded_for=True)

    assert client_ip(request, settings) == "203.0.113.5"


def test_client_ip_rejects_invalid_forwarded_ip():
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {"x-forwarded-for": "not-an-ip"}
    settings = Settings(trust_x_forwarded_for=True)

    assert client_ip(request, settings) == "10.0.0.1"


def test_client_ip_ignores_leftmost_spoof_when_proxy_appends_real():
    """Attacker prepends a fake hop; trusted proxy appends the real client."""
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {"x-forwarded-for": "1.2.3.4, 203.0.113.5"}
    settings = Settings(trust_x_forwarded_for=True)

    assert client_ip(request, settings) == "203.0.113.5"


def test_client_ip_prefers_fly_client_ip_over_xff():
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {
        "fly-client-ip": "198.51.100.9",
        "x-forwarded-for": "1.2.3.4, 203.0.113.5",
    }
    settings = Settings(trust_x_forwarded_for=True)

    assert client_ip(request, settings) == "198.51.100.9"


def test_client_ip_ignores_fly_client_ip_from_untrusted_peer():
    request = MagicMock()
    request.client.host = "203.0.113.5"
    request.headers = {"fly-client-ip": "1.2.3.4"}
    settings = Settings(trust_x_forwarded_for=True)

    assert client_ip(request, settings) == "203.0.113.5"


def test_client_ip_falls_back_when_all_xff_hops_are_trusted_proxies():
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers = {"x-forwarded-for": "10.0.0.2, 192.168.1.1"}
    settings = Settings(trust_x_forwarded_for=True)

    assert client_ip(request, settings) == "10.0.0.1"
