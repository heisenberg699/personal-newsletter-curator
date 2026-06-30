# frontend/app.py
# ----------------------------------------------------------
# The visual web app the user actually sees.
# Streamlit talks to the FastAPI backend over HTTP (the same
# routes you tested on /docs). It never touches the database
# directly — it just calls the API and shows the results.
#
# Run it (with the backend already running) from the project root:
#     streamlit run frontend/app.py
# ----------------------------------------------------------

import requests
import streamlit as st

# Where the backend lives. If you change the uvicorn port, change it here.
import os
API = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Personal Newsletter Curator", page_icon="📰", layout="centered")


# ---- small helpers ---------------------------------------

def auth_headers():
    """Returns the Authorization header using the token saved after login."""
    return {"Authorization": f"Bearer {st.session_state.get('token', '')}"}


def api_get(path):
    return requests.get(f"{API}{path}", headers=auth_headers(), timeout=60)


def api_post(path, json=None, timeout=300):
    return requests.post(f"{API}{path}", json=json, headers=auth_headers(), timeout=timeout)


def safe_detail(response, fallback):
    """Reads an error message from the response without crashing on empty/non-JSON bodies."""
    try:
        return response.json().get("detail", fallback)
    except Exception:
        return f"{fallback} (server returned status {response.status_code})"


# ---- session state ---------------------------------------
# Streamlit reruns the whole script on every interaction, so we
# keep the login token in st.session_state, which persists.
if "token" not in st.session_state:
    st.session_state.token = None
if "email" not in st.session_state:
    st.session_state.email = None


# ==========================================================
# LOGIN / SIGNUP SCREEN  (shown when not logged in)
# ==========================================================

def login_screen():
    st.title("📰 Personal Newsletter Curator")
    st.caption("AI-curated news from the sources you choose, summarised for your interests.")

    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pw")
        if st.button("Log in", type="primary"):
            try:
                r = requests.post(f"{API}/login/json",
                                  json={"email": email, "password": password}, timeout=30)
                if r.status_code == 200:
                    st.session_state.token = r.json()["access_token"]
                    st.session_state.email = email
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Login failed"))
            except requests.exceptions.ConnectionError:
                st.error("Can't reach the backend. Is uvicorn running on port 8000?")

    with tab_signup:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input("Password (6+ characters)", type="password", key="signup_pw")
        interests = st.text_area(
            "Your interests",
            placeholder="e.g. AI, geopolitics, renewable energy, India trade policy",
            key="signup_interests",
        )
        cadence = st.selectbox("Email frequency", ["daily", "weekly"], key="signup_cadence")
        if st.button("Create account", type="primary"):
            try:
                r = requests.post(f"{API}/signup", json={
                    "email": email, "password": password,
                    "interests_text": interests, "email_cadence": cadence,
                }, timeout=30)
                if r.status_code == 200:
                    st.session_state.token = r.json()["access_token"]
                    st.session_state.email = email
                    st.success("Account created!")
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Signup failed"))
            except requests.exceptions.ConnectionError:
                st.error("Can't reach the backend. Is uvicorn running on port 8000?")


# ==========================================================
# MAIN APP  (shown when logged in)
# ==========================================================

def main_app():
    # --- sidebar: who's logged in + logout + sources ---
    with st.sidebar:
        st.write(f"Logged in as **{st.session_state.email}**")
        if st.button("Log out"):
            st.session_state.token = None
            st.session_state.email = None
            st.rerun()

        st.divider()
        st.subheader("Your sources")

        # Add a new source
        with st.expander("➕ Add a source"):
            stype = st.selectbox("Type", ["rss", "reddit", "hn"],
                                 help="rss = feed URL · reddit = subreddit name · hn = Hacker News search tag")
            svalue = st.text_input("Value",
                                   placeholder="https://thediplomat.com/feed/  •  geopolitics  •  artificial intelligence")
            if st.button("Add"):
                r = api_post("/sources", {"type": stype, "value": svalue})
                if r.status_code == 200:
                    st.success("Added!")
                    st.rerun()
                else:
                    st.error(r.json().get("detail", "Could not add"))

        # List existing sources with delete buttons
        r = api_get("/sources")
        if r.status_code == 200:
            sources = r.json()
            if not sources:
                st.info("No sources yet. Add one above.")
            for s in sources:
                col1, col2 = st.columns([4, 1])
                col1.write(f"`{s['type']}` {s['value']}")
                if col2.button("🗑", key=f"del_{s['id']}"):
                    api_post  # noqa (kept for symmetry)
                    requests.delete(f"{API}/sources/{s['id']}", headers=auth_headers(), timeout=30)
                    st.rerun()

    # --- main area: tabs for Digest and Stats ---
    st.title("📰 Your Digest")

    tab_digest, tab_stats = st.tabs(["Today's digest", "📊 Stats"])

    with tab_digest:
        col1, col2 = st.columns([1, 1])
        if col1.button("🔄 Build new digest", type="primary"):
            with st.spinner("Fetching, ranking and summarising… first build can take up to a minute."):
                try:
                    r = api_post("/digests/build")
                    if r.status_code == 200:
                        st.success("Fresh digest built!")
                    else:
                        st.error(safe_detail(r, "Could not build digest"))
                except requests.exceptions.Timeout:
                    st.warning("Still building on the server — give it a moment, then refresh the page.")
                except requests.exceptions.ConnectionError:
                    st.error("Lost connection to the backend. Is uvicorn still running?")

        if col2.button("✉️ Email me this digest"):
            with st.spinner("Sending…"):
                r = api_post("/digests/latest/email")
            if r.status_code == 200:
                st.success(r.json()["status"])
            else:
                st.error(safe_detail(r, "Could not send email"))

        st.divider()

        # Show the latest digest
        r = api_get("/digests/latest")
        if r.status_code == 200:
            digest = r.json()
            st.caption(f"Built: {digest['created_at'][:19]}  ·  {len(digest['items'])} stories")
            for item in digest["items"]:
                with st.container(border=True):
                    # Title links through the /click route so the click is tracked
                    click_url = (f"{API}/click?user_id=0&story_id={item['story_id']}"
                                 f"&redirect={item['url']}")
                    st.markdown(f"#### [{item['title']}]({item['url']})")
                    st.write(item["summary"])
                    st.markdown(f"💡 *{item['why_matters']}*")
                    st.caption(f"relevance score: {item['rank_score']:.3f}")
        elif r.status_code == 404:
            st.info("No digest yet. Click **Build new digest** to create your first one.")
        else:
            st.error("Could not load digest.")

    with tab_stats:
        r = api_get("/stats")
        if r.status_code == 200:
            stats = r.json()
            st.metric("Total clicks", stats["total_clicks"])
            st.subheader("Most-clicked stories")
            if stats["top_stories"]:
                for s in stats["top_stories"]:
                    st.write(f"**{s['clicks']}×** — [{s['title']}]({s['url']})")
            else:
                st.info("No clicks yet. Click a story link in your digest or email.")
        else:
            st.error("Could not load stats.")


# ==========================================================
# ROUTER
# ==========================================================
if st.session_state.token:
    main_app()
else:
    login_screen()
