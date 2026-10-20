from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
import uuid
import logging
from fastapi import Depends, HTTPException, Request
from auth_service import auth_service
from models.session_models import (
    EnhancedGlobalSession, SessionStatus, CardGeneratorSessionState,
    StoreGeneratorSessionState, RulesLawyerSessionState, StatblockGeneratorSessionState,
    GlobalSessionPreferences, CardGeneratorUpdateRequest
)
from models.dungeonmind_objects import StepId

logger = logging.getLogger(__name__)
class EnhancedGlobalSessionManager:
    """Enhanced session manager with CardGenerator support and cross-tool features"""
    
    def __init__(self, session_timeout_hours: int = 24):
        self.sessions: Dict[str, EnhancedGlobalSession] = {}
        self.session_timeout = timedelta(hours=session_timeout_hours)

    def create_session(
        self, 
        user_id: Optional[str] = None, 
        platform: str = 'web',
        request: Optional[Request] = None,
        authenticated_principal_id: Optional[str] = None,
    ) -> str:
        """Create a new enhanced session and return its ID"""
        session_id = str(uuid.uuid4())

        # When a verified principal is supplied, it is the only source of the
        # session's authenticated user identity. `user_id` remains for legacy
        # internal callers but does not authenticate a session by itself.
        if authenticated_principal_id is not None:
            user_id = authenticated_principal_id
        
        # Extract client info if request is provided
        ip_address = None
        user_agent = None
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
        
        session = EnhancedGlobalSession(
            session_id=session_id,
            user_id=user_id,
            platform=platform,
            ip_address=ip_address,
            user_agent=user_agent
        )
        session._authenticated_principal_id = authenticated_principal_id
        
        self.sessions[session_id] = session
        logger.info(f"Created new enhanced session: {session_id} for user: {user_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[EnhancedGlobalSession]:
        """Retrieve a session by ID and update its access time"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            
            # Check if session has expired
            if session.is_expired():
                logger.info(f"Session {session_id} has expired, removing")
                del self.sessions[session_id]
                return None
            
            session.update_access_time()
            return session
        return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a specific session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Deleted session: {session_id}")
            return True
        return False

    async def update_cardgenerator_state(
        self, 
        session_id: str, 
        state_updates: Dict[str, Any]
    ) -> bool:
        """Update CardGenerator state within a session"""
        session = self.get_session(session_id)
        if not session:
            logger.warning(f"Session {session_id} not found for CardGenerator update")
            return False
            
        # Initialize CardGenerator state if it doesn't exist
        if not session.cardgenerator:
            session.cardgenerator = CardGeneratorSessionState()
            
        # Apply updates to CardGenerator state
        for key, value in state_updates.items():
            if hasattr(session.cardgenerator, key):
                setattr(session.cardgenerator, key, value)
                
        session.cardgenerator.last_updated = datetime.now()
        session.update_access_time()
        
        # If an item is being worked on, add to recently viewed
        if session.cardgenerator.active_item_id:
            session.add_to_recently_viewed(session.cardgenerator.active_item_id)
            
        logger.debug(f"Updated CardGenerator state for session {session_id}")
        return True

    async def update_tool_state(
        self, 
        session_id: str, 
        tool_name: str, 
        state_updates: Dict[str, Any]
    ) -> bool:
        """Generic method to update any tool's state"""
        if tool_name == 'cardgenerator':
            return await self.update_cardgenerator_state(session_id, state_updates)
        
        # Add other tools as they're implemented
        session = self.get_session(session_id)
        if not session:
            return False
            
        if tool_name == 'storegenerator':
            if not session.storegenerator:
                session.storegenerator = StoreGeneratorSessionState()
            # Apply updates (placeholder implementation)
            session.storegenerator.last_updated = datetime.now()
        elif tool_name == 'ruleslawyer':
            if not session.ruleslawyer:
                session.ruleslawyer = RulesLawyerSessionState()
            session.ruleslawyer.last_updated = datetime.now()
        elif tool_name == 'statblockgenerator':
            if not session.statblockgenerator:
                session.statblockgenerator = StatblockGeneratorSessionState()
            session.statblockgenerator.last_updated = datetime.now()
        else:
            logger.warning(f"Unknown tool: {tool_name}")
            return False
            
        session.update_access_time()
        return True

    def cleanup_old_sessions(self):
        """Remove expired sessions"""
        current_time = datetime.now()
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            if session.is_expired():
                expired_sessions.append(session_id)
                
        for session_id in expired_sessions:
            logger.info(f"Cleaning up expired session: {session_id}")
            del self.sessions[session_id]
            
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")

    def get_session_status(self, session: EnhancedGlobalSession) -> SessionStatus:
        """Get comprehensive status of a session"""
        return SessionStatus(
            active=not session.is_expired(),
            expires_at=session.expires_at,
            last_accessed=session.last_accessed,
            current_tool=session.current_tool,
            active_world_id=session.active_world_id,
            active_project_id=session.active_project_id,
            has_cardgenerator=session.cardgenerator is not None,
            has_storegenerator=session.storegenerator is not None,
            has_ruleslawyer=session.ruleslawyer is not None,
            has_statblockgenerator=session.statblockgenerator is not None,
            clipboard_count=len(session.clipboard),
            recently_viewed_count=len(session.recently_viewed),
            pinned_objects_count=len(session.pinned_objects)
        )

    def get_user_sessions(self, user_id: str) -> List[EnhancedGlobalSession]:
        """Get all active sessions for a user"""
        user_sessions = []
        for session in self.sessions.values():
            if session.user_id == user_id and not session.is_expired():
                user_sessions.append(session)
        return user_sessions

    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about current sessions"""
        total_sessions = len(self.sessions)
        authenticated_sessions = sum(1 for s in self.sessions.values() if s.user_id)
        
        tool_usage = {
            'cardgenerator': sum(1 for s in self.sessions.values() if s.cardgenerator),
            'storegenerator': sum(1 for s in self.sessions.values() if s.storegenerator),
            'ruleslawyer': sum(1 for s in self.sessions.values() if s.ruleslawyer),
            'statblockgenerator': sum(1 for s in self.sessions.values() if s.statblockgenerator)
        }
        
        return {
            'total_sessions': total_sessions,
            'authenticated_sessions': authenticated_sessions,
            'anonymous_sessions': total_sessions - authenticated_sessions,
            'tool_usage': tool_usage
        }

# Create global session manager instance
session_manager = EnhancedGlobalSessionManager()

async def get_session(session_id: str = None, request: Request = None) -> tuple[EnhancedGlobalSession, str]:
    """Dependency for getting or creating a session"""
    if not session_id and request:
        session_id = request.cookies.get("dungeonmind_session_id")

    if not session_id:
        session_id = session_manager.create_session(request=request)
    
    session = await get_existing_session(session_id, request)
    if not session:
        session_id = session_manager.create_session(request=request)
        session = session_manager.get_session(session_id)

    return session, session_id


async def get_existing_session(
    session_id: str, request: Request
) -> Optional[EnhancedGlobalSession]:
    """Resolve an existing session while enforcing verified ownership."""
    # Inspect the candidate without refreshing its access timestamp: a denied
    # principal must not mutate even that small piece of session state.
    session = session_manager.sessions.get(session_id)
    if session and session.is_expired():
        session_manager.delete_session(session_id)
        session = None
    if session and session._authenticated_principal_id is not None:
        # A verified session is bound to the principal that created it. Session
        # IDs and cookies are locators, not credentials. Markerless legacy
        # sessions intentionally retain bearer compatibility below.
        if request is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        auth_result = await auth_service.get_current_user_from_request(request)
        current_user = auth_result.user if auth_result.authenticated else None
        if current_user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        if (
            session._authenticated_principal_id != current_user.user_id
            or session.user_id != current_user.user_id
        ):
            raise HTTPException(
                status_code=403,
                detail="Session is not associated with the authenticated user",
            )
    if session:
        session = session_manager.get_session(session_id)
    return session

async def get_authenticated_session(session_id: str = None, request: Request = None) -> tuple[EnhancedGlobalSession, str]:
    """Resolve a session only when its verified DMS principal matches the caller."""
    if request is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    auth_result = await auth_service.get_current_user_from_request(request)
    current_user = auth_result.user if auth_result.authenticated else None
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Resolve the requested ID without allowing get_session's compatibility
    # fallback to hide a cross-principal session-ID collision.
    requested_id = session_id or request.cookies.get("dungeonmind_session_id")
    session, session_id = await get_session(requested_id, request)

    if (
        session._authenticated_principal_id != current_user.user_id
        or session.user_id != current_user.user_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Session is not associated with the authenticated user",
        )
    
    return session, session_id

# Export the session manager instance and dependencies
__all__ = [
    'session_manager', 
    'get_session', 
    'get_existing_session',
    'get_authenticated_session',
    'EnhancedGlobalSession', 
    'SessionStatus',
    'EnhancedGlobalSessionManager'
]
