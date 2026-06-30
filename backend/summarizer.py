# backend/summarizer.py
# ----------------------------------------------------------
# Turns a raw article into two short, useful pieces of text:
#   • summary     — 2 plain sentences on what the article says
#   • why_matters — 1 sentence on why THIS user should care,
#                   written using their stated interests
#
# Uses Groq (free, very fast) running Llama 3. If the API key is
# missing or the call fails, we fall back to a simple summary so
# the digest is never empty.
# ----------------------------------------------------------

import json
import os

from dotenv import load_dotenv

load_dotenv()

# The model Groq serves for free. Fast and good enough for summaries.
GROQ_MODEL = "llama-3.1-8b-instant"

_client = None


def get_client():
    """Creates the Groq client once and reuses it. Returns None if no key."""
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            return None
        from groq import Groq
        _client = Groq(api_key=api_key)
    return _client


def summarize_story(title: str, raw_text: str, user_interests: str) -> dict:
    """
    Returns a dict: {"summary": "...", "why_matters": "..."}.

    We ask the model to reply in strict JSON so we can parse it
    reliably. If anything goes wrong, we return a safe fallback
    instead of raising — the digest must always have content.
    """
    client = get_client()

    # ---- fallback if Groq isn't configured ----
    if client is None:
        return _fallback(title, raw_text)

    # The prompt is deliberately strict about format and length.
    # "Respond ONLY with JSON" + an example shape = reliable parsing.
    prompt = f"""You are writing a personalised news digest.

The reader's interests: {user_interests or "general news"}

Article title: {title}
Article text: {raw_text[:1500]}

Write:
1. "summary": exactly 2 sentences, plain and factual, on what this article says.
2. "why_matters": exactly 1 sentence on why it matters specifically to a reader interested in the topics above. If it doesn't clearly connect, say why it's still worth a glance.

Respond ONLY with a JSON object, no preamble, no markdown:
{{"summary": "...", "why_matters": "..."}}"""

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,        # low = consistent, factual
            max_tokens=250,
            # Asking Groq itself to guarantee valid JSON
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        data = json.loads(content)

        # Make sure both keys exist even if the model forgot one
        return {
            "summary": data.get("summary", "").strip() or _fallback(title, raw_text)["summary"],
            "why_matters": data.get("why_matters", "").strip()
            or "Relevant to your selected interests.",
        }
    except Exception as e:
        print(f"[summarizer] Groq call failed ({e}); using fallback.")
        return _fallback(title, raw_text)


def _fallback(title: str, raw_text: str) -> dict:
    """
    A no-AI summary: the title plus the first ~200 chars of text.
    Keeps the app working even with no API key or no internet.
    """
    snippet = raw_text.strip().replace("\n", " ")[:200]
    if snippet:
        summary = f"{title}. {snippet}..."
    else:
        summary = title
    return {
        "summary": summary,
        "why_matters": "Matched one of your sources or interests.",
    }
