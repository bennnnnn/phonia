from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import process_bootstrap
from app.core.body_limit import RequestBodyLimitMiddleware
from app.core.compression import CompressionMiddleware
from app.core.config import cors_allow_origins, get_settings
from app.core.domain_errors import register_domain_error_handler
from app.core.request_id import RequestIdMiddleware
from app.core.rest_rate_limit import RestRateLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.unavailable import register_unavailable_handlers
from app.modules.account import api as auth
from app.modules.analytics import api as analytics
from app.modules.attachments import api as attachments
from app.modules.billing import api as webhooks
from app.modules.chat import api as chats
from app.modules.chat import stream_api as chat_stream
from app.modules.chat import ws_api as ws
from app.modules.chemistry import api as chemistry_api
from app.modules.images import api as images
from app.modules.link_preview import api as link_preview
from app.modules.math import api as math_api
from app.modules.memory import api as memories
from app.modules.notifications import api as users
from app.modules.physics import api as physics_api
from app.modules.search import api as search
from app.modules.speech import api as speech
from app.modules.speech import realtime as speech_realtime
from app.modules.todos import api as todos
from app.routers import (
    admin,
    health,
    legal,
    models,
)

# Routes that take a photo or audio clip in the body. Everything else gets
# the small JSON cap (``max_request_body_bytes``); these get
# ``max_upload_request_body_bytes``. Each route still enforces its own exact
# limit — this only stops a body from being buffered past the cap.
UPLOAD_BODY_PATHS = (
    r"/speech/transcribe",
    r"/(math|physics|chemistry)/scan/read",
    r"/attachments/[^/]+/upload",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    await process_bootstrap.initialize_process(settings)
    role = process_bootstrap.validate_process_role(settings)
    if role in ("all", "worker"):
        await process_bootstrap.start_worker_runtime(settings)
    yield
    await process_bootstrap.shutdown_process(stop_worker=role in ("all", "worker"))


def create_app() -> FastAPI:
    settings = get_settings()
    # Hide OpenAPI/Swagger on production — reduces scanner surface. Dev/staging
    # keep /docs for local exploration.
    docs_enabled = settings.environment != "production"
    app = FastAPI(
        title="Recall API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    cors_origins = cors_allow_origins(settings)
    # Middleware is outermost-last: rate-limit must sit *inside* CORS so a 429
    # still gets Access-Control-* headers (browsers otherwise report a network
    # error). Security headers wrap the whole stack last. The body cap is
    # innermost so its 413 still carries CORS / request-id / security headers.
    app.add_middleware(RequestBodyLimitMiddleware, upload_paths=UPLOAD_BODY_PATHS)
    app.add_middleware(RestRateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        # Credentials cannot be used with wildcard origins; only enable when
        # an explicit allow-list is configured (prod requires that).
        allow_credentials=cors_origins != ["*"],
        # Explicit method/header allowlists — `["*"]` here reflects every
        # method/header the client might use and lets the browser block the
        # rest, instead of echoing whatever the client sends.
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-CSRF-Token"],
    )
    # Baseline security headers (nosniff / no-frame / no-referrer / HSTS in
    # production behind TLS). Added last so it wraps the whole stack on the
    # way out; per-route headers that already set one are not overridden.
    app.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=settings.environment == "production",
    )
    # Outermost: every JSON body the stack produces, error replies included, leaves
    # gzipped for a client that accepts it. Streams and sockets pass untouched.
    app.add_middleware(CompressionMiddleware)
    register_unavailable_handlers(app)
    register_domain_error_handler(app)

    app.include_router(health.router)
    app.include_router(legal.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(analytics.router)
    app.include_router(webhooks.router)
    app.include_router(webhooks.plans_router)
    app.include_router(users.router)
    app.include_router(link_preview.router)
    app.include_router(chats.router)
    app.include_router(chat_stream.router)
    app.include_router(memories.router)
    app.include_router(models.router)
    app.include_router(todos.router)
    app.include_router(math_api.router)
    app.include_router(physics_api.router)
    app.include_router(chemistry_api.router)
    app.include_router(search.router)
    app.include_router(attachments.router)
    app.include_router(speech.router)
    app.include_router(speech_realtime.router)
    app.include_router(images.router)
    app.include_router(ws.router)

    return app


app = create_app()
