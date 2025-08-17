import firebase_admin
import os
from firebase_admin import credentials, firestore

# Get service account path from environment variable with fallback
SERVICE_ACCOUNT_PATH = os.getenv(
    'SERVICE_ACCOUNT_PATH', 
    '/home/user/serviceAccountKey.json'  # Default for Docker container
)

# Initialize Firebase Admin SDK
cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
firebase_admin.initialize_app(cred)

# Firestore instance
db = firestore.client()
