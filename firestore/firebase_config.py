import firebase_admin
import os
from pathlib import Path
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

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



# Initialize Firebase Admin SDK
cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
firebase_admin.initialize_app(cred)

# Firestore instance
db = firestore.client()
