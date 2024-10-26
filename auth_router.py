import os
from fastapi import APIRouter, Request, HTTPException, Depends
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.responses import RedirectResponse, JSONResponse
import logging
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

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
    # Generate a new nonce for each login attempt
    nonce = os.urandom(16).hex()
    request.session['nonce'] = nonce
    redirect_uri = request.url_for('auth_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri, nonce=nonce)

@router.get('/callback')
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        nonce = request.session.pop('nonce', None)
        user = await oauth.google.parse_id_token(token, nonce=nonce)
        
        logger.info(f"Received user information: {user}")
        
        # Set user information in the session
        request.session['user'] = dict(user)
        
        # Set session expiration (e.g., 1 hour from now)
        request.session['exp'] = (datetime.utcnow() + timedelta(hours=1)).timestamp()
        
        logger.info(f"Session after setting user: {request.session}")
        
        return RedirectResponse(url='/')
    except Exception as e:
        logger.error(f"Error during authorization: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

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
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

def get_current_user_dependency():
    return Depends(get_current_user)

@router.get("/current-user")
async def current_user(user: dict = get_current_user_dependency()):
    return user
