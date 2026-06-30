# test_summarizer.py
# ----------------------------------------------------------
# Step 6 test — run from the project root:
#     python test_summarizer.py
#
# If GROQ_API_KEY is set in .env, it calls the real AI.
# If not, it shows the fallback summary still works.
# ----------------------------------------------------------

import os

from dotenv import load_dotenv

from backend.summarizer import summarize_story

load_dotenv()

has_key = bool(os.environ.get("GROQ_API_KEY", "").strip())
print(f"GROQ_API_KEY present: {has_key}")
print("(no key = you'll see the fallback summary, which is fine)\n")

# A realistic test article matching your interests
title = "India and Oman sign comprehensive economic partnership agreement"
raw_text = (
    "India and Oman have signed a CEPA covering tariff reductions on "
    "thousands of goods, services trade, and investment protection. "
    "The deal is India's first trade agreement with a Gulf Cooperation "
    "Council member and is expected to boost bilateral trade significantly, "
    "with energy, petrochemicals, and engineering goods among key sectors."
)
interests = "AI, geopolitics, energy, India trade policy"

print("--- Article ---")
print("Title:", title)
print("\n--- AI output ---")
result = summarize_story(title, raw_text, interests)
print("SUMMARY:    ", result["summary"])
print("WHY MATTERS:", result["why_matters"])

# Basic sanity checks
print("\n--- Checks ---")
print("summary present: ", bool(result["summary"]))
print("why_matters present:", bool(result["why_matters"]))

# Test the fallback explicitly by temporarily hiding the key
print("\n--- Forced fallback test (no key) ---")
saved = os.environ.pop("GROQ_API_KEY", None)
import backend.summarizer as s
s._client = None  # reset the cached client
fb = summarize_story(title, raw_text, interests)
print("SUMMARY:    ", fb["summary"])
print("WHY MATTERS:", fb["why_matters"])
if saved:
    os.environ["GROQ_API_KEY"] = saved

print("\nDone.")
