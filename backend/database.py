# backend/database.py
# ----------------------------------------------------------
# This file sets up the database connection.
# We use SQLite — the whole database lives in one file on disk
# called newsletter.db, created automatically on first run.
# ----------------------------------------------------------

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# The database file will be created in the folder you run the app from.
# "check_same_thread=False" is needed because FastAPI may use
# the same connection from different threads — safe for SQLite here.
DATABASE_URL = "sqlite:///./newsletter.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# SessionLocal is a "factory" — every time we call SessionLocal()
# we get a fresh database session (a short-lived conversation with the DB).
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class for all our table models in models.py.
Base = declarative_base()


def get_db():
    """
    FastAPI dependency.
    Opens a database session for one request, then closes it —
    even if the request raises an error (that's what finally does).
    Usage in a route:  db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """
    Creates all tables defined in models.py if they don't exist yet.
    Called once at app startup from main.py.
    """
    # Import here so all model classes register themselves on Base
    # before we ask SQLAlchemy to create the tables.
    from backend import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
