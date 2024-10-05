import os
from fastapi import APIRouter, Request, HTTPException
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.responses import RedirectResponse
import logging

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
    return await google.authorize_redirect(request, CONFIG['OAUTH_REDIRECT_URI'])

@router.get('/callback')
async def auth_callback(request: Request):
    logger.debug("Callback route accessed")
    logger.debug(f"Request URL: {request.url}")
    logger.debug(f"Request query params: {request.query_params}")
    try:
        token = await google.authorize_access_token(request)
        logger.debug("Access token obtained")
        user_info = token.get('userinfo')
        if not user_info:
            raise ValueError("User info not found in token")
        request.session['user'] = dict(user_info)
        return RedirectResponse(url='/storegenerator')
    except Exception as e:
        logger.error(f"Error during authorization: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error during authorization: {str(e)}")

@router.get('/profile')
async def profile(request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

