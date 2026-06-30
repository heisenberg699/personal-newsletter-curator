# backend/main.py
# ----------------------------------------------------------
# The FastAPI app starts here.
# Step 1: only one test route (/health) + create tables on startup.
# Routes for auth, sources, digests etc. will be added in later steps.
# ----------------------------------------------------------

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.auth import (
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.database import create_tables, get_db
from backend.digest_builder import build_digest_for_user
from backend.scheduler import run_now, start_scheduler, stop_scheduler
from backend.models import Click, Digest, DigestItem, Source, Story, User
from backend.schemas import (
    DigestItemResponse,
    DigestResponse,
    LoginRequest,
    SignupRequest,
    SourceCreate,
    SourceResponse,
    TokenResponse,
    UserResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- startup ----
    # Create all database tables if they don't exist yet.
    create_tables()
    print("Database tables created (newsletter.db)")
    # Start the background scheduler (daily digest at 07:00).
    start_scheduler()
    yield
    # ---- shutdown ----
    # Stop the scheduler's background thread cleanly.
    stop_scheduler()


app = FastAPI(title="Personal Newsletter Curator", lifespan=lifespan)


@app.get("/health")
def health_check():
    """Simple test route — if this returns ok, the server is alive."""
    return {"status": "ok"}


# ----------------------------------------------------------
# STEP 2 — Auth routes
# ----------------------------------------------------------

@app.post("/signup", response_model=TokenResponse)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    """
    Creates a new user and returns a login token immediately,
    so the user doesn't have to log in right after signing up.
    """
    # Refuse duplicate emails — email is our unique login identity.
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Basic sanity checks
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if body.email_cadence not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="email_cadence must be 'daily' or 'weekly'")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),  # never store the plain password
        interests_text=body.interests_text,
        email_cadence=body.email_cadence,
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # reloads the row so user.id is filled in

    return TokenResponse(access_token=create_token(user.id))


@app.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Checks email + password and returns a token.
    Uses the standard OAuth2 form (fields named 'username' and 'password')
    so the green Authorize button on /docs works out of the box.
    Our 'username' is simply the email address.
    """
    user = db.query(User).filter(User.email == form.username).first()

    # Same error for "no such user" and "wrong password" —
    # we don't want to tell attackers which emails exist.
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    return TokenResponse(access_token=create_token(user.id))


@app.post("/login/json", response_model=TokenResponse)
def login_json(body: LoginRequest, db: Session = Depends(get_db)):
    """
    Same as /login but accepts JSON: { "email": ..., "password": ... }.
    The Streamlit frontend (Step 11) will use this one — JSON is
    easier to send with requests.post() than form data.
    """
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return TokenResponse(access_token=create_token(user.id))


@app.get("/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)):
    """
    Test route for the token: returns the logged-in user's own details.
    If the token is missing/expired/forged, you get 401 instead.
    """
    return current_user


# ----------------------------------------------------------
# STEP 3 — Source management routes
# A "source" is one place we fetch articles from:
#   type "rss"    → value is a feed URL
#   type "reddit" → value is a subreddit name (e.g. "python")
#   type "hn"     → value is a Hacker News search tag (e.g. "solar")
# ----------------------------------------------------------

@app.post("/sources", response_model=SourceResponse)
def add_source(
    body: SourceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Saves one new source for the logged-in user."""
    # Only the three known types are allowed
    if body.type not in ("rss", "reddit", "hn"):
        raise HTTPException(status_code=400, detail="type must be 'rss', 'reddit', or 'hn'")

    # Clean up the value a little (people often paste extra spaces,
    # or "r/python" instead of just "python")
    value = body.value.strip()
    if body.type == "reddit" and value.lower().startswith("r/"):
        value = value[2:]
    if value == "":
        raise HTTPException(status_code=400, detail="value cannot be empty")

    # Don't save the exact same source twice for the same user
    duplicate = (
        db.query(Source)
        .filter(
            Source.user_id == current_user.id,
            Source.type == body.type,
            Source.value == value,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="You already added this source")

    source = Source(user_id=current_user.id, type=body.type, value=value)
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@app.get("/sources", response_model=list[SourceResponse])
def list_sources(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all sources belonging to the logged-in user."""
    return db.query(Source).filter(Source.user_id == current_user.id).all()


@app.delete("/sources/{source_id}")
def delete_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Removes one source by id.
    The user_id filter is important — it stops user A
    from deleting user B's sources by guessing ids.
    """
    source = (
        db.query(Source)
        .filter(Source.id == source_id, Source.user_id == current_user.id)
        .first()
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    db.delete(source)
    db.commit()
    return {"deleted": source_id}


# ----------------------------------------------------------
# STEP 7 — Digest routes
# ----------------------------------------------------------

def _digest_to_response(digest: Digest, db: Session) -> DigestResponse:
    """Helper: turn a Digest row + its items into the API response shape."""
    items = []
    for item in db.query(DigestItem).filter(DigestItem.digest_id == digest.id).all():
        story = db.get(Story, item.story_id)
        if story is None:
            continue
        items.append(DigestItemResponse(
            story_id=story.id,
            title=story.title,
            url=story.url,
            summary=item.summary,
            why_matters=item.why_matters,
            rank_score=item.rank_score,
        ))
    # Best-ranked stories first
    items.sort(key=lambda x: x.rank_score, reverse=True)
    return DigestResponse(
        id=digest.id,
        created_at=str(digest.created_at),
        items=items,
    )


@app.post("/digests/build", response_model=DigestResponse)
def build_digest(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Runs the whole pipeline now and returns the freshly built digest.
    This can take a few seconds (it calls the AI for each story).
    """
    digest_id = build_digest_for_user(current_user, db)
    if digest_id is None:
        raise HTTPException(
            status_code=400,
            detail="Could not build a digest — add some sources and interests first.",
        )
    digest = db.get(Digest, digest_id)
    return _digest_to_response(digest, db)


@app.get("/digests", response_model=list[DigestResponse])
def list_digests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all of the user's digests, newest first."""
    digests = (
        db.query(Digest)
        .filter(Digest.user_id == current_user.id)
        .order_by(Digest.created_at.desc())
        .all()
    )
    return [_digest_to_response(d, db) for d in digests]


@app.get("/digests/latest", response_model=DigestResponse)
def latest_digest(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the user's most recent digest (handy for the frontend home page)."""
    digest = (
        db.query(Digest)
        .filter(Digest.user_id == current_user.id)
        .order_by(Digest.created_at.desc())
        .first()
    )
    if digest is None:
        raise HTTPException(status_code=404, detail="No digests yet — build one first.")
    return _digest_to_response(digest, db)


# ----------------------------------------------------------
# STEP 8 — Scheduler test route
# ----------------------------------------------------------

@app.post("/admin/run-scheduler-now")
def run_scheduler_now(current_user: User = Depends(get_current_user)):
    """
    Manually fires the daily job right now — the same code path the
    07:00 scheduler uses — so you can test it without waiting.
    Builds a digest for EVERY user (that's what the real job does).
    """
    run_now()
    return {"status": "scheduler job ran — check your digests and the server log"}


# ----------------------------------------------------------
# STEP 9 — Email a digest on demand
# ----------------------------------------------------------

@app.post("/digests/latest/email")
def email_latest_digest(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Emails the user's most recent digest to their own address.
    Useful to test email delivery without rebuilding.
    """
    digest = (
        db.query(Digest)
        .filter(Digest.user_id == current_user.id)
        .order_by(Digest.created_at.desc())
        .first()
    )
    if digest is None:
        raise HTTPException(status_code=404, detail="No digests yet — build one first.")

    from backend.emailer import send_digest_email
    sent = send_digest_email(current_user, digest, db)
    if not sent:
        raise HTTPException(
            status_code=400,
            detail="Email not sent — check GMAIL_ADDRESS / GMAIL_APP_PASSWORD in .env "
                   "and the server log.",
        )
    return {"status": f"digest emailed to {current_user.email}"}


# ----------------------------------------------------------
# STEP 10 — Click tracking
# The links in the email point here. We record the click, then
# bounce the reader on to the real article. No login needed —
# email clients can't send auth headers — so the user_id and
# story_id travel in the URL instead.
# ----------------------------------------------------------

@app.get("/click")
def track_click(
    user_id: int,
    story_id: int,
    redirect: str,
    db: Session = Depends(get_db),
):
    """
    Records one click, then 307-redirects the browser to the article.
    Even if saving the click fails, we still redirect — the reader
    must always reach the article they clicked.
    """
    try:
        # Only record if both the user and story really exist,
        # so bad/old links don't create junk rows.
        user = db.get(User, user_id)
        story = db.get(Story, story_id)
        if user and story:
            db.add(Click(user_id=user_id, story_id=story_id))
            db.commit()
    except Exception as e:
        print(f"[click] failed to record click: {e}")

    # Send the reader to the actual article.
    return RedirectResponse(url=redirect)


@app.get("/stats")
def my_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Simple engagement stats for the logged-in user:
    total clicks, and their most-clicked stories.
    The frontend (Step 11) can show this on a dashboard.
    """
    total_clicks = db.query(Click).filter(Click.user_id == current_user.id).count()

    # Count clicks per story for this user
    rows = (
        db.query(Click.story_id)
        .filter(Click.user_id == current_user.id)
        .all()
    )
    counts = {}
    for (story_id,) in rows:
        counts[story_id] = counts.get(story_id, 0) + 1

    # Build a small "top clicked" list, most clicks first
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
    top_stories = []
    for story_id, n in top:
        story = db.get(Story, story_id)
        if story:
            top_stories.append({
                "story_id": story_id,
                "title": story.title,
                "url": story.url,
                "clicks": n,
            })

    return {
        "total_clicks": total_clicks,
        "top_stories": top_stories,
    }
