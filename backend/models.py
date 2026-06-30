# backend/models.py
# ----------------------------------------------------------
# All six database tables, defined as Python classes.
# SQLAlchemy turns each class into a real table in newsletter.db.
# Every column has a comment explaining what it stores.
# ----------------------------------------------------------

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)

from backend.database import Base


def utc_now():
    """Returns the current time in UTC. Used as the default for date columns."""
    return datetime.now(timezone.utc)


# Table: users
# Stores one row per registered user
class User(Base):
    __tablename__ = "users"

    # integer, auto-increment primary key
    id = Column(Integer, primary_key=True, index=True)
    # string, unique, used for login and email delivery
    email = Column(String, unique=True, index=True, nullable=False)
    # string, bcrypt hash — never store the plain password
    password_hash = Column(String, nullable=False)
    # string, free text like "solar energy, Python, pipeline safety"
    interests_text = Column(String, default="")
    # string: "daily" or "weekly" — how often digest emails are sent
    email_cadence = Column(String, default="daily")
    # datetime when the account was created
    created_at = Column(DateTime, default=utc_now)


# Table: sources
# Each row is one RSS feed, subreddit, or HN tag the user has added
class Source(Base):
    __tablename__ = "sources"

    # integer, auto-increment primary key
    id = Column(Integer, primary_key=True, index=True)
    # foreign key → users.id (which user owns this source)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # string: "rss", "reddit", or "hn"
    type = Column(String, nullable=False)
    # string: the RSS URL, subreddit name, or HN search tag
    value = Column(String, nullable=False)
    # datetime when the source was added
    created_at = Column(DateTime, default=utc_now)


# Table: stories
# One row per article fetched from any source
class Story(Base):
    __tablename__ = "stories"

    # integer, auto-increment primary key
    id = Column(Integer, primary_key=True, index=True)
    # string, unique — used to avoid saving the same article twice
    url = Column(String, unique=True, index=True, nullable=False)
    # string, the article headline
    title = Column(String, nullable=False)
    # string, first 2000 chars of the article body (enough for summarising)
    raw_text = Column(String, default="")
    # string: "rss", "reddit", or "hn" — where this story came from
    source_type = Column(String, nullable=False)
    # datetime when we fetched it
    fetched_at = Column(DateTime, default=utc_now)
    # boolean, False until we compute and store its embedding in ChromaDB
    embedded = Column(Boolean, default=False)


# Table: digests
# One digest per user per day
class Digest(Base):
    __tablename__ = "digests"

    # integer, auto-increment primary key
    id = Column(Integer, primary_key=True, index=True)
    # foreign key → users.id (whose digest this is)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # datetime — the date this digest was built
    created_at = Column(DateTime, default=utc_now)


# Table: digest_items
# One row per story in a digest, with the AI-written summary
class DigestItem(Base):
    __tablename__ = "digest_items"

    # integer, auto-increment primary key
    id = Column(Integer, primary_key=True, index=True)
    # foreign key → digests.id (which digest this item belongs to)
    digest_id = Column(Integer, ForeignKey("digests.id"), nullable=False)
    # foreign key → stories.id (which article this item is about)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    # string, 2-sentence summary written by the AI
    summary = Column(String, default="")
    # string, 1 personalised sentence: why this matters to this user
    why_matters = Column(String, default="")
    # float, the similarity score that put this story in the digest
    rank_score = Column(Float, default=0.0)


# Table: clicks
# Records every time a user clicks a story link
class Click(Base):
    __tablename__ = "clicks"

    # integer, auto-increment primary key
    id = Column(Integer, primary_key=True, index=True)
    # foreign key → users.id (who clicked)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # foreign key → stories.id (what they clicked)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=False)
    # datetime of the click
    clicked_at = Column(DateTime, default=utc_now)
