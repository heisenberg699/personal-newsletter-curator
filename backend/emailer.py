# backend/emailer.py
# ----------------------------------------------------------
# Formats a digest into a clean HTML email and sends it through
# Gmail's SMTP server.
#
# Needs in .env:
#   GMAIL_ADDRESS       your gmail address
#   GMAIL_APP_PASSWORD  a 16-char "App Password" (NOT your normal
#                       password — see Step 9 instructions)
#
# If those are missing, send_digest_email() skips gracefully and
# returns False instead of crashing — the digest still exists in
# the app, it just isn't emailed.
# ----------------------------------------------------------

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from backend.models import Digest, DigestItem, Story, User

load_dotenv()

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()


def build_email_html(user: User, digest: Digest, db: Session) -> str:
    """
    Builds the HTML body of the digest email.
    Each story becomes a card with title (linked), summary, and
    a highlighted 'why this matters to you' line.
    The link goes through our /click route so we can track opens
    (that tracking route is added in Step 10).
    """
    items = (
        db.query(DigestItem)
        .filter(DigestItem.digest_id == digest.id)
        .order_by(DigestItem.rank_score.desc())
        .all()
    )

    # Inline CSS — email clients ignore <style> tags and external CSS,
    # so every style has to live on the element itself.
    cards = []
    for item in items:
        story = db.get(Story, item.story_id)
        if story is None:
            continue

        # Step 10 will make this a tracked link; for now it points
        # straight at the article, with the user/story ids ready.
        link = (
            f"http://127.0.0.1:8000/click?user_id={user.id}"
            f"&story_id={story.id}&redirect={story.url}"
        )

        cards.append(f"""
        <div style="border:1px solid #e0e0e0; border-radius:8px;
                    padding:16px; margin-bottom:16px; background:#ffffff;">
          <a href="{link}" style="font-size:17px; font-weight:bold;
                    color:#1a73e8; text-decoration:none;">
            {story.title}
          </a>
          <p style="color:#333; font-size:14px; line-height:1.5; margin:10px 0;">
            {item.summary}
          </p>
          <p style="color:#0b8043; font-size:13px; font-style:italic; margin:0;">
            💡 {item.why_matters}
          </p>
        </div>
        """)

    cards_html = "".join(cards) if cards else "<p>No stories today.</p>"

    return f"""
    <html>
      <body style="font-family:Arial,sans-serif; background:#f5f5f5;
                   padding:20px; margin:0;">
        <div style="max-width:600px; margin:0 auto;">
          <h2 style="color:#202124;">Your Personal News Digest</h2>
          <p style="color:#5f6368; font-size:13px;">
            Curated for your interests: {user.interests_text or "general news"}
          </p>
          {cards_html}
          <p style="color:#9aa0a6; font-size:12px; text-align:center;
                    margin-top:24px;">
            Sent by your Personal Newsletter Curator
          </p>
        </div>
      </body>
    </html>
    """


def send_digest_email(user: User, digest: Digest, db: Session) -> bool:
    """
    Sends the digest to the user's email via Gmail SMTP.
    Returns True if sent, False if skipped or failed.
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("[emailer] skipped — GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env")
        return False

    html = build_email_html(user, digest, db)

    # MIMEMultipart('alternative') lets us send HTML (and could carry
    # a plain-text version too). We set the headers, then the body.
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Personal News Digest"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = user.email
    msg.attach(MIMEText(html, "html"))

    try:
        # Gmail's SSL SMTP server runs on port 465.
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"[emailer] sent digest to {user.email}")
        return True
    except Exception as e:
        # Wrong app password, network blocked, etc. — log, don't crash.
        print(f"[emailer] failed to send to {user.email}: {e}")
        return False
