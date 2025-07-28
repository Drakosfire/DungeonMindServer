import os
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import Request, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class User(BaseModel):
    """Standardized user model across all DungeonMind applications"""
    sub: str  # Google user ID
    email: str
    name: str
    picture: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    verified_email: Optional[bool] = None
    
    @property
    def user_id(self) -> str:
        """Standard user ID accessor"""
        return self.sub

class AuthResult(BaseModel):
    """Standard authentication result"""
    authenticated: bool
    user: Optional[User] = None
    error: Optional[str] = None

class AuthService:
    """
    Centralized authentication service for all DungeonMind applications.
    
    This service provides:
    - Standardized user authentication
    - Session validation
    - Cross-service auth utilities
    - Consistent error handling
    """
    
    def __init__(self, dungeonmind_api_url: str = None):
        self.api_url = dungeonmind_api_url or os.environ.get('DUNGEONMIND_API_URL')
        if not self.api_url:
            raise ValueError("DUNGEONMIND_API_URL must be set")
    
    async def get_current_user_from_request(self, request: Request) -> AuthResult:
        """
        Get current authenticated user from FastAPI request.
        Used by DungeonMindServer endpoints.
        """
        try:
            user_data = request.session.get('user')
            if not user_data:
                return AuthResult(authenticated=False, error="No user in session")
            
            # Check session expiration
            exp = request.session.get('exp')
            if exp and datetime.utcnow().timestamp() > exp:
                request.session.clear()
                return AuthResult(authenticated=False, error="Session expired")
            
            user = User(**user_data)
            return AuthResult(authenticated=True, user=user)
            
        except Exception as e:
            logger.error(f"Error getting current user from request: {str(e)}")
            return AuthResult(authenticated=False, error=str(e))
    
    async def get_current_user_from_cookies(self, cookies: Dict[str, str]) -> AuthResult:
        """
        Get current authenticated user from cookies via HTTP request.
        Used by external services like StoreGenerator.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/api/auth/current-user",
                    cookies=cookies,
                    follow_redirects=True,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    user = User(**user_data)
                    return AuthResult(authenticated=True, user=user)
                elif response.status_code == 401:
                    return AuthResult(authenticated=False, error="Not authenticated")
                else:
                    logger.error(f"Unexpected auth response: {response.status_code}")
                    return AuthResult(authenticated=False, error="Authentication service error")
                    
        except httpx.TimeoutException:
            logger.error("Timeout connecting to authentication service")
            return AuthResult(authenticated=False, error="Authentication timeout")
        except Exception as e:
            logger.error(f"Error authenticating user: {str(e)}")
            return AuthResult(authenticated=False, error="Authentication service unavailable")
    
    def get_login_url(self) -> str:
        """Get the standardized login URL"""
        return f"{self.api_url}/api/auth/login"
    
    def get_logout_url(self) -> str:
        """Get the standardized logout URL"""
        return f"{self.api_url}/api/auth/logout"
    
    async def validate_user_for_operation(self, user: Optional[User], required: bool = True) -> Optional[User]:
        """
        Validate user for operations that require authentication.
        
        Args:
            user: User object or None
            required: Whether authentication is required
            
        Returns:
            User object if valid, None if not required, raises HTTPException if required but invalid
        """
        if not user and required:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user
    
    def get_user_id(self, user: Optional[User]) -> Optional[str]:
        """Extract user ID safely"""
        return user.user_id if user else None
    
    async def check_service_health(self) -> bool:
        """Check if the authentication service is available"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_url}/health", timeout=10.0)
                return response.status_code == 200
        except Exception:
            return False

# Global auth service instance
auth_service = AuthService()

# Convenience functions for backward compatibility
async def get_current_user_from_request(request: Request) -> AuthResult:
    """Convenience wrapper for request-based auth"""
    return await auth_service.get_current_user_from_request(request)

async def get_current_user_from_cookies(cookies: Dict[str, str]) -> AuthResult:
    """Convenience wrapper for cookie-based auth"""
    return await auth_service.get_current_user_from_cookies(cookies)

def get_login_url() -> str:
    """Convenience wrapper for login URL"""
    return auth_service.get_login_url()

def get_logout_url() -> str:
    """Convenience wrapper for logout URL"""
    return auth_service.get_logout_url() 