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

# Health check route
@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "ok"}

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
            reload_dirs=["routers", "cardgenerator", "cloudflare", "cloudflareR2", "firestore", "ruleslawyer", "storegenerator", "sms"]
        )
    else:
        # Use direct app object for production
        uvicorn.run(
            app, 
            host="0.0.0.0", 
            port=7860,
            reload=False
        )
