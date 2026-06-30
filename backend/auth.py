# backend/auth.py
# ----------------------------------------------------------
# Everything related to passwords and login tokens.
# Four jobs only:
#   1. hash_password      — turn a plain password into a safe bcrypt hash
#   2. verify_password    — check a plain password against a stored hash
#   3. create_token       — make a JWT string that proves "this is user X"
#   4. get_current_user   — read the token on each request, return the user
# ----------------------------------------------------------

import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User

# Read variables from the .env file into the environment
load_dotenv()

# The secret used to sign tokens. If someone knows this, they can
# forge tokens — so it lives in .env, never in code or git.
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_DAYS = 7  # one login lasts a week — fine for a student project

# passlib handles bcrypt for us. "deprecated=auto" just means
# it will upgrade old hash formats automatically if we ever change schemes.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Tells FastAPI: "the token arrives in the Authorization: Bearer <token> header,
# and the login form lives at /login" (this powers the Authorize button in /docs).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def hash_password(plain: str) -> str:
    """Turns 'mypassword' into a bcrypt hash like '$2b$12$...'. One-way — cannot be reversed."""
    return pwd_context.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    """Returns True if the plain password matches the stored hash."""
    return pwd_context.verify(plain, password_hash)


def create_token(user_id: int) -> str:
    """
    Builds a JWT containing the user's id ("sub" = subject)
    and an expiry time 7 days from now, signed with our secret.
    """
    expires = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRY_DAYS)
    payload = {
        "sub": str(user_id),   # JWT standard wants "sub" to be a string
        "exp": expires,        # the library converts this to a unix timestamp
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Used by protected routes via Depends(get_current_user).
    Reads the Bearer token, checks the signature and expiry,
    looks up the user in the database, and returns the User object.
    Raises 401 if anything is wrong.
    """
    credentials_error = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except JWTError:
        # Covers bad signature, expired token, malformed token
        raise credentials_error

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_error

    return user
