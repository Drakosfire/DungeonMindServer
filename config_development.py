import os
from dotenv import load_dotenv

# Load the .env file
load_dotenv('.env')

CONFIG = {
    'GOOGLE_CLIENT_ID': os.getenv('GOOGLE_CLIENT_ID'),
    'GOOGLE_CLIENT_SECRET': os.getenv('GOOGLE_CLIENT_SECRET'),
    'OAUTH_REDIRECT_URI': 'http://localhost:7860/auth/callback',
    # Other development-specific settings...
}