from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.content.account_deletion import account_deletion_markdown
from app.content.legal import markdown_to_html
from app.content.privacy_policy import privacy_policy_markdown
from app.content.terms import terms_of_service_markdown
from app.core.config import Settings
from app.core.deps import get_settings_dep

router = APIRouter(prefix="/legal", tags=["legal"])

_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600"}


def _page(markdown: str, *, title: str) -> HTMLResponse:
    return HTMLResponse(markdown_to_html(markdown, page_title=title), headers=_CACHE_HEADERS)


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(settings: Settings = Depends(get_settings_dep)) -> HTMLResponse:
    return _page(privacy_policy_markdown(settings.support_email), title="Recall Privacy Policy")


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service(settings: Settings = Depends(get_settings_dep)) -> HTMLResponse:
    return _page(terms_of_service_markdown(settings.support_email), title="Recall Terms of Service")


@router.get("/delete-account", response_class=HTMLResponse)
async def delete_account(settings: Settings = Depends(get_settings_dep)) -> HTMLResponse:
    """Public page for the Play Console "Delete account URL": no sign-in needed."""
    return _page(
        account_deletion_markdown(settings.support_email), title="Delete Your Recall Account"
    )
