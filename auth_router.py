from fastapi import APIRouter, Request, HTTPException
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.responses import RedirectResponse
import os

router = APIRouter()

# Configuration for OAuth
config_file = '.env'
if not os.path.exists(config_file):
    print(f"Warning: Config file '{config_file}' not found. Using environment variables.")
    config = Config(environ=os.environ)
else:
    config = Config(config_file)

oauth = OAuth(config)

google = oauth.register(
    name='google',
    client_id=config('GOOGLE_CLIENT_ID', default=None),
    client_secret=config('GOOGLE_CLIENT_SECRET', default=None),
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    access_token_url='https://oauth2.googleapis.com/token',
    authorize_redirect_uri='http://localhost:7860/auth/callback',
    client_kwargs={'scope': 'openid profile email'},
)

if not google.client_id or not google.client_secret:
    raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env file or environment variables")

@router.get('/login')
async def login(request: Request):
    redirect_uri = request.url_for('auth_callback')
    return await google.authorize_redirect(request, redirect_uri)

@router.get('/auth/callback')
async def auth_callback(request: Request):
    try:
        token = await google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if not user_info:
            raise ValueError("User info not found in token")
        request.session['user'] = dict(user_info)
        return RedirectResponse(url='/storegenerator')
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error during authorization")

@router.get('/profile')
async def profile(request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

