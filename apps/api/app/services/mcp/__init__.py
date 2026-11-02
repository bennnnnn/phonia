"""Register service-layer MCP tool orchestrators."""

from app.core.config import Settings
from app.gateways.mcp.registry import register
from app.modules.images.gen_tool import ImageGenAdapter
from app.modules.images.search_tool import ImageSearchAdapter
from app.modules.math.tool import SympyAdapter
from app.modules.web_search import WebSearchAdapter


def setup_mcp_adapters(settings: Settings) -> None:
    register(WebSearchAdapter(settings))
    if settings.math_tools_enabled:
        register(SympyAdapter(settings))
    if settings.image_generation_enabled:
        register(ImageGenAdapter(settings))
    if settings.image_search_enabled:
        register(ImageSearchAdapter(settings))
