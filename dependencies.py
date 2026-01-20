import os

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from ruleslawyer.constants import (
    DEFAULT_RULESLAWYER_DB_NAME,
    RULESLAWYER_DB_NAME_ENV,
    RULESLAWYER_MONGODB_URI_ENV,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

_ruleslawyer_mongo_client = None


async def get_current_user(request: Request):
    user = request.session.get('user')
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_ruleslawyer_db():
    global _ruleslawyer_mongo_client

    try:
        from pymongo import MongoClient
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MongoDB client is not available",
        ) from exc

    mongo_uri = os.environ.get(RULESLAWYER_MONGODB_URI_ENV, "mongodb://localhost:27017")
    db_name = os.environ.get(RULESLAWYER_DB_NAME_ENV, DEFAULT_RULESLAWYER_DB_NAME)

    if _ruleslawyer_mongo_client is None:
        _ruleslawyer_mongo_client = MongoClient(mongo_uri)

    return _ruleslawyer_mongo_client[db_name]