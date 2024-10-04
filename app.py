from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from auth_router import router as auth_router
from storegenerator.store_router import router as store_router
import os

app = FastAPI()
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["www.dungeonmind.net"])


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600
)
# Increase the maximum upload size to 10 MB
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["www.dungeonmind.net"],
    
)

app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET_KEY"))

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/saved_data", StaticFiles(directory="saved_data"), name="saved_data")
app.mount("/storegenerator/static", StaticFiles(directory="storegenerator/static"), name="storegenerator_static")

# Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Routers
app.include_router(auth_router, prefix='/auth')
app.include_router(store_router)

# Route to serve the landing page at the root URL
@app.get("/", response_class=HTMLResponse)
async def serve_landing_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get('APP_HOST', '0.0.0.0')
    port = int(os.environ.get('APP_PORT', 7860))
    uvicorn.run(app, host=host, port=port)
