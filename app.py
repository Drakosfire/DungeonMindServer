from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from fastapi import Depends


import os
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the current environment
env = os.environ.get('ENVIRONMENT', 'development')
if env == 'production':
    load_dotenv('.env.production', override=True)
    logger.info(f"Production environment detected.")
else:
    load_dotenv('.env.development', override=True)
    logger.info(f"Development environment detected.")

# Fail closed before importing SMS router (which may honor TWILIO_TEST_MODE)
from security.production_guards import assert_safe_production_config

assert_safe_production_config()

# Presence-only startup checks (never log secret values, lengths, or endpoints)
logger.debug(
    "SMS/Twilio env configured: external_key=%s external_endpoint=%s twilio_sid=%s twilio_token=%s",
    bool(os.getenv("EXTERNAL_MESSAGE_API_KEY")),
    bool(os.getenv("EXTERNAL_SMS_ENDPOINT")),
    bool(os.getenv("TWILIO_ACCOUNT_SID")),
    bool(os.getenv("TWILIO_AUTH_TOKEN")),
)

# Import routers AFTER loading the environment variables
from routers import (
    auth_router,
    session_router,
    store_router,
    lawyer_router
)

# Import SMS router
from sms.sms_router import router as sms_router

# Import new focused CardGenerator routers (replacing monolithic cardgenerator_router)
from routers.card_generation_router import router as card_generation_router
from routers.image_management_router import router as image_management_router
from routers.asset_router import router as asset_router
from routers.cardgenerator_project_router import router as cardgenerator_project_router
from routers.cardgenerator_compatibility_router import router as cardgenerator_compatibility_router

# Import legacy StatBlockGenerator app routes and historical v2 compatibility routes.
from routers.statblockgenerator_router import router as statblockgenerator_router
from routers import statblockgenerator_router as statblockgenerator_router_module
from routers.statblock_v2_compatibility_router import router as statblock_v2_compatibility_router
from routers import statblock_v2_compatibility_router as statblock_v2_compatibility_router_module
from statblockgenerator.runtime import get_statblock_generator as get_legacy_statblock_generator

# One shared StatBlockGenerator / OpenAI client for legacy + v2 compatibility mounts.
_shared_statblock_generator = get_legacy_statblock_generator()
statblockgenerator_router_module.statblock_generator = _shared_statblock_generator
statblock_v2_compatibility_router_module.statblock_generator = _shared_statblock_generator

# Import DungeonBuddy statblock v1 bounded-context router
from firestore.firebase_config import db as dungeonbuddy_statblocks_v1_db
from statblocks_v1.api import dependencies as dungeonbuddy_statblocks_v1_dependencies
from statblocks_v1.api.health import health_router as dungeonbuddy_statblocks_v1_health_router
from statblocks_v1.api.health import liveness_router as dungeonbuddy_statblocks_v1_liveness_router
from statblocks_v1.api.health import configure_composition_probe as configure_statblocks_v1_composition_probe
from statblocks_v1.api.http_errors import register_error_handlers as register_statblocks_v1_error_handlers
from statblocks_v1.api.router import router as dungeonbuddy_statblocks_v1_router
from statblocks_v1.config import StatblocksV1Settings as DungeonBuddyStatblocksV1Settings
from statblocks_v1.infrastructure.production_asset_pipeline import (
    generate_assets as dungeonbuddy_statblocks_v1_asset_pipeline,
    production_asset_credentials_ready as dungeonbuddy_statblocks_v1_assets_ready,
)
from statblocks_v1.infrastructure.runtime import (
    build_candidate_repository as build_statblocks_v1_candidate_repository,
    build_generation_service as build_statblocks_v1_generation_service,
    build_persistence_repository as build_statblocks_v1_persistence_repository,
    configure_asset_pipeline as configure_statblocks_v1_asset_pipeline,
    probe_production_composition as probe_statblocks_v1_composition,
)
from statblocks_v1.observability import request_observability as statblocks_v1_request_observability

# Import PlayerCharacterGenerator router
from routers.playercharactergenerator_router import router as playercharactergenerator_router

# Import Demo router for testing GenerationDrawerEngine
from routers.demo_router import router as demo_router

# Import MapGenerator router
from routers.map_router import router as map_router

# Import new global session and object routers
from routers.global_session_router import router as global_session_router
from routers.global_objects_router import router as global_objects_router

# Import session_manager
from session_management import get_session

# Import RulesLawyerService
from routers.ruleslawyer_router import RulesLawyerService

app = FastAPI()

# Initialize RulesLawyerService
rules_lawyer_service = RulesLawyerService()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan function to preload embeddings on app startup."""
    try:
        logger.info("Starting application and loading default embeddings...")
        # Load default embeddings into memory
        rules_lawyer_service.load_embeddings_on_startup()
        logger.info("Default embeddings successfully cached.")
        yield  # Application runs here
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        raise e
    finally:
        logger.info("Cleaning up resources...")


# Set allowed hosts based on the environment
# This is a comma-separated list of hosts, so we need to split it
allowed_hosts = os.environ.get('ALLOWED_HOSTS', '').split(',')
logger.info(f"Allowed hosts: {allowed_hosts}")
react_landing_url = os.environ.get('REACT_LANDING_URL')
logger.info(f"React landing URL: {react_landing_url}")

# Convert hosts to proper CORS origins
cors_origins = []
for host in allowed_hosts:
    host = host.strip()
    if host.startswith('http'):
        cors_origins.append(host)
    else:
        # Add both http and https for localhost
        if 'localhost' in host or '127.0.0.1' in host:
            cors_origins.extend([f"http://{host}", f"https://{host}"])
        else:
            cors_origins.append(f"https://{host}")

logger.info(f"CORS origins: {cors_origins}")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add standardized session middleware
from session_config import add_session_middleware
add_session_middleware(app)
# Add the middleware with the appropriate allowed hosts (this used to be first)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# Reject oversized bodies early (matches nginx client_max_body_size 10M on dungeonmind.net)
from security_limits.request_limits import limit_request_body_middleware

app.middleware("http")(limit_request_body_middleware)


@app.middleware("http")
async def _release_demo_quota_middleware(request, call_next):
    """Release in-flight demo quota slots after the response completes."""
    try:
        return await call_next(request)
    finally:
        ip = getattr(request.state, "demo_quota_ip", None)
        if ip:
            from security_limits.demo_quota import demo_quota_store
            demo_quota_store.release(ip)

# Routers
app.include_router(
    session_router,
    prefix="/api/session",
    tags=["session"]
)

app.include_router(
    auth_router, 
    prefix='/api/auth',
    tags=["auth"]
)

app.include_router(
    store_router, 
    prefix="/api/store",
    tags=["store"],
    dependencies=[Depends(get_session)]
)

app.include_router(
    lawyer_router, 
    prefix="/api/ruleslawyer",
    tags=["ruleslawyer"],
    dependencies=[Depends(get_session)]
)

app.include_router(
    sms_router,
    prefix="/api/sms",
    tags=["sms"]
)

# Register new focused CardGenerator routers (replacing monolithic cardgenerator_router)
app.include_router(
    card_generation_router,
    tags=["Card Generation"]
)

app.include_router(
    image_management_router,
    tags=["Image Management"]
)

app.include_router(
    asset_router,
    tags=["Assets"]
)

app.include_router(
    cardgenerator_project_router,
    tags=["CardGenerator Projects"]
)

# TEMPORARY: Compatibility router for old monolithic endpoints
# TODO: Remove in v3.0 after frontend migration is complete
app.include_router(
    cardgenerator_compatibility_router,
    tags=["CardGenerator Compatibility (Deprecated)"]
)

# Include new global session and object routers
app.include_router(
    global_session_router,
    tags=["Global Session Management"]
)

app.include_router(
    global_objects_router,
    tags=["Global Object Management"]
)

# Include legacy StatBlockGenerator app routes and historical v2 compatibility routes.
# Both routers bind the shared StatBlockGenerator from statblockgenerator.runtime
# so production import constructs one generator/OpenAI client, not two.
app.include_router(
    statblockgenerator_router,
    tags=["StatBlock Generator (Legacy App)"]
)
app.include_router(
    statblock_v2_compatibility_router,
    tags=["StatBlock Generator v2 (Historical Compatibility)"]
)

# Include DungeonBuddy statblock v1 router (candidate workflow).
# Wire factories from app.py so api never imports infrastructure.
register_statblocks_v1_error_handlers(app)
# Only advertise/inject the asset pipeline when generation + CDN credentials exist.
_statblocks_v1_asset_pipeline = (
    dungeonbuddy_statblocks_v1_asset_pipeline
    if dungeonbuddy_statblocks_v1_assets_ready()
    else None
)
configure_statblocks_v1_asset_pipeline(_statblocks_v1_asset_pipeline)
dungeonbuddy_statblocks_v1_dependencies.configure_candidate_repository_factory(
    lambda: build_statblocks_v1_candidate_repository(dungeonbuddy_statblocks_v1_db)
)
dungeonbuddy_statblocks_v1_dependencies.configure_persistence_repository_factory(
    lambda: build_statblocks_v1_persistence_repository(dungeonbuddy_statblocks_v1_db)
)
dungeonbuddy_statblocks_v1_dependencies.configure_generation_service_factory(
    lambda: build_statblocks_v1_generation_service(
        client=dungeonbuddy_statblocks_v1_db,
        asset_pipeline=_statblocks_v1_asset_pipeline,
    )
)


def _statblocks_v1_composition_probe(settings: DungeonBuddyStatblocksV1Settings) -> list[str]:
    # Asset gateway stays opt-in; when enabled without a pipeline, readiness fails closed.
    return probe_statblocks_v1_composition(
        settings,
        client=dungeonbuddy_statblocks_v1_db,
        factories_configured=True,
    )


configure_statblocks_v1_composition_probe(_statblocks_v1_composition_probe)
app.middleware("http")(statblocks_v1_request_observability)
app.include_router(dungeonbuddy_statblocks_v1_liveness_router)
app.include_router(dungeonbuddy_statblocks_v1_health_router)
app.include_router(
    dungeonbuddy_statblocks_v1_router,
    tags=["DungeonBuddy Statblocks v1"]
)

# Include PlayerCharacterGenerator router
app.include_router(
    playercharactergenerator_router,
    tags=["Player Character Generator"]
)

# Demo router is opt-in only (never mounted in production by default).
_demo_enabled = os.getenv("DEMO_ROUTER_ENABLED", "false").lower() == "true"
if env != "production" and _demo_enabled:
    app.include_router(
        demo_router,
        tags=["Demo/Testing"]
    )
elif env == "production" and _demo_enabled:
    logger.warning("DEMO_ROUTER_ENABLED ignored in production")

# Include MapGenerator router
app.include_router(
    map_router,
    tags=["Map Generator"]
)

# Health check route
@app.get("/health", response_class=JSONResponse)
async def health_check():
    """
    Global health check endpoint for DungeonMind API.
    Returns overall server status and environment info.
    """
    return {
        "status": "ok",
        "service": "dungeonmind-api",
        "environment": env,
        "services": {
            "statblockgenerator": "/api/statblockgenerator/health",
            "playercharactergenerator": "/api/playercharactergenerator/health",
            "cardgenerator": "/api/cardgenerator/health",
            "ruleslawyer": "/api/ruleslawyer/health",
            "mapgenerator": "/api/mapgenerator/health"
        }
    }


@app.get("/api/health", response_class=JSONResponse)
async def api_health_check():
    """
    API-prefixed health check for consistent frontend access.
    """
    return {
        "status": "ok",
        "service": "dungeonmind-api",
        "environment": env
    }

# Serve React app directly
@app.get("/", response_class=RedirectResponse)
async def serve_react_app():
    return RedirectResponse(url=react_landing_url)

#return the dungeonmind server api root url
@app.get("/config")
async def get_config():
    return {"DUNGEONMIND_API_URL": os.environ.get('DUNGEONMIND_API_URL')}


# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")


def create_app() -> FastAPI:
    """
    Application factory for tests and alternative entrypoints.

    Re-checks production guards. Router mounting happens at module import
    (uvicorn `app:app`); callers that need a fresh ENVIRONMENT for mounts
    should import this module in a subprocess after setting env.
    """
    assert_safe_production_config()
    return app


if __name__ == "__main__":
    import uvicorn
    
    # Enable hot reload in development environment
    reload = env == 'development'
    logger.info(f"Starting server with reload={reload}")
    
    if reload:
        # Use import string format for reload functionality
        uvicorn.run(
            "app:app",  # Import string required for reload
            host="0.0.0.0", 
            port=7860,
            reload=True,
            reload_dirs=["routers", "cardgenerator", "cloudflare", "cloudflareR2", "firestore", "ruleslawyer", "storegenerator", "sms", "mapgenerator"]
        )
    else:
        # Use direct app object for production
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=7860,
            reload=False
        )
