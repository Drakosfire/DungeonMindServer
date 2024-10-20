import os
from fastapi import APIRouter, Request, HTTPException, Depends
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.responses import RedirectResponse, JSONResponse
import logging
from datetime import datetime, timedelta

router = APIRouter()

# Load configuration based on environment
env = os.getenv('ENVIRONMENT', 'development')
if env == 'production':
    from config_production import CONFIG
else:
    from config_development import CONFIG

# Initialize OAuth without passing CONFIG directly
oauth = OAuth()

# Register the Google client
google = oauth.register(
    name='google',
    client_id=CONFIG['GOOGLE_CLIENT_ID'],
    client_secret=CONFIG['GOOGLE_CLIENT_SECRET'],
    redirect_uri=CONFIG['OAUTH_REDIRECT_URI'],
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    access_token_url='https://oauth2.googleapis.com/token',
    client_kwargs={'scope': 'openid profile email'},
)

if not google.client_id or not google.client_secret:
    raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env file or environment variables")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@router.get('/login')
async def login(request: Request):
    logger.debug(f"Login route accessed. Client ID: {google.client_id}")
    logger.debug(f"Redirect URI: {CONFIG['OAUTH_REDIRECT_URI']}")
    redirect_uri = await google.authorize_redirect(request, CONFIG['OAUTH_REDIRECT_URI'])
    return redirect_uri  # Return the RedirectResponse directly

@router.get('/callback')
async def auth_callback(request: Request):
    try:
        token = await google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            raise ValueError("User info not found in token")
        
        # Create a session with user info and expiration
        session_data = {
            'user': dict(user_info),
            'exp': (datetime.utcnow() + timedelta(days=1)).timestamp()  # Set session to expire in 1 day
        }
        request.session.update(session_data)
        
        return RedirectResponse(url='/')
    except Exception as e:
        logger.error(f"Error during authorization: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error during authorization: {str(e)}")

@router.get('/profile')
async def profile(request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Check if session has expired
    exp = request.session.get('exp')
    if exp and datetime.utcnow().timestamp() > exp:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Session expired")
    
    return user

@router.get('/logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/')

# Dependency to get current user
async def get_current_user(request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Check if session has expired
    exp = request.session.get('exp')
    if exp and datetime.utcnow().timestamp() > exp:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Session expired")
    
    return user

# Use this dependency in routes that require authentication
@router.get('/protected-route')
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {"message": "This is a protected route", "user": current_user}

@router.get('/current-user')
async def get_current_user(request: Request):
    user = request.session.get('user')
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    
    # Check if session has expired
    exp = request.session.get('exp')
    if exp and datetime.utcnow().timestamp() > exp:
        request.session.clear()
        return JSONResponse(status_code=401, content={"detail": "Session expired"})
    
    return user
