from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.deps import get_current_user, get_redis, get_settings_dep
from app.models import model_catalog
from app.models.orm import User
from app.models.schemas import ModelInfo
from app.services import model_health

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelInfo])
async def list_models(
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> list[ModelInfo]:
    """Selectable chat models with pricing, availability, and live health.

    The "Auto" option is not a model — the client offers it separately and the
    backend resolves it per message. Provider routing stays server-side only.
    """
    _ = user
    selectable = model_catalog.selectable_models()
    health = await model_health.enrich_models_health(redis, settings, [m.id for m in selectable])
    return [
        ModelInfo(
            id=m.id,
            label=m.label,
            description=m.description,
            tier=m.tier,
            plan_access=m.plan_access,
            available=model_health.is_available(m, settings),
            input_price_per_m=m.input_price_per_m,
            output_price_per_m=m.output_price_per_m,
            quota_multiplier=m.quota_multiplier,
            healthy=health[m.id].healthy,
            latency_p50_ms=health[m.id].latency_p50_ms,
            health_samples=health[m.id].sample_count,
        )
        for m in selectable
    ]
