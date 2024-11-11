from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from google.cloud import datastore
from starlette.status import HTTP_302_FOUND
from starlette.middleware.sessions import SessionMiddleware
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="SESSION_SECRET_KEY")

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URI = "https://www.googleapis.com/oauth2/v1/userinfo"

# Initialize Datastore client
datastore_client = datastore.Client()

@app.get("/auth/login")
def login_with_google():
    """Redirect to Google's OAuth endpoint."""
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
    }
    google_auth_url = f"{GOOGLE_AUTH_URI}?{'&'.join(f'{key}={value}' for key, value in params.items())}"
    return RedirectResponse(url=google_auth_url, status_code=HTTP_302_FOUND)

@app.get("/auth/callback")
def google_auth_callback(request: Request, response: Response, code: str):
    """Handle the callback from Google and store user info in a cookie."""
    # Exchange authorization code for tokens
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    token_response = requests.post(GOOGLE_TOKEN_URI, data=token_data).json()
    access_token = token_response.get("access_token")

    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to authenticate with Google.")

    # Fetch user info
    user_info = requests.get(
        GOOGLE_USERINFO_URI, headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    user_id = user_info["id"]
    user_email = user_info["email"]

    # Store user info in Datastore
    key = datastore_client.key("Users", user_id)
    entity = datastore.Entity(key)
    entity.update({"email": user_email})
    datastore_client.put(entity)

    # Store user ID in a cookie
    response.set_cookie(key="user_id", value=user_id, httponly=True)
    return {"message": "User logged in successfully", "user": user_info}
