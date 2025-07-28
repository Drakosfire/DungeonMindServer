import os
import logging
from starlette.middleware.sessions import SessionMiddleware

logger = logging.getLogger(__name__)

class DungeonMindSessionConfig:
    """
    Centralized session configuration for all DungeonMind applications.
    Ensures consistent session management across the ecosystem.
    """
    
    def __init__(self):
        self.secret_key = os.environ.get("SESSION_SECRET_KEY")
        if not self.secret_key:
            raise ValueError("SESSION_SECRET_KEY environment variable must be set")
        
        # Environment-based configuration
        self.environment = os.environ.get('ENVIRONMENT', 'development')
        self.is_production = self.environment == 'production'
        
        # Detect cross-origin development setup (HTTPS frontend, HTTP backend)
        backend_url = os.environ.get('DUNGEONMIND_API_URL', '')
        frontend_url = os.environ.get('REACT_LANDING_URL', '')
        
        # Check if we're in localhost development
        # Also check if we're running on localhost port 7860 (even if env vars point to dev server)
        is_localhost_dev = (
            not self.is_production and 
            ('localhost' in backend_url or '127.0.0.1' in backend_url or
             'localhost' in frontend_url or '127.0.0.1' in frontend_url or
             os.environ.get('LOCAL_DEVELOPMENT', '').lower() == 'true')
        )
        
        # Check if we're in HTTPS dev environment (both frontend and backend on same HTTPS domain)
        is_https_dev = (
            not self.is_production and 
            backend_url.startswith('https://') and 
            frontend_url.startswith('https://') and
            'dev.dungeonmind.net' in backend_url
        )
        
        self.is_cross_origin_dev = (
            not self.is_production and 
            backend_url.startswith('http://') and 
            frontend_url.startswith('https://')
        )
        
        # Session cookie configuration
        self.cookie_name = "dungeonmind_session"
        self.max_age = 24 * 60 * 60  # 24 hours in seconds
        self.path = "/"
        
        # HTTPS dev environment (like production but with dev domain)
        if is_https_dev:
            logger.info("HTTPS development environment detected (dev.dungeonmind.net)")
            self.https_only = True
            self.same_site = "lax"  # Works well for same-domain HTTPS
            self.domain = "dev.dungeonmind.net"  # Restrict to dev domain
            self.secure = True  # Require HTTPS
        # Cross-origin development needs special cookie settings
        elif self.is_cross_origin_dev or is_localhost_dev:
            if is_localhost_dev:
                logger.warning("Localhost development detected")
            else:
                logger.warning("Cross-origin development detected (HTTPS frontend, HTTP backend)")
            logger.warning("Using permissive cookie settings for development")
            self.https_only = False
            self.same_site = "none"  # Required for cross-origin
            self.domain = None  # Don't restrict domain in cross-origin dev
            self.secure = False  # Allow non-HTTPS cookies in development
        else:
            self.https_only = self.is_production
            self.same_site = "none" if self.is_production else "lax"
            self.domain = ".dungeonmind.net" if self.is_production else None
            self.secure = self.is_production
        
        logger.info(f"Session config initialized for {self.environment} environment")
        logger.info(f"HTTPS dev mode: {is_https_dev}")
        logger.info(f"Cross-origin dev mode: {self.is_cross_origin_dev}")
        logger.info(f"HTTPS only: {self.https_only}, Domain: {self.domain}, SameSite: {self.same_site}")
        logger.info(f"Cookie name: {self.cookie_name}, Max age: {self.max_age}s")
    
    def get_middleware_kwargs(self) -> dict:
        """
        Get the keyword arguments for SessionMiddleware.
        Returns a dictionary suitable for passing to add_middleware().
        """
        config = {
            "secret_key": self.secret_key,
            "session_cookie": self.cookie_name,
            "max_age": self.max_age,
            "path": self.path,
            "https_only": self.https_only,
            "same_site": self.same_site,
        }
        
        # Only add domain in production or HTTPS dev
        if self.domain:
            config["domain"] = self.domain
        
        logger.info(f"Session middleware config: {config}")
        return config
    
    def get_cookie_kwargs(self) -> dict:
        """
        Get the keyword arguments for setting cookies in responses.
        Returns a dictionary suitable for passing to response.set_cookie().
        """
        config = {
            "httponly": True,
            "secure": self.secure,
            "samesite": self.same_site,
        }
        
        # Only add domain in production or HTTPS dev
        if self.domain:
            config["domain"] = self.domain
        
        return config
    
    def add_to_app(self, app):
        """
        Add the standardized session middleware to a FastAPI app.
        
        Args:
            app: FastAPI application instance
        """
        middleware_kwargs = self.get_middleware_kwargs()
        app.add_middleware(SessionMiddleware, **middleware_kwargs)
        
        logger.info("Added standardized session middleware to application")
        logger.debug(f"Session middleware config: {middleware_kwargs}")

# Global session configuration instance
session_config = DungeonMindSessionConfig()

# Convenience function for adding session middleware
def add_session_middleware(app):
    """
    Convenience function to add standardized session middleware to an app.
    
    Args:
        app: FastAPI application instance
    """
    session_config.add_to_app(app) 