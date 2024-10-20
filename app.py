from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from auth_router import router as auth_router
from storegenerator.store_router import router as store_router
import os

app = FastAPI()

# Get the current environment
env = os.getenv('ENVIRONMENT', 'development')

# Set allowed hosts based on the environment
if env == 'production':
    allowed_hosts = ["www.dungeonmind.net"]
else:
    allowed_hosts = ["localhost", "127.0.0.1", "0.0.0.0", "localhost:7860", "localhost:3000"]
    react_landing_url = "http://localhost:3000"
# Add the middleware with the appropriate allowed hosts
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600
)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))

# Routers
app.include_router(auth_router, prefix='/auth')
app.include_router(store_router)

# Health check route
@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "ok"}

# Redirect root to React app on port 3000
@app.get("/", response_class=HTMLResponse)
async def redirect_to_react():
    return HTMLResponse(content=f'<meta http-equiv="refresh" content="0; url={react_landing_url}" />')

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/saved_data", StaticFiles(directory="saved_data"), name="saved_data")
app.mount("/storegenerator/static", StaticFiles(directory="storegenerator/static"), name="storegenerator_static")

# Mount React build directory at a specific path
app.mount("/react-landing", StaticFiles(directory="react-landing/build", html=True), name="react_landing")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
