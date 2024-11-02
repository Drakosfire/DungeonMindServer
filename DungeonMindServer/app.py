from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from auth_router import router as auth_router
from store_router import router as store_router
import os
import logging

logger = logging.getLogger(__name__)

app = FastAPI()

# Add SessionMiddleware
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.environ.get("SESSION_SECRET_KEY"),
    same_site="lax",  # This allows cookies to be sent in cross-site requests
    https_only=True, # Set to True in production
    domain=".dungeonmind.net" # Set to .dungeonmind.net in production
)

# Get the current environment
env = os.environ.get('ENVIRONMENT', 'development')

# Set allowed hosts based on the environment
if env == 'production':
    allowed_hosts = ["www.dungeonmind.net"]
    react_landing_url = "https://www.dungeonmind.net"
    logger.info(f"Production environment detected. React landing URL: {react_landing_url}")

else:
    allowed_hosts = ["localhost", "127.0.0.1", "0.0.0.0", "localhost:7860", "localhost:3000", "dev.dungeonmind.net", "storegenerator"]
    react_landing_url = "http://dev.dungeonmind.net"
    logger.info(f"Development environment detected. React landing URL: {react_landing_url}")

# Add the middleware with the appropriate allowed hosts
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://dev.dungeonmind.net", "https://www.dungeonmind.net"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router, prefix='/auth')
app.include_router(store_router, prefix="/store")

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
        "DUNGEONMIND_BASE_URL": "https://www.dungeonmind.net" if env == 'production' else "https://dev.dungeonmind.net",
        "DUNGEONMIND_API_URL": "https://www.dungeonmind.net" if env == 'production' else "https://dev.dungeonmind.net",
        "ENVIRONMENT": env
    }

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/saved_data", StaticFiles(directory="saved_data"), name="saved_data")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
