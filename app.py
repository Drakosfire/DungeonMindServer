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

# Debug logging for environment variables
logger.info(f"EXTERNAL_MESSAGE_API_KEY present: {bool(os.getenv('EXTERNAL_MESSAGE_API_KEY'))}")
logger.info(f"EXTERNAL_MESSAGE_API_KEY value: {'*' * len(os.getenv('EXTERNAL_MESSAGE_API_KEY', '')) if os.getenv('EXTERNAL_MESSAGE_API_KEY') else 'None'}")
logger.info(f"EXTERNAL_SMS_ENDPOINT present: {bool(os.getenv('EXTERNAL_SMS_ENDPOINT'))}")
logger.info(f"EXTERNAL_SMS_ENDPOINT value: {os.getenv('EXTERNAL_SMS_ENDPOINT', 'None')}")
logger.info(f"TWILIO_ACCOUNT_SID present: {bool(os.getenv('TWILIO_ACCOUNT_SID'))}")
logger.info(f"TWILIO_AUTH_TOKEN present: {bool(os.getenv('TWILIO_AUTH_TOKEN'))}")

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

# Import StatBlockGenerator router
from routers.statblockgenerator_router import router as statblockgenerator_router

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

# Include StatBlockGenerator router
app.include_router(
    statblockgenerator_router,
    tags=["StatBlock Generator"]
)

# Include DungeonBuddy statblock v1 router (candidate workflow).
# Wire factories from app.py so api never imports infrastructure.
register_statblocks_v1_error_handlers(app)
configure_statblocks_v1_asset_pipeline(dungeonbuddy_statblocks_v1_asset_pipeline)
dungeonbuddy_statblocks_v1_dependencies.configure_candidate_repository_factory(
    lambda: build_statblocks_v1_candidate_repository(dungeonbuddy_statblocks_v1_db)
)
dungeonbuddy_statblocks_v1_dependencies.configure_persistence_repository_factory(
    lambda: build_statblocks_v1_persistence_repository(dungeonbuddy_statblocks_v1_db)
)
dungeonbuddy_statblocks_v1_dependencies.configure_generation_service_factory(
    lambda: build_statblocks_v1_generation_service(
        client=dungeonbuddy_statblocks_v1_db,
        asset_pipeline=dungeonbuddy_statblocks_v1_asset_pipeline,
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

# Include Demo router for testing GenerationDrawerEngine
app.include_router(
    demo_router,
    tags=["Demo/Testing"]
)

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
