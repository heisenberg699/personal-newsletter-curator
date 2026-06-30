# backend/embedder.py
# ----------------------------------------------------------
# The "meaning" engine of the app.
#
# An embedding is a list of 384 numbers that captures what a text
# MEANS. Texts about similar topics get similar numbers, so we can
# find "stories about things this user cares about" with maths
# instead of keyword matching.
#
# Two jobs:
#   1. embed_pending_stories — compute embeddings for new stories
#      and store them in ChromaDB (a small vector database on disk)
#   2. rank_stories_for_user — given a user's interests text,
#      return the story ids that are closest in meaning
# ----------------------------------------------------------

import chromadb
from sqlalchemy.orm import Session

from backend.models import Story

# ---- lazy singletons -------------------------------------
# The model (~80 MB) takes a few seconds to load, so we load it
# ONCE the first time it's needed and reuse it afterwards.
# Same for the ChromaDB client.

_model = None
_collection = None


def get_model():
    """Loads the sentence-transformer model once, then reuses it."""
    global _model
    if _model is None:
        # Import here so the API server can start fast even
        # before this heavy library is ever needed.
        from sentence_transformers import SentenceTransformer

        print("[embedder] loading model all-MiniLM-L6-v2 (first time only)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def get_collection():
    """
    Opens (or creates) the ChromaDB collection where story
    embeddings live. PersistentClient saves to the chroma_db/
    folder so embeddings survive restarts.
    """
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path="./chroma_db")
        _collection = client.get_or_create_collection(
            name="stories",
            # cosine distance = standard choice for comparing text meanings
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


# ---- job 1: embed new stories -----------------------------

def embed_pending_stories(db: Session, batch_size: int = 64) -> int:
    """
    Finds all stories with embedded=False, computes their embeddings
    (title + first part of the text), stores them in ChromaDB,
    then marks them embedded=True in SQLite.
    Returns how many stories were embedded.

    ChromaDB caps how many items can be added in a single call
    (commonly 166), so we add in chunks to stay safely under that.
    """
    pending = db.query(Story).filter(Story.embedded == False).all()  # noqa: E712
    if not pending:
        return 0

    model = get_model()
    collection = get_collection()

    # Embed the title plus a slice of the body — the title carries
    # most of the meaning, the body adds context.
    texts = [f"{s.title}. {s.raw_text[:500]}" for s in pending]

    # encode() is much faster on a list than one-by-one
    vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=False)

    # ChromaDB rejects very large single adds. Split into safe chunks.
    CHROMA_MAX_ADD = 150  # stay comfortably below Chroma's ~166 ceiling
    for start in range(0, len(pending), CHROMA_MAX_ADD):
        chunk = pending[start:start + CHROMA_MAX_ADD]
        chunk_vectors = vectors[start:start + CHROMA_MAX_ADD]
        collection.add(
            # ChromaDB wants string ids; we reuse the SQLite story id
            ids=[str(s.id) for s in chunk],
            embeddings=[v.tolist() for v in chunk_vectors],
            # metadata lets us filter later if we ever want to
            metadatas=[{"source_type": s.source_type} for s in chunk],
        )

    # Mark them done in SQLite so we never embed twice
    for s in pending:
        s.embedded = True
    db.commit()

    return len(pending)


# ---- job 2: find stories matching a user's interests ------

def rank_stories_for_user(interests_text: str, top_n: int = 10) -> list[tuple[int, float]]:
    """
    Embeds the user's interests text and asks ChromaDB:
    "which stored stories are closest in meaning?"

    Returns a list of (story_id, similarity_score) pairs,
    best match first. similarity_score is between 0 and 1,
    where 1 = identical meaning.
    """
    if not interests_text.strip():
        return []

    collection = get_collection()

    # An empty collection would make query() crash
    if collection.count() == 0:
        return []

    model = get_model()
    query_vector = model.encode([interests_text])[0].tolist()

    results = collection.query(
        query_embeddings=[query_vector],
        # can't ask for more results than stories stored
        n_results=min(top_n, collection.count()),
    )

    # ChromaDB returns cosine DISTANCE (0 = identical, 2 = opposite).
    # similarity = 1 - distance gives the friendlier "higher is better".
    ids = results["ids"][0]
    distances = results["distances"][0]

    return [(int(story_id), round(1 - dist, 4)) for story_id, dist in zip(ids, distances)]
