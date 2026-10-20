import os
from fastapi import APIRouter, Request, HTTPException, Depends
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.responses import RedirectResponse, JSONResponse, Response
import logging
from datetime import datetime, timedelta
import ipaddress
import re
from urllib.parse import unquote, urlsplit

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

# Defer hard failure to login — import-time raise breaks test collection
logger.info(f"Redirect URI: {redirect_callback}")
_oauth_configured = bool(google.client_id and google.client_secret)
if not _oauth_configured:
    logger.error(
        "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not set; "
        "/api/auth/login will return 503 until configured"
    )


_RETURN_PATH_CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def _has_unsafe_percent_decoding(value: str, *, reject_separators: bool = True) -> bool:
    """Reject separators or controls revealed by repeated percent decoding."""
    current = value
    for _ in range(8):
        decoded = unquote(current)
        if decoded == current:
            return False

        if len(_RETURN_PATH_CONTROL.findall(decoded)) > len(
            _RETURN_PATH_CONTROL.findall(current)
        ):
            return True
        if reject_separators and (
            decoded.count('/') > current.count('/')
            or decoded.count('\\') > current.count('\\')
        ):
            return True
        current = decoded

    # Deeply nested escaping is ambiguous and not useful in a return path.
    return unquote(current) != current


def _safe_frontend_return_path(value: str | None) -> str:
    """Accept only a same-origin absolute path for the post-login return."""
    if not value or not value.startswith('/') or value.startswith('//'):
        return '/'
    if '\\' in value or _RETURN_PATH_CONTROL.search(value):
        return '/'
    try:
        parsed = urlsplit(value)
    except ValueError:
        return '/'
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith('/')
        or parsed.path.startswith('//')
    ):
        return '/'
    if (
        _has_unsafe_percent_decoding(parsed.path)
        or _has_unsafe_percent_decoding(parsed.query, reject_separators=False)
        or _has_unsafe_percent_decoding(parsed.fragment, reject_separators=False)
    ):
        return '/'
    return value


def _canonical_http_origin(value: str | None) -> str | None:
    """Return a canonical HTTP(S) origin, rejecting URL components beyond origin."""
    if (
        not value
        or value != value.strip()
        or value.lower() == 'null'
        or ',' in value
        or '?' in value
        or '#' in value
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        return None

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    host = parsed.hostname
    if (
        scheme not in {'http', 'https'}
        or not parsed.netloc
        or parsed.netloc.endswith(':')
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or not host
        or '%' in host
        or (port is not None and not 1 <= port <= 65535)
    ):
        return None

    if ':' in host:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return None
        if address.version != 6:
            return None
        canonical_host = f'[{address.compressed}]'
    else:
        try:
            canonical_host = host.encode('idna').decode('ascii').lower()
        except UnicodeError:
            return None
        labels = canonical_host.split('.')
        if len(canonical_host) > 253 or any(
            not label
            or len(label) > 63
            or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?', label)
            for label in labels
        ):
            return None
        if all(label.isdigit() for label in labels):
            try:
                if ipaddress.ip_address(canonical_host).version != 4:
                    return None
            except ValueError:
                return None

    if port == (443 if scheme == 'https' else 80):
        port = None
    port_suffix = f':{port}' if port is not None else ''
    return f'{scheme}://{canonical_host}{port_suffix}'


def _trusted_logout_origins() -> set[str]:
    """Read the explicit, comma-separated logout origin allowlist."""
    configured = os.environ.get('AUTH_TRUSTED_FRONTEND_ORIGINS', '')
    if not configured.strip():
        return set()

    origins: set[str] = set()
    for item in configured.split(','):
        origin = _canonical_http_origin(item.strip())
        if origin is None:
            return set()
        origins.add(origin)
    return origins


def _has_trusted_logout_origin(request: Request) -> bool:
    supplied_origins = request.headers.getlist('origin')
    if len(supplied_origins) != 1:
        return False
    origin = _canonical_http_origin(supplied_origins[0])
    return origin is not None and origin in _trusted_logout_origins()


@router.get('/login')
async def login(request: Request):
    if not _oauth_configured:
        raise HTTPException(status_code=503, detail="OAuth is not configured on this server")

    redirect_uri = redirect_callback
    
    # Store the return URL in session so we can redirect back after OAuth
    return_to = _safe_frontend_return_path(request.query_params.get('redirect', '/'))
    request.session['return_to'] = return_to
    
    logger.info(
        "Login request: host=%s return_to_set=%s",
        request.headers.get("host", "unknown"),
        bool(return_to),
    )
    return await oauth.google.authorize_redirect(request, redirect_uri, nonce=request.session.get('nonce'))

@router.get('/callback')
async def auth_callback(request: Request):
    try:
        # Never log headers, cookies, session dicts, or full URL (may contain code/state)
        logger.info("Auth callback processing")
        
        token = await oauth.google.authorize_access_token(request)
        user = await oauth.google.parse_id_token(token, nonce=request.session.get('nonce'))
        
        # Store user in session
        user_dict = dict(user)
        request.session['user'] = user_dict
        
        logger.info("User authenticated successfully (sub present=%s)", bool(user_dict.get("sub")))
        
        # Get the return URL from session (stored during login)
        return_to = _safe_frontend_return_path(request.session.pop('return_to', '/'))
        
        # Redirect back to the frontend application at the original page
        frontend_url = os.environ.get('REACT_LANDING_URL', 'http://localhost:3000')
        redirect_url = frontend_url.rstrip('/') + return_to
        logger.info("Auth callback redirecting to frontend")
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error("Error during authorization: %s", type(e).__name__, exc_info=True)
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

@router.post('/logout', status_code=204)
async def logout(request: Request):
    """Clear the browser session only for an explicitly trusted frontend origin."""
    if not _has_trusted_logout_origin(request):
        logger.warning('Logout rejected due to missing, malformed, or untrusted Origin')
        raise HTTPException(status_code=403, detail='Untrusted request origin')

    logger.info("Logout requested (authenticated=%s)", "user" in request.session)
    request.session.clear()
    return Response(status_code=204)

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

@router.get('/current-user')
async def get_current_user_endpoint(request: Request):
    """
    Get the current authenticated user.
    Returns user data if authenticated, 401 if not.
    """
    auth_result = await auth_service.get_current_user_from_request(request)
    
    if auth_result.authenticated:
        logger.info("current-user: authenticated")
        # Return the user data as a dictionary for API compatibility
        return auth_result.user.dict()
    else:
        logger.info("current-user: not authenticated")
        return JSONResponse(status_code=401, content={"detail": auth_result.error or "Not authenticated"})
