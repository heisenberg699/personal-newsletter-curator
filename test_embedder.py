# test_embedder.py
# ----------------------------------------------------------
# Step 5 test — run from the project root:
#     python test_embedder.py
# First run downloads the model (~80 MB), so be patient once.
#
# It plants a few stories with KNOWN topics, embeds them, then
# checks that a user interested in "space" gets the space story
# ranked first — proving similarity search actually works.
# ----------------------------------------------------------

from backend.database import SessionLocal, create_tables
from backend.embedder import embed_pending_stories, rank_stories_for_user
from backend.fetcher import save_stories
from backend.models import Story

create_tables()
db = SessionLocal()

print("--- 1. Planting 4 test stories with known topics ---")
test_stories = [
    {"title": "NASA announces new telescope for deep space astronomy",
     "url": "https://example.com/test-space",
     "raw_text": "The new space telescope will observe distant galaxies and exoplanets."},
    {"title": "Indian rupee strengthens against the dollar",
     "url": "https://example.com/test-finance",
     "raw_text": "Currency markets reacted to the central bank's latest policy decision."},
    {"title": "New high-yield wheat variety released for farmers",
     "url": "https://example.com/test-farming",
     "raw_text": "Agricultural scientists developed a drought-resistant wheat strain."},
    {"title": "China and India hold border talks in Delhi",
     "url": "https://example.com/test-geopolitics",
     "raw_text": "Diplomats discussed de-escalation along the disputed boundary."},
]
print("saved:", save_stories(test_stories, "rss", db), "new (0 if you ran this before — fine)")

print("\n--- 2. Embedding all pending stories ---")
count = embed_pending_stories(db)
print(f"embedded {count} stories")
remaining = db.query(Story).filter(Story.embedded == False).count()  # noqa: E712
print(f"stories still pending: {remaining} (should be 0)")

print("\n--- 3. Similarity search: user interested in 'astronomy and space exploration' ---")
results = rank_stories_for_user("astronomy and space exploration", top_n=4)
for story_id, score in results:
    story = db.get(Story, story_id)
    print(f"  {score:.4f}  {story.title[:60]}")
top_title = db.get(Story, results[0][0]).title.lower()
print("PASS" if "space" in top_title or "telescope" in top_title
      else "FAIL — expected the space story first")

print("\n--- 4. Similarity search: 'geopolitics and international relations' ---")
results = rank_stories_for_user("geopolitics and international relations", top_n=4)
for story_id, score in results:
    story = db.get(Story, story_id)
    print(f"  {score:.4f}  {story.title[:60]}")

print("\n--- 5. Empty interests returns nothing ---")
print("result:", rank_stories_for_user(""), "(expect [])")

db.close()
print("\nDone. A chroma_db/ folder should now exist in your project root.")
