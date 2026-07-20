import firebase_admin
import os
from pathlib import Path
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Get the directory where this file is located
CURRENT_DIR = Path(__file__).parent
SERVER_ROOT = CURRENT_DIR.parent  # DungeonMindServer/ directory

# Load environment variables based on current environment
env = os.getenv('ENVIRONMENT', 'development')
if env == 'production':
    load_dotenv(SERVER_ROOT / '.env.production', override=True)
else:
    load_dotenv(SERVER_ROOT / '.env.development', override=True)

# Get service account path from environment variable with fallback
if env == 'production':
    SERVICE_ACCOUNT_PATH = os.getenv(
            'SERVICE_ACCOUNT_PATH', 
            '/home/user/serviceAccountKey.json'  # Default for Docker container
        )
else:
    # Use absolute path relative to this file's location
    default_path = SERVER_ROOT / 'serviceAccountKey.json'
    SERVICE_ACCOUNT_PATH = os.getenv(
        'SERVICE_ACCOUNT_PATH', 
        str(default_path)  # Absolute path to DungeonMindServer/serviceAccountKey.json
    )


def _init_firebase():
    """
    Initialize Firebase. In CI/test without a key file, leave uninitialized
    so security unit tests can collect without credentials.
    """
    path = Path(SERVICE_ACCOUNT_PATH)
    skip = os.getenv("FIREBASE_SKIP_INIT", "").lower() in ("1", "true", "yes")
    if skip or not path.is_file():
        if not path.is_file():
            logger.warning(
                "Firebase service account missing at %s — deferring init "
                "(set FIREBASE_SKIP_INIT=true for intentional test mode)",
                path,
            )
        return None, None

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(path))
        firebase_admin.initialize_app(cred)
    return firestore.client(), path


_db, _sa_path = _init_firebase()


class _LazyFirestore:
    """Proxy so import succeeds when credentials are absent (CI collection)."""

    def __getattr__(self, name):
        global _db
        if _db is None:
            _db, _ = _init_firebase()
        if _db is None:
            raise RuntimeError(
                "Firestore is not initialized (missing serviceAccountKey.json). "
                "Provide SERVICE_ACCOUNT_PATH or skip Firebase-dependent tests."
            )
        return getattr(_db, name)


db = _db if _db is not None else _LazyFirestore()
