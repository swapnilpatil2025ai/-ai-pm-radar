"""AI PM Radar: a twice-weekly AI briefing written for product managers.

Reads stories from data/stories.json and data/editions.json, which the
pipeline in pipeline/run.py refreshes on a schedule (see .github/workflows).
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

# ---- Edit these to make it yours -------------------------------------------
AUTHOR_NAME = "Your Name"
AUTHOR_LINK = ""  # e.g. https://www.linkedin.com/in/your-handle
REPO_LINK = ""  # e.g. https://github.com/your-handle/ai-pm-radar
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
CATEGORIES = ["All", "Models", "Products", "Agents & Dev", "Policy & Safety", "Market"]
IMPACT_LABEL = {"high": "High impact", "medium": "Worth knowing", "watch": "Watch"}

st.set_page_config(page_title="AI PM Radar", page_icon="📡", layout="centered")

st.markdown(
    """
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
h1, h2, h3, .radar-headline { font-family: "Bricolage Grotesque", system-ui, sans-serif !important; letter-spacing: -0.01em; }
.radar-meta { font-family: "IBM Plex Mono", monospace; font-size: 12.5px; opacity: .75; display: flex; gap: 16px; flex-wrap: wrap; }
.radar-tags { font-family: "IBM Plex Mono", monospace; font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 18px; }
.radar-cat { color: #1f5fd6; }
.radar-impact { padding: 2px 7px; border-radius: 4px; font-weight: 500; }
.radar-impact.high { color: #c2410c; background: rgba(194,65,12,.12); }
.radar-impact.medium { color: #8a6a00; background: rgba(184,140,0,.14); }
.radar-impact.watch { color: #5b6678; background: rgba(91,102,120,.14); }
.radar-date { opacity: .7; }
.radar-headline { font-size: 1.3rem; font-weight: 500; line-height: 1.25; margin: 6px 0 4px; }
.radar-pm { opacity: .85; }
.radar-specs { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 8px; margin: 0 0 12px; }
.radar-spec { border: 1px solid rgba(128,128,128,.3); border-radius: 8px; padding: 9px 11px; }
.radar-spec dt { font-family: "IBM Plex Mono", monospace; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .7; }
.radar-spec dd { margin: 2px 0 0; font-family: "IBM Plex Mono", monospace; font-size: 14px; overflow-wrap: anywhere; }
.radar-h4 { font-family: "IBM Plex Mono", monospace; font-size: 12px; text-transform: uppercase; letter-spacing: .07em; opacity: .7; margin: 14px 0 4px; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=600)
def load_data() -> tuple[list[dict], dict]:
    stories = json.loads((DATA_DIR / "stories.json").read_text(encoding="utf-8"))
    editions_path = DATA_DIR / "editions.json"
    editions = json.loads(editions_path.read_text(encoding="utf-8")) if editions_path.exists() else {}
    return stories, editions


def fmt_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        d = datetime.fromisoformat(value[:10])
        return f"{d.day} {d:%b %Y}"
    except ValueError:
        return value


def esc(text) -> str:
    return html.escape(str(text or ""))


def matches(story: dict, category: str, query: str) -> bool:
    if category != "All" and story.get("category") != category:
        return False
    if not query:
        return True
    haystack = " ".join(
        [story.get("headline", ""), story.get("summary", ""), story.get("pmTake", ""), story.get("category", "")]
        + list(story.get("details", []))
        + [f"{s.get('label', '')} {s.get('value', '')}" for s in story.get("specs", [])]
    ).lower()
    return query.lower() in haystack


def render_story(story: dict) -> None:
    impact = story.get("impact", "")
    tags = f'<span class="radar-cat">{esc(story.get("category", "News"))}</span>'
    if impact in IMPACT_LABEL:
        tags += f'<span class="radar-impact {impact}">{IMPACT_LABEL[impact]}</span>'
    if story.get("eventDate"):
        tags += f'<span class="radar-date">{esc(fmt_date(story["eventDate"]))}</span>'
    st.markdown(
        f'<div class="radar-tags">{tags}</div><div class="radar-headline">{esc(story.get("headline"))}</div>',
        unsafe_allow_html=True,
    )
    if story.get("summary"):
        st.markdown(esc(story["summary"]))
    if story.get("pmTake"):
        st.markdown(f'<div class="radar-pm"><b>For PMs:</b> {esc(story["pmTake"])}</div>', unsafe_allow_html=True)

    with st.expander("Full details"):
        specs = [s for s in story.get("specs", []) if s.get("label") and s.get("value")]
        if specs:
            cells = "".join(
                f'<div class="radar-spec"><dt>{esc(s["label"])}</dt><dd>{esc(s["value"])}</dd></div>' for s in specs
            )
            st.markdown(f'<dl class="radar-specs">{cells}</dl>', unsafe_allow_html=True)
        if story.get("details"):
            st.markdown('<div class="radar-h4">The full picture</div>', unsafe_allow_html=True)
            for para in story["details"]:
                st.markdown(esc(para))
        if story.get("actions"):
            st.markdown('<div class="radar-h4">What to do with it</div>', unsafe_allow_html=True)
            st.markdown("\n".join(f"- {esc(a)}" for a in story["actions"]))
        links = [s for s in story.get("sources", []) if str(s.get("url", "")).startswith(("https://", "http://"))]
        if links:
            st.markdown('<div class="radar-h4">Sources</div>', unsafe_allow_html=True)
            st.markdown(" · ".join(f"[{esc(s.get('name') or 'Source')}]({s['url']})" for s in links))
    st.divider()


# ---- Page -------------------------------------------------------------------
stories, editions = load_data()
stories.sort(key=lambda s: s.get("publishedAt", ""), reverse=True)

st.title("AI PM Radar")
st.markdown(
    "What changed in AI this week and what it means for product managers. "
    "Read the one-line brief; open a story for specs, sources and the full technical picture."
)
latest = fmt_date(stories[0]["publishedAt"]) if stories else "none yet"
st.markdown(
    f'<div class="radar-meta"><span>Last update <b>{esc(latest)}</b></span>'
    f"<span>New editions <b>Mon &amp; Thu</b></span><span>{len(stories)} stories archived</span></div>",
    unsafe_allow_html=True,
)
st.write("")

category = st.pills("Topic", CATEGORIES, default="All", label_visibility="collapsed") or "All"
query = st.text_input("Search", placeholder="Search stories, models, companies", label_visibility="collapsed").strip()

shown = [s for s in stories if matches(s, category, query)]
if not stories:
    st.info("No editions yet. The first one appears after the next scheduled run (Mondays and Thursdays).")
elif not shown:
    st.info("Nothing matches. Try another topic or clear the search box.")

edition_keys = sorted({s.get("edition", "Unsorted") for s in shown}, reverse=True)
for key in edition_keys:
    group = sorted((s for s in shown if s.get("edition", "Unsorted") == key), key=lambda s: s.get("rank", 99))
    meta = editions.get(key, {})
    st.header(meta.get("title") or f"Edition of {fmt_date(key)}", divider="gray")
    st.caption(f"{len(group)} {'story' if len(group) == 1 else 'stories'}")
    if meta.get("intro") and category == "All" and not query:
        st.markdown(f"*{esc(meta['intro'])}*")
    for story in group:
        render_story(story)

# ---- About / how it works (the portfolio part) -----------------------------
with st.sidebar:
    st.subheader("About")
    by = f"[{AUTHOR_NAME}]({AUTHOR_LINK})" if AUTHOR_LINK else AUTHOR_NAME
    st.markdown(f"Built and maintained by {by}.")
    st.markdown(
        "**How it works**\n\n"
        "1. Twice a week a GitHub Actions job pulls the latest posts from ~12 AI news feeds.\n"
        "2. An LLM (Google Gemini, free tier) ranks them for relevance to an AI product manager and groups duplicates.\n"
        "3. For each pick it reads the full articles and writes a structured brief: "
        "summary, PM takeaway, hard specs, details, actions.\n"
        "4. Links are restricted to the articles it actually read, so it can't cite sources it didn't use.\n"
        "5. The job commits the new edition; Streamlit redeploys automatically.\n\n"
        "The model provider is swappable (Gemini or Claude) with one setting, and the whole stack runs on free tiers."
    )
    if REPO_LINK:
        st.markdown(f"[Source code]({REPO_LINK})")
