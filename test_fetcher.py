# test_fetcher.py
# ----------------------------------------------------------
# Small test script for Step 4 — run it from the project root:
#     python test_fetcher.py
# It tries all three fetchers and saves the results to the DB,
# printing what happened at each stage.
# ----------------------------------------------------------

from backend.database import SessionLocal, create_tables
from backend.fetcher import fetch_hn, fetch_reddit, fetch_rss, save_stories

# Make sure tables exist even if the API server was never started
create_tables()
db = SessionLocal()

print("\n--- 1. RSS test (Python Insider blog) ---")
rss_stories = fetch_rss("https://feeds.feedburner.com/PythonInsider")
print(f"fetched {len(rss_stories)} stories")
if rss_stories:
    print("first one:", rss_stories[0]["title"])
    print("url:      ", rss_stories[0]["url"])
saved = save_stories(rss_stories, "rss", db)
print(f"saved {saved} new stories to the database")

print("\n--- 2. Hacker News test (tag: 'solar energy') ---")
hn_stories = fetch_hn("solar energy", max_stories=5)
print(f"fetched {len(hn_stories)} stories")
for s in hn_stories[:3]:
    print(" •", s["title"])
saved = save_stories(hn_stories, "hn", db)
print(f"saved {saved} new stories")

print("\n--- 3. Reddit test (r/geopolitics) ---")
print("(needs REDDIT_CLIENT_ID / REDDIT_SECRET in .env — skips gracefully if missing)")
reddit_stories = fetch_reddit("geopolitics", max_posts=5)
print(f"fetched {len(reddit_stories)} stories")
for s in reddit_stories[:3]:
    print(" •", s["title"])
saved = save_stories(reddit_stories, "reddit", db)
print(f"saved {saved} new stories")

print("\n--- 4. Duplicate check ---")
saved_again = save_stories(rss_stories, "rss", db)
print(f"re-saving the same RSS stories saved {saved_again} new rows (should be 0)")

db.close()
print("\nDone. Open newsletter.db in DB Browser and look at the 'stories' table.")
