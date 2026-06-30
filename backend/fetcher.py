# backend/fetcher.py
# ----------------------------------------------------------
# Pulls articles from the three source types and saves them.
# Every fetch function returns the SAME shape:
#     a list of dicts with keys: title, url, raw_text
# so the rest of the app never cares where a story came from.
#
# All functions are wrapped in try/except — a dead RSS feed or
# a Reddit outage must never crash the daily digest job.
# ----------------------------------------------------------

import os

import feedparser
import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from backend.models import Story

load_dotenv()

# How many characters of article body we keep — enough for the AI
# to summarise, small enough to keep the database light.
MAX_TEXT_CHARS = 2000


def fetch_rss(url: str, max_entries: int = 30) -> list[dict]:
    """
    Reads an RSS feed URL using feedparser.
    Returns a list of dicts, each with keys: title, url, raw_text.
    raw_text = first 2000 chars of the entry's summary/description.

    Some feeds publish their whole archive (hundreds of entries) in
    one response, which would flood the database — so we keep only
    the most recent `max_entries`.
    """
    stories = []
    try:
        feed = feedparser.parse(url)

        # feed.entries is a list of articles in the feed (newest first).
        # Slice to the most recent ones so a huge archive feed can't
        # dump hundreds of old posts into our database at once.
        for entry in feed.entries[:max_entries]:
            # Some feeds call the body "summary", others "description".
            # .get() returns "" if the field is missing instead of crashing.
            body = entry.get("summary", "") or entry.get("description", "")

            stories.append({
                "title": entry.get("title", "(no title)"),
                "url": entry.get("link", ""),
                "raw_text": body[:MAX_TEXT_CHARS],
            })
    except Exception as e:
        # Bad URL, network down, malformed XML — log and move on.
        print(f"[fetcher] RSS failed for {url}: {e}")

    return stories


def fetch_hn(tag: str, max_stories: int = 20) -> list[dict]:
    """
    Searches Hacker News through the free Algolia API (no key needed).
    Example request:
    https://hn.algolia.com/api/v1/search?query=solar&tags=story&hitsPerPage=20
    """
    stories = []
    try:
        response = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": tag, "tags": "story", "hitsPerPage": max_stories},
            timeout=10,  # don't hang forever if the API is slow
        )
        response.raise_for_status()  # turns HTTP errors (404, 500...) into exceptions

        for hit in response.json().get("hits", []):
            # Some HN posts are text-only ("Ask HN") and have no external URL.
            # For those, link to the HN discussion page instead.
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"

            stories.append({
                "title": hit.get("title", "(no title)"),
                "url": url,
                # story_text exists only for text posts; usually empty
                "raw_text": (hit.get("story_text") or "")[:MAX_TEXT_CHARS],
            })
    except Exception as e:
        print(f"[fetcher] HN failed for tag '{tag}': {e}")

    return stories


def fetch_reddit(subreddit: str, max_posts: int = 20) -> list[dict]:
    """
    Fetches top posts of the last 24 hours from r/{subreddit} using praw.
    Needs REDDIT_CLIENT_ID, REDDIT_SECRET, REDDIT_USER_AGENT in .env.
    """
    stories = []
    try:
        # Import praw here (not at the top) so the rest of the app
        # still runs even if praw isn't installed yet.
        import praw

        reddit = praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_SECRET"],
            user_agent=os.environ.get("REDDIT_USER_AGENT", "newsletter_curator/1.0"),
        )

        # "top" of the last "day" = the 20 best posts of the last 24 hours
        for post in reddit.subreddit(subreddit).top(time_filter="day", limit=max_posts):
            stories.append({
                "title": post.title,
                "url": post.url,
                # selftext = the body of a text post; link posts have none
                "raw_text": (post.selftext or "")[:MAX_TEXT_CHARS],
            })
    except KeyError as e:
        print(f"[fetcher] Reddit skipped — missing {e} in .env")
    except Exception as e:
        print(f"[fetcher] Reddit failed for r/{subreddit}: {e}")

    return stories


def save_stories(stories: list[dict], source_type: str, db: Session) -> int:
    """
    Saves a list of fetched stories into the database.
    Skips any story whose URL already exists (prevents duplicates).
    Returns how many NEW stories were saved.
    """
    new_count = 0

    for s in stories:
        # A story without a URL can't be deduplicated or clicked — skip it.
        if not s.get("url"):
            continue

        # The duplicate check from the build prompt:
        exists = db.query(Story).filter_by(url=s["url"]).first()
        if exists:
            continue

        db.add(Story(
            url=s["url"],
            title=s["title"],
            raw_text=s.get("raw_text", ""),
            source_type=source_type,
            embedded=False,   # Step 5 will compute the embedding later
        ))
        new_count += 1

    db.commit()
    return new_count
