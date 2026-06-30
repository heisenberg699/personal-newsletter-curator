# backend/digest_builder.py
# ----------------------------------------------------------
# The keystone. One function — build_digest_for_user — runs the
# whole pipeline for a single user and saves a finished digest:
#
#   1. FETCH   each of the user's sources (RSS / HN / Reddit)
#   2. SAVE    new stories to the DB (skipping duplicates)
#   3. EMBED   any stories that don't have embeddings yet
#   4. RANK    all stored stories against the user's interests
#   5. SUMMARISE the top N with Groq (summary + why_matters)
#   6. SAVE    a Digest row + one DigestItem per chosen story
#
# Returns the new digest's id, or None if there was nothing to build.
# ----------------------------------------------------------

from sqlalchemy.orm import Session

from backend.embedder import embed_pending_stories, rank_stories_for_user
from backend.fetcher import fetch_hn, fetch_reddit, fetch_rss, save_stories
from backend.models import Digest, DigestItem, Source, Story, User
from backend.summarizer import summarize_story

# How many stories end up in one digest
TOP_N = 8


def build_digest_for_user(user: User, db: Session) -> int | None:
    """Runs the full pipeline for one user. Returns the new digest id or None."""

    print(f"\n[digest] building for {user.email} ...")

    # ---- 1 & 2: fetch every source, save new stories ----
    sources = db.query(Source).filter(Source.user_id == user.id).all()
    if not sources:
        print("[digest] user has no sources — nothing to build.")
        return None

    total_new = 0
    for src in sources:
        if src.type == "rss":
            fetched = fetch_rss(src.value)
        elif src.type == "hn":
            fetched = fetch_hn(src.value)
        elif src.type == "reddit":
            fetched = fetch_reddit(src.value)
        else:
            fetched = []

        new = save_stories(fetched, src.type, db)
        total_new += new
        print(f"[digest]   {src.type}:{src.value} -> {len(fetched)} fetched, {new} new")

    # ---- 3: embed anything new ----
    embedded = embed_pending_stories(db)
    print(f"[digest] embedded {embedded} new stories")

    # ---- 4: rank all stored stories against this user's interests ----
    ranked = rank_stories_for_user(user.interests_text, top_n=TOP_N)
    if not ranked:
        print("[digest] nothing to rank (no stories or empty interests).")
        return None

    # ---- 5 & 6: summarise the winners and save the digest ----
    digest = Digest(user_id=user.id)
    db.add(digest)
    db.flush()  # gives digest.id without a full commit yet

    for story_id, score in ranked:
        story = db.get(Story, story_id)
        if story is None:
            continue

        ai = summarize_story(story.title, story.raw_text, user.interests_text)

        db.add(DigestItem(
            digest_id=digest.id,
            story_id=story.id,
            summary=ai["summary"],
            why_matters=ai["why_matters"],
            rank_score=score,
        ))
        print(f"[digest]   + ({score:.3f}) {story.title[:55]}")

    db.commit()
    print(f"[digest] done — digest id {digest.id} with {len(ranked)} items")

    # ---- 7: email it (skips gracefully if Gmail isn't configured) ----
    try:
        from backend.emailer import send_digest_email
        send_digest_email(user, digest, db)
    except Exception as e:
        print(f"[digest] email step failed (digest still saved): {e}")

    return digest.id


def build_digests_for_all_users(db: Session) -> dict:
    """
    Builds a digest for every user. Used by the scheduler in Step 8.
    Returns a small report: {user_email: digest_id_or_None}.
    """
    report = {}
    for user in db.query(User).all():
        try:
            report[user.email] = build_digest_for_user(user, db)
        except Exception as e:
            # One user's failure must not stop everyone else's digest
            print(f"[digest] FAILED for {user.email}: {e}")
            report[user.email] = None
    return report
