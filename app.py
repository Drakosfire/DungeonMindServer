from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from auth_router import router as auth_router
import os
import logging

logger = logging.getLogger(__name__)
app = FastAPI()

# Add SessionMiddleware
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SESSION_SECRET_KEY"),
    same_site="lax",  # This allows cookies to be sent in cross-site requests
    https_only=False  # Set to True in production
)

# Get the current environment
env = os.getenv('ENVIRONMENT', 'testing')

# Set allowed hosts and origins based on the environment
if env == 'production':
    logger.info("Production environment detected")
    allowed_hosts = ["www.dungeonmind.net"]
    origins = ["https://www.dungeonmind.net"]
    react_landing_url = "https://www.dungeonmind.net"
else:
    logger.info("Testing or development environment detected")
    allowed_hosts = ["testserver", "localhost", "127.0.0.1"]
    origins = ["http://testserver", "http://localhost", "http://127.0.0.1"]
    react_landing_url = "dev.dungeonmind.net"  # Assuming your React app runs on port 3000 in development

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TrustedHost Middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=allowed_hosts
)

# Routers
app.include_router(auth_router, prefix='/auth')

# Health check route
@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "ok"}

# Serve React app directly
@app.get("/", response_class=RedirectResponse)
async def serve_react_app():
    return RedirectResponse(url=react_landing_url)

# Configuration endpoint
@app.get("/config", response_class=JSONResponse)
async def get_config():
    return {
        "DUNGEONMIND_BASE_URL": "https://www.dungeonmind.net" if env == 'production' else "http://dev.dungeonmind.net",
        "DUNGEONMIND_API_URL": "https://www.dungeonmind.net" if env == 'production' else "http://localhost:7860",
        "ENVIRONMENT": env
    }

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/saved_data", StaticFiles(directory="saved_data"), name="saved_data")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.middleware("http")
async def log_requests(request, call_next):
    logger.debug(f"Received request: {request.method} {request.url}")
    logger.debug(f"Headers: {request.headers}")
    response = await call_next(request)
    logger.debug(f"Response status: {response.status_code}")
    return response

print("Environment variables:")
print(f"TESTING: {os.environ.get('TESTING')}")
print(f"ENVIRONMENT: {os.environ.get('ENVIRONMENT')}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
