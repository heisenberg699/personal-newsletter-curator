# backend/schemas.py
# ----------------------------------------------------------
# Pydantic models = the "shapes" of data going in and out of the API.
# FastAPI uses these to validate requests and document /docs automatically.
# More shapes will be added here in later steps (sources, digests, ...).
# ----------------------------------------------------------

from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    """Body of POST /signup"""
    email: EmailStr            # EmailStr rejects things that aren't valid emails
    password: str
    interests_text: str = ""   # e.g. "solar energy, Python, pipeline safety"
    email_cadence: str = "daily"   # "daily" or "weekly"


class LoginRequest(BaseModel):
    """Body of POST /login"""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """What /signup and /login return"""
    access_token: str
    token_type: str = "bearer"   # standard name browsers/tools expect


class UserResponse(BaseModel):
    """Safe view of a user — never includes the password hash."""
    id: int
    email: str
    interests_text: str
    email_cadence: str

    class Config:
        from_attributes = True   # lets Pydantic read directly from a SQLAlchemy object


class UpdateInterestsRequest(BaseModel):
    """Body of PATCH /me/interests"""
    interests_text: str


class SourceCreate(BaseModel):
    """Body of POST /sources"""
    type: str    # "rss", "reddit", or "hn"
    value: str   # the RSS URL, subreddit name, or HN search tag


class SourceResponse(BaseModel):
    """What GET /sources returns (one per row)"""
    id: int
    type: str
    value: str

    class Config:
        from_attributes = True


class DigestItemResponse(BaseModel):
    """One story inside a digest, with its AI summary."""
    story_id: int
    title: str
    url: str
    summary: str
    why_matters: str
    rank_score: float


class DigestResponse(BaseModel):
    """A full digest: when it was made + its list of items."""
    id: int
    created_at: str
    items: list[DigestItemResponse]
