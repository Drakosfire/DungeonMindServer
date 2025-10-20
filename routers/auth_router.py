import os
from fastapi import APIRouter, Request, HTTPException, Depends
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.responses import RedirectResponse, JSONResponse
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
router = APIRouter()

# Load configuration based on environment
env = os.getenv('ENVIRONMENT', 'development')
logger.info(f"Current environment: {env}")

# Initialize OAuth without passing CONFIG directly
oauth = OAuth()

# Build a safe redirect URI even if env var is missing
base_api_url = os.environ.get('DUNGEONMIND_API_URL')
if not base_api_url:
    logger.warning("DUNGEONMIND_API_URL not set; defaulting to http://localhost:7860")
    base_api_url = 'http://localhost:7860'
redirect_callback = f"{base_api_url.rstrip('/')}/api/auth/callback"

# Register the Google client
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    redirect_uri=redirect_callback,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    access_token_url='https://oauth2.googleapis.com/token',
    client_kwargs={'scope': 'openid profile email'},
)

# Check if the required environment variables are set
logger.info(f"Redirect URI: {redirect_callback}")
if not google.client_id or not google.client_secret:
    raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env file or environment variables")

@router.get('/login')
async def login(request: Request):
    redirect_uri = redirect_callback
    
    # Store the return URL in session so we can redirect back after OAuth
    return_to = request.query_params.get('redirect', '/')
    request.session['return_to'] = return_to
    
    logger.info(f"Login request from: {request.headers.get('x-forwarded-proto', 'unknown')}://{request.headers.get('host', 'unknown')}")
    logger.info(f"Using redirect URI: {redirect_uri}")
    logger.info(f"Will return user to: {return_to}")
    return await oauth.google.authorize_redirect(request, redirect_uri, nonce=request.session.get('nonce'))

@router.get('/callback')
async def auth_callback(request: Request):
    try:
        logger.info("Auth callback processing...")
        logger.info(f"Request URL: {request.url}")
        logger.info(f"Request headers: {dict(request.headers)}")
        logger.info(f"Existing session data: {dict(request.session) if request.session else 'None'}")
        
        token = await oauth.google.authorize_access_token(request)
        user = await oauth.google.parse_id_token(token, nonce=request.session.get('nonce'))
        
        # Store user in session
        user_dict = dict(user)
        request.session['user'] = user_dict
        
        logger.info(f"User authenticated successfully: {user_dict.get('email')} (ID: {user_dict.get('sub')})")
        logger.info(f"Session after storing user: {dict(request.session)}")
        logger.info(f"Session ID: {request.session.get('_session_id', 'no-session-id')}")
        
        # Get the return URL from session (stored during login)
        return_to = request.session.pop('return_to', '/')
        
        # Redirect back to the frontend application at the original page
        frontend_url = os.environ.get('REACT_LANDING_URL', 'http://localhost:3000')
        redirect_url = frontend_url.rstrip('/') + return_to
        logger.info(f"Redirecting to frontend: {redirect_url}")
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error(f"Error during authorization: {str(e)}", exc_info=True)
        # Redirect to frontend with error parameter
        frontend_url = os.environ.get('REACT_LANDING_URL', 'http://localhost:3000')
        return RedirectResponse(url=f"{frontend_url}?auth_error=true")

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
    user_email = request.session.get('user', {}).get('email', 'unknown')
    logger.info(f"Logging out user: {user_email}")
    request.session.clear()
    
    # Redirect back to frontend
    frontend_url = os.environ.get('REACT_LANDING_URL', 'http://localhost:3000')
    return RedirectResponse(url=frontend_url)

# Import centralized auth service
from auth_service import auth_service, AuthResult, User

# Dependency to get current user
async def get_current_user(request: Request) -> User:
    """
    FastAPI dependency for getting the current authenticated user.
    Raises HTTPException if not authenticated.
    """
    auth_result = await auth_service.get_current_user_from_request(request)
    if not auth_result.authenticated:
        raise HTTPException(status_code=401, detail=auth_result.error or "Unauthorized")
    return auth_result.user

# Optional user dependency (doesn't raise exception if not authenticated)
async def get_current_user_optional(request: Request) -> User | None:
    """
    FastAPI dependency for getting the current user without requiring authentication.
    Returns None if not authenticated.
    """
    auth_result = await auth_service.get_current_user_from_request(request)
    return auth_result.user if auth_result.authenticated else None

# Use this dependency in routes that require authentication
@router.get('/protected-route')
async def protected_route(current_user: User = Depends(get_current_user)):
    return {"message": "This is a protected route", "user": current_user.dict()}

@router.get('/debug-config')
async def debug_config():
    """
    Debug endpoint to check environment configuration
    """
    return {
        "environment": os.environ.get('ENVIRONMENT', 'not-set'),
        "dungeonmind_api_url": os.environ.get('DUNGEONMIND_API_URL', 'not-set'),
        "react_landing_url": os.environ.get('REACT_LANDING_URL', 'not-set'),
        "google_client_id": "set" if os.environ.get('GOOGLE_CLIENT_ID') else "not-set",
        "google_client_secret": "set" if os.environ.get('GOOGLE_CLIENT_SECRET') else "not-set",
        "session_secret_key": "set" if os.environ.get('SESSION_SECRET_KEY') else "not-set",
    }

@router.get('/debug-session')
async def debug_session(request: Request):
    """
    Debug endpoint to check session and cookie status
    """
    return {
        "session_data": dict(request.session) if request.session else {},
        "cookies": dict(request.cookies),
        "headers": dict(request.headers),
        "url": str(request.url),
        "method": request.method,
        "has_user_in_session": 'user' in (request.session or {}),
        "session_keys": list(request.session.keys()) if request.session else [],
    }

@router.get('/current-user')
async def get_current_user_endpoint(request: Request):
    """
    Get the current authenticated user.
    Returns user data if authenticated, 401 if not.
    """
    logger.info("'/current-user' endpoint accessed")
    
    # Debug session and cookie information
    session_id = request.session.get('session_id', 'no-session-id')
    cookies_received = dict(request.cookies)
    session_data = dict(request.session) if request.session else {}
    
    logger.info(f"Session ID: {session_id}")
    logger.info(f"Cookies received: {list(cookies_received.keys())}")
    logger.info(f"Session data keys: {list(session_data.keys())}")
    logger.info(f"Has 'user' in session: {'user' in session_data}")
    
    if 'user' in session_data:
        logger.info(f"User in session: {session_data['user'].get('email', 'no-email')}")
    
    auth_result = await auth_service.get_current_user_from_request(request)
    
    if auth_result.authenticated:
        logger.info(f"User authenticated successfully: {auth_result.user.email}")
        # Return the user data as a dictionary for API compatibility
        return auth_result.user.dict()
    else:
        logger.warning(f"User not authenticated: {auth_result.error}")
        return JSONResponse(status_code=401, content={"detail": auth_result.error or "Not authenticated"})
