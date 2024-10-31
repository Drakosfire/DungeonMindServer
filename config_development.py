import os
from dotenv import load_dotenv

# Load the .env file
load_dotenv('.env')

CONFIG = {
    'GOOGLE_CLIENT_ID': os.getenv('GOOGLE_CLIENT_ID'),
    'GOOGLE_CLIENT_SECRET': os.getenv('GOOGLE_CLIENT_SECRET'),
    'OAUTH_REDIRECT_URI': 'https://localhost:7860/auth/callback',
    'CLOUDFLARE_ACCOUNT_ID': os.getenv('CLOUDFLARE_ACCOUNT_ID'),
    'CLOUDFLARE_IMAGES_API_TOKEN': os.getenv('CLOUDFLARE_IMAGES_API_TOKEN'),
    # Other development-specific settings...
}