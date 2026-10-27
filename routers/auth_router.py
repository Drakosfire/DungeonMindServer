import os
from fastapi import APIRouter, Request, HTTPException, Depends
from authlib.integrations.starlette_client import OAuth
from starlette.responses import RedirectResponse, JSONResponse, Response
import logging
from datetime import datetime
import ipaddress
import re
from urllib.parse import parse_qsl, parse_qs, urlencode, unquote, urlsplit, urlunsplit

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
_WEBSITE_FRONTEND = 'website'
_BUDDY_FRONTEND = 'buddy'
_AUTH_RETURN_SESSION_KEY = 'auth_returns'
_MAX_AUTH_RETURN_FLOWS = 2
_MAX_AUTH_RETURN_PATH_LENGTH = 512
_SAFE_WEBSITE_FALLBACK = 'http://localhost:3000'


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
    if (
        not value
        or len(value) > _MAX_AUTH_RETURN_PATH_LENGTH
        or not value.startswith('/')
        or value.startswith('//')
    ):
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


def _frontend_origin(frontend: str) -> str | None:
    """Resolve a fixed frontend key through server-owned origin configuration."""
    setting = 'BUDDY_FRONTEND_URL' if frontend == _BUDDY_FRONTEND else 'REACT_LANDING_URL'
    configured = os.environ.get(setting)
    if not configured:
        return None if frontend == _BUDDY_FRONTEND else _SAFE_WEBSITE_FALLBACK
    candidate = configured
    try:
        parsed = urlsplit(configured)
    except ValueError:
        return None
    if parsed.path == '/' and not parsed.query and not parsed.fragment:
        candidate = f'{parsed.scheme}://{parsed.netloc}'
    return _canonical_http_origin(candidate)


def _website_fallback_url(return_path: str = '/') -> str:
    """Build a fallback using only the server-owned website origin and safe path."""
    origin = _frontend_origin(_WEBSITE_FRONTEND) or _SAFE_WEBSITE_FALLBACK
    return origin + _safe_frontend_return_path(return_path)


def _frontend_error_path(return_path: str, frontend: str, error: str) -> str:
    """Append a bounded auth error code while retaining safe route state."""
    safe_path = _safe_frontend_return_path(return_path)
    parsed = urlsplit(safe_path)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != 'auth_error'
    ]
    error_value = 'true' if frontend == _WEBSITE_FRONTEND else error
    query.append(('auth_error', error_value))
    return urlunsplit(('', '', parsed.path or '/', urlencode(query, doseq=True), parsed.fragment))


def _requested_frontend(request: Request) -> str:
    values = request.query_params.getlist('frontend')
    return _BUDDY_FRONTEND if values == [_BUDDY_FRONTEND] else _WEBSITE_FRONTEND


def _callback_state(request: Request) -> str | None:
    values = request.query_params.getlist('state')
    if len(values) != 1 or not values[0] or len(values[0]) > 512:
        return None
    if _RETURN_PATH_CONTROL.search(values[0]):
        return None
    return values[0]


def _validated_auth_return(value: object, expected_state: str) -> tuple[str, str] | None:
    if not isinstance(value, dict):
        return None
    state = value.get('state')
    frontend = value.get('frontend')
    return_path = value.get('return_to')
    if (
        not isinstance(state, str)
        or not state
        or state != expected_state
        or len(state) > 512
        or _RETURN_PATH_CONTROL.search(state)
        or not isinstance(frontend, str)
        or frontend not in {_WEBSITE_FRONTEND, _BUDDY_FRONTEND}
        or not isinstance(return_path, str)
    ):
        return None
    return frontend, _safe_frontend_return_path(return_path)


def _stored_auth_returns(session: dict) -> dict[str, dict[str, str]]:
    """Return at most four validated pending login intents from the signed session."""
    value = session.get(_AUTH_RETURN_SESSION_KEY)
    if not isinstance(value, dict):
        return {}
    pending: dict[str, dict[str, str]] = {}
    for state, intent in value.items():
        if not isinstance(state, str) or not state or len(state) > 512:
            continue
        validated = _validated_auth_return(intent, state)
        if validated is None:
            continue
        frontend, return_to = validated
        pending[state] = {
            'state': state,
            'frontend': frontend,
            'return_to': return_to,
        }
    return dict(list(pending.items())[-_MAX_AUTH_RETURN_FLOWS:])


def _callback_error_redirect(frontend: str, return_path: str, error: str) -> RedirectResponse:
    if frontend == _WEBSITE_FRONTEND:
        # Preserve the existing website callback error landing behavior.
        return RedirectResponse(url=_website_fallback_url('/?auth_error=true'))
    origin = _frontend_origin(frontend)
    if origin is None:
        # A missing or malformed Buddy origin must never become redirect authority.
        return RedirectResponse(url=_website_fallback_url('/?auth_error=true'))
    path = _frontend_error_path(return_path, frontend, error)
    return RedirectResponse(url=origin + path)


@router.get('/login')
async def login(request: Request):
    if not _oauth_configured:
        raise HTTPException(status_code=503, detail="OAuth is not configured on this server")

    redirect_uri = redirect_callback
    frontend = _requested_frontend(request)
    frontend_origin = _frontend_origin(frontend)
    if frontend_origin is None:
        return RedirectResponse(url=_website_fallback_url('/?auth_error=true'))

    redirect_values = request.query_params.getlist('redirect')
    return_to = _safe_frontend_return_path(
        redirect_values[0] if len(redirect_values) == 1 else '/'
    )
    logger.info(
        "Login request: frontend=%s return_to_set=%s",
        frontend,
        bool(return_to),
    )
    response = await oauth.google.authorize_redirect(
        request, redirect_uri, nonce=request.session.get('nonce')
    )
    location = response.headers.get('location', '')
    try:
        states = parse_qs(urlsplit(location).query).get('state', [])
    except ValueError:
        states = []
    if (
        len(states) != 1
        or not states[0]
        or len(states[0]) > 512
        or _RETURN_PATH_CONTROL.search(states[0])
    ):
        pending = _stored_auth_returns(request.session)
        if pending:
            request.session[_AUTH_RETURN_SESSION_KEY] = pending
        else:
            request.session.pop(_AUTH_RETURN_SESSION_KEY, None)
        raise HTTPException(status_code=503, detail='OAuth state could not be established')
    pending = _stored_auth_returns(request.session)
    pending.pop(states[0], None)
    pending[states[0]] = {
        'state': states[0],
        'frontend': frontend,
        'return_to': return_to,
    }
    while len(pending) > _MAX_AUTH_RETURN_FLOWS:
        pending.pop(next(iter(pending)))
    request.session[_AUTH_RETURN_SESSION_KEY] = pending
    return response

@router.get('/callback')
async def auth_callback(request: Request):
    callback_state = _callback_state(request)
    pending = _stored_auth_returns(request.session)
    intent = pending.pop(callback_state, None) if callback_state is not None else None
    if pending:
        request.session[_AUTH_RETURN_SESSION_KEY] = pending
    else:
        request.session.pop(_AUTH_RETURN_SESSION_KEY, None)
    validated = (
        _validated_auth_return(intent, callback_state)
        if intent is not None and callback_state is not None
        else None
    )
    if callback_state is None or validated is None:
        logger.warning('Auth callback rejected because OAuth state did not match the return intent')
        return RedirectResponse(url=_website_fallback_url('/?auth_error=true'))

    frontend, return_to = validated
    provider_errors = request.query_params.getlist('error')
    provider_error = provider_errors[0] if len(provider_errors) == 1 else None
    if len(provider_errors) > 1:
        return _callback_error_redirect(frontend, return_to, 'failed')
    if provider_error:
        cancelled = provider_error == 'access_denied'
        logger.info('OAuth provider returned an error (cancelled=%s)', cancelled)
        return _callback_error_redirect(
            frontend, return_to, 'cancelled' if cancelled else 'failed'
        )

    try:
        # Never log headers, cookies, session dicts, or full URL (may contain code/state)
        logger.info("Auth callback processing")
        
        token = await oauth.google.authorize_access_token(request)
        user = await oauth.google.parse_id_token(token, nonce=request.session.get('nonce'))
        
        # Store user in session
        user_dict = dict(user)
        request.session['user'] = user_dict
        
        logger.info("User authenticated successfully (sub present=%s)", bool(user_dict.get("sub")))
        
        frontend_url = _frontend_origin(frontend)
        if frontend_url is None:
            logger.error('Buddy frontend origin became unavailable during OAuth callback')
            return RedirectResponse(url=_website_fallback_url('/?auth_error=true'))
        redirect_url = frontend_url + return_to
        logger.info("Auth callback redirecting to frontend")
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error("Error during authorization: %s", type(e).__name__, exc_info=True)
        return _callback_error_redirect(frontend, return_to, 'failed')

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
from auth_service import auth_service, User  # noqa: E402

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
