# 📰 Personal Newsletter Curator

An AI-powered app that reads your chosen sources (RSS feeds, Hacker News,
Reddit), ranks every story against your stated interests using semantic
embeddings, writes a personalised summary of each with an LLM, and emails
you a daily digest — with click tracking to see what you actually read.

## What it does

1. **Fetches** articles from RSS feeds, Hacker News, and subreddits you add
2. **Embeds** each story with sentence-transformers and stores vectors in ChromaDB
3. **Ranks** stories by semantic similarity to your interests
4. **Summarises** the top stories with Groq (Llama 3) — 2 sentences + a
   personalised "why this matters to you" line
5. **Builds** a digest and **emails** it via Gmail (HTML, formatted)
6. **Schedules** the whole thing to run automatically every morning at 07:00
7. **Tracks clicks** so you can see your most-read stories

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, SQLite
- **Auth:** JWT (python-jose) + bcrypt password hashing
- **AI:** sentence-transformers (all-MiniLM-L6-v2), ChromaDB, Groq (Llama 3.1)
- **Sources:** feedparser (RSS), praw (Reddit), Algolia API (Hacker News)
- **Scheduling:** APScheduler
- **Email:** Gmail SMTP (SSL)
- **Frontend:** Streamlit

## Setup

1. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate          # Windows
   source venv/bin/activate       # Mac/Linux
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your keys:
   - `JWT_SECRET` — run `python -c "import secrets; print(secrets.token_hex(32))"`
   - `GROQ_API_KEY` — free at https://console.groq.com
   - `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` — a Gmail App Password (needs 2-Step Verification)
   - `REDDIT_CLIENT_ID` / `REDDIT_SECRET` — create a "script" app at https://reddit.com/prefs/apps
4. Start the backend (terminal 1):
   ```
   uvicorn backend.main:app --reload
   ```
5. Start the frontend (terminal 2):
   ```
   streamlit run frontend/app.py
   ```
6. Open http://localhost:8501

## API docs

With the backend running, visit http://localhost:8000/docs for interactive
Swagger docs covering every endpoint.

## Project structure

```
newsletter_curator/
├── backend/
│   ├── main.py            FastAPI app + all routes
│   ├── database.py        SQLAlchemy engine, session, get_db
│   ├── models.py          6 tables: users, sources, stories, digests, digest_items, clicks
│   ├── schemas.py         Pydantic request/response shapes
│   ├── auth.py            password hashing + JWT
│   ├── fetcher.py         RSS / HN / Reddit fetchers
│   ├── embedder.py        sentence-transformers + ChromaDB ranking
│   ├── summarizer.py      Groq summaries (with offline fallback)
│   ├── digest_builder.py  the pipeline that chains it all
│   ├── scheduler.py       APScheduler daily job
│   └── emailer.py         HTML digest email via Gmail SMTP
├── frontend/
│   └── app.py             Streamlit UI
├── test_fetcher.py        per-stage test scripts
├── test_embedder.py
├── test_summarizer.py
├── requirements.txt
└── .env.example

Auto-created at runtime: newsletter.db (SQLite), chroma_db/ (vector store)
```

## Notes / future improvements

- **Email deliverability:** new senders often land in spam; production would use
  a transactional service (SendGrid / SES) with SPF/DKIM.
- **Scheduling:** the in-process scheduler only runs while uvicorn is up; a
  cloud host or OS-level cron would make it truly daily.
- **Password reset:** add a "forgot password" email flow.
- **Click tracking from the web UI:** currently most reliable from the email links.
