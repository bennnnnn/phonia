import pytest
from fastapi.testclient import TestClient

from app.content.legal import contact_markdown, markdown_to_html
from app.core.config import Settings
from app.core.deps import get_settings_dep
from app.main import create_app

_SUPPORT = "help@recall.example"


def _client(support_email: str = _SUPPORT) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(support_email=support_email)
    return TestClient(app)


def test_privacy_policy_html() -> None:
    response = _client().get("/legal/privacy")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Privacy Policy" in response.text
    assert "Google or Apple Sign-In" in response.text
    assert "export_limits" in response.text
    assert "do not retain your data" not in response.text
    assert response.headers.get("cache-control") == "public, max-age=3600"


# Apple 5.1.2(i) and Play User Data: every outside service that receives personal
# data is named, with what it receives.
@pytest.mark.parametrize(
    "named",
    [
        "Effective date:",
        "OpenRouter",
        "Anthropic",
        "OpenAI",
        "Mathpix",
        "Tavily",
        "public search engines",
        "PubChem",
        "RevenueCat",
        "Sentry",
        "Cloudflare R2",
        "Neon",
        "Upstash",
        "Fly.io",
        "Resend",
        "Expo",
        "precise coordinates",
        "push notification token",
        "How Long We Keep Data",
        "30 days",
    ],
)
def test_privacy_policy_names_each_processor_and_fact(named: str) -> None:
    assert named in _client().get("/legal/privacy").text


def test_privacy_policy_says_where_a_scanned_photo_goes() -> None:
    """The scanner sends its photo to the server the moment it is cut (``/{subject}/scan/read``):
    math to Mathpix and a vision model, physics and chemistry to a vision model through
    OpenRouter; the read keeps nothing. The policy said so only for math photos."""
    page = _client().get("/legal/privacy").text
    assert "Scanned problems" in page
    assert "is sent to Recall" in page and "to read the problem" in page
    assert "Recall does not keep that photo" in page
    assert "photos you scan in the scanner (math, physics and chemistry)" in page


@pytest.mark.parametrize("path", ["/legal/privacy", "/legal/terms", "/legal/delete-account"])
def test_legal_pages_link_the_support_email(path: str) -> None:
    text = _client().get(path).text
    assert f'<a href="mailto:{_SUPPORT}">{_SUPPORT}</a>' in text
    assert "app-store listing" not in text


@pytest.mark.parametrize("path", ["/legal/privacy", "/legal/terms", "/legal/delete-account"])
def test_legal_pages_still_render_without_a_support_email(path: str) -> None:
    response = _client(support_email="").get(path)
    assert response.status_code == 200
    assert "mailto:" not in response.text
    assert "app-store listing" in response.text


def test_terms_of_service_html() -> None:
    response = _client().get("/legal/terms")
    assert response.status_code == 200
    assert "Terms of Service" in response.text
    assert "Google or Apple" in response.text
    assert "third-party AI and search services" in response.text
    assert '<a href="/legal/privacy">Privacy Policy</a>' in response.text


def test_delete_account_page_is_public_and_explains_both_ways() -> None:
    response = TestClient(create_app()).get("/legal/delete-account")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.headers.get("cache-control") == "public, max-age=3600"
    text = response.text
    assert "<h1>Delete Your Recall Account</h1>" in text
    assert "<ol>" in text and "Tap Data controls." in text
    assert "Delete your account" in text
    assert "What is deleted" in text and "What is kept, and for how long" in text
    assert "35 days" in text
    assert "does not cancel a subscription" in text


def test_contact_markdown_links_only_a_plain_address() -> None:
    assert contact_markdown(" help@recall.example ") == (
        "email [help@recall.example](mailto:help@recall.example)"
    )
    for unusable in ["", "   ", "not-an-email", "a@b.c) [x](https://evil.example"]:
        assert "mailto:" not in contact_markdown(unusable)


def test_markdown_to_html_escapes_and_only_links_safe_schemes() -> None:
    page = markdown_to_html(
        "\n".join(
            [
                "# Title <b>",
                "- [ok](https://example.com/a?b=1&c=2) and **bold**",
                "1. first",
                "2. [mail](mailto:x@example.com)",
                "[bad](javascript:alert(1)) <script>",
            ]
        ),
        page_title="T",
    )
    assert "<h1>Title &lt;b&gt;</h1>" in page
    assert '<a href="https://example.com/a?b=1&amp;c=2">ok</a>' in page
    assert "<strong>bold</strong>" in page
    assert "<ul>\n<li>" in page and "</ul>\n<ol>" in page
    assert '<a href="mailto:x@example.com">mail</a>' in page
    assert '<a href="javascript' not in page
    assert "&lt;script&gt;" in page


@pytest.mark.parametrize(
    "environment, support_email, warns",
    [
        ("production", "", True),
        ("production", "  ", True),
        ("production", _SUPPORT, False),
        ("development", "", False),
    ],
)
def test_production_boot_warns_without_a_support_email(
    caplog: pytest.LogCaptureFixture, environment: str, support_email: str, warns: bool
) -> None:
    """A missing contact address warns but never blocks boot."""
    import logging

    from app.content.legal import warn_if_no_support_email

    settings = Settings(environment=environment, support_email=support_email)
    with caplog.at_level(logging.WARNING, logger="app.content.legal"):
        warn_if_no_support_email(settings)
    assert any("SUPPORT_EMAIL" in r.getMessage() for r in caplog.records) is warns
