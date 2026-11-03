"""Build a new AI PM Radar edition.

Steps:
  1. Collect recent posts from the RSS feeds in sources.py.
  2. Ask the model to pick the 8-12 most important items for an AI product manager
     (grouping articles about the same event) and write the edition intro.
  3. For each pick, fetch the full articles and ask the model for a structured brief.
  4. Append the new edition to data/stories.json and data/editions.json.

The model provider is chosen in pipeline/llm.py (Gemini free tier by default).

Run:  python -m pipeline.run            (needs GEMINI_API_KEY, or PROVIDER=anthropic + ANTHROPIC_API_KEY)
      python -m pipeline.run --dry-run  (fetch + select only, writes nothing)
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import trafilatura

from pipeline.llm import make_client
from pipeline.sources import FEEDS

ROOT = Path(__file__).resolve().parent.parent
STORIES_PATH = ROOT / "data" / "stories.json"
EDITIONS_PATH = ROOT / "data" / "editions.json"

IST = timezone(timedelta(hours=5, minutes=30))
CATEGORIES = ["Models", "Products", "Agents & Dev", "Policy & Safety", "Market"]
IMPACTS = ["high", "medium", "watch"]
USER_AGENT = "AI-PM-Radar/1.0 (personal news digest)"
MAX_ARTICLE_CHARS = 12_000
MAX_CANDIDATES = 150

EDITOR_BRIEF = (
    "You are the editor of AI PM Radar, a twice-weekly briefing for AI product managers. "
    "Readers want to know what changed in AI and what it means for building products: new models "
    "(capabilities, benchmarks, pricing, context, availability), product launches and UX shifts from major "
    "labs and platforms, agents and developer tooling, policy and safety changes that affect what can ship, "
    "and market moves (pricing, usage limits, funding, M&A) that change build-vs-buy decisions. "
    "Skip event promos, listicles, opinion pieces without news, and minor funding rounds."
)

SELECT_TOOL = {
    "name": "select_stories",
    "description": "Choose the stories for this edition.",
    "input_schema": {
        "type": "object",
        "properties": {
            "edition_intro": {
                "type": "string",
                "description": "2-3 sentences on the main themes of this edition, in plain language.",
            },
            "picks": {
                "type": "array",
                "minItems": 1,
                "maxItems": 12,
                "description": "Most important first. Group candidates that cover the same event into one pick.",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 4},
                        "working_title": {"type": "string"},
                        "why": {"type": "string", "description": "One line: why an AI PM should care."},
                    },
                    "required": ["candidate_ids", "working_title", "why"],
                },
            },
        },
        "required": ["edition_intro", "picks"],
    },
}

STORY_TOOL = {
    "name": "write_story",
    "description": "Write one structured story for the briefing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "Specific, at most 110 characters."},
            "category": {"type": "string", "enum": CATEGORIES},
            "impact": {
                "type": "string",
                "enum": IMPACTS,
                "description": "high = likely changes roadmaps or vendor choices; medium = worth knowing; watch = early signal.",
            },
            "eventDate": {"type": "string", "description": "YYYY-MM-DD the event happened, from the articles."},
            "summary": {"type": "string", "description": "1-2 sentences."},
            "pmTake": {"type": "string", "description": "One sentence on why it matters to a product manager."},
            "specs": {
                "type": "array",
                "minItems": 2,
                "maxItems": 6,
                "description": "Hard facts stated in the articles: parameters, context window, price per 1M tokens, benchmark scores, availability, dates. Never estimate.",
                "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                    "required": ["label", "value"],
                },
            },
            "details": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": {"type": "string"},
                "description": "Paragraphs with the full technical picture, caveats and context.",
            },
            "actions": {
                "type": "array",
                "minItems": 2,
                "maxItems": 3,
                "items": {"type": "string"},
                "description": "Concrete things a PM could do this week.",
            },
            "source_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Which of the provided articles you relied on.",
            },
        },
        "required": ["headline", "category", "impact", "summary", "pmTake", "specs", "details", "actions", "source_ids"],
    },
}


# ---- data ------------------------------------------------------------------
def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def slugify(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "story"


# ---- step 1: collect --------------------------------------------------------
def entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def collect_candidates(since: datetime, seen_urls: set[str]) -> list[dict]:
    candidates, urls = [], set()
    for name, url in FEEDS:
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as exc:  # a dead feed must not stop the run
            print(f"  ! skipped {name}: {exc}", file=sys.stderr)
            continue
        kept = 0
        for e in feed.entries:
            link = (e.get("link") or "").split("#")[0]
            when = entry_time(e)
            if not link or link in urls or link in seen_urls or (when and when < since):
                continue
            snippet = html.unescape(re.sub(r"<[^>]+>", " ", e.get("summary", "") or ""))
            candidates.append(
                {
                    "title": (e.get("title") or "").strip(),
                    "url": link,
                    "source": name,
                    "date": when.date().isoformat() if when else "",
                    "snippet": " ".join(snippet.split())[:300],
                }
            )
            urls.add(link)
            kept += 1
        print(f"  {name}: {kept} new")
    candidates.sort(key=lambda c: c["date"], reverse=True)
    return candidates[:MAX_CANDIDATES]


def fetch_article(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
        resp.raise_for_status()
        text = trafilatura.extract(resp.text, include_comments=False, include_tables=True) or ""
    except Exception as exc:
        print(f"  ! could not fetch {url}: {exc}", file=sys.stderr)
        text = ""
    return text[:MAX_ARTICLE_CHARS]


# ---- model calls ----------------------------------------------------------
def call_tool(client, tool: dict, prompt: str, max_tokens: int = 4000) -> dict:
    return client.call_tool(EDITOR_BRIEF, tool, prompt, max_tokens)


def select(client, candidates: list[dict], recent_headlines: list[str]) -> dict:
    listing = "\n".join(
        f"[{i}] {c['date']} | {c['source']} | {c['title']} | {c['snippet']}" for i, c in enumerate(candidates)
    )
    recent = "\n".join(f"- {h}" for h in recent_headlines) or "(none)"
    prompt = (
        f"Candidate articles published since the last edition:\n{listing}\n\n"
        f"Headlines already covered in recent editions (don't repeat unless there is a material new development):\n{recent}\n\n"
        "Pick the 8-12 most important stories for an AI product manager. Group candidates about the same event."
    )
    return call_tool(client, SELECT_TOOL, prompt, max_tokens=3000)


def write_story(client, pick: dict, articles: list[dict]) -> dict:
    blocks = "\n\n".join(
        f"<article id=\"{i}\" source=\"{a['source']}\" date=\"{a['date']}\" url=\"{a['url']}\">\n"
        f"TITLE: {a['title']}\n{a['text'] or a['snippet']}\n</article>"
        for i, a in enumerate(articles)
    )
    prompt = (
        f"Story: {pick['working_title']}\nWhy it was picked: {pick['why']}\n\n{blocks}\n\n"
        "Write the story using only facts in these articles. Use your own words; never copy sentences. "
        "If articles disagree on a number, say so or leave it out."
    )
    return call_tool(client, STORY_TOOL, prompt, max_tokens=3000)


def clean_story(raw: dict, articles: list[dict], edition: str, rank: int, now: datetime) -> dict:
    used = [i for i in raw.get("source_ids", []) if isinstance(i, int) and 0 <= i < len(articles)] or range(len(articles))
    # Links come only from articles we actually fetched, never from the model's text.
    sources = [{"name": articles[i]["source"], "url": articles[i]["url"]} for i in dict.fromkeys(used)]
    event_date = raw.get("eventDate", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_date or ""):
        event_date = next((a["date"] for a in articles if a["date"]), edition)
    headline = raw["headline"].strip()
    return {
        "id": f"{edition}-{slugify(headline)}",
        "edition": edition,
        "rank": rank,
        "publishedAt": now.isoformat(timespec="seconds"),
        "eventDate": event_date,
        "category": raw["category"] if raw.get("category") in CATEGORIES else "Market",
        "impact": raw["impact"] if raw.get("impact") in IMPACTS else "watch",
        "headline": headline[:140],
        "summary": raw["summary"].strip(),
        "pmTake": raw["pmTake"].strip(),
        "specs": [s for s in raw.get("specs", []) if s.get("label") and s.get("value")][:6],
        "details": [p for p in raw.get("details", []) if p.strip()][:4],
        "actions": [a for a in raw.get("actions", []) if a.strip()][:3],
        "sources": sources,
    }


# ---- main ------------------------------------------------------------------
def main(argv: list[str] | None = None, client=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="collect and select only; write nothing")
    parser.add_argument("--lookback-days", type=int, default=None, help="override how far back to look")
    args = parser.parse_args(argv)

    stories = load_json(STORIES_PATH, [])
    editions = load_json(EDITIONS_PATH, {})
    now = datetime.now(IST)
    edition = now.date().isoformat()

    if args.lookback_days is not None:
        since = now - timedelta(days=args.lookback_days)
    elif stories:
        last = max(datetime.fromisoformat(s["publishedAt"]) for s in stories)
        since = max(last - timedelta(hours=12), now - timedelta(days=7))
    else:
        since = now - timedelta(days=4)
    seen_urls = {src["url"] for s in stories for src in s.get("sources", [])}
    recent_headlines = [s["headline"] for s in sorted(stories, key=lambda s: s["publishedAt"], reverse=True)[:40]]

    print(f"Collecting posts since {since:%Y-%m-%d %H:%M %Z}")
    candidates = collect_candidates(since, seen_urls)
    print(f"{len(candidates)} candidates")
    if len(candidates) < 3:
        print("Too few new articles; skipping this run.")
        return 0

    if client is None:
        client = make_client()

    selection = select(client, candidates, recent_headlines)
    picks = selection.get("picks", [])
    print(f"Selected {len(picks)} stories")
    if args.dry_run:
        for p in picks:
            print(f"  - {p['working_title']}  ({p['why']})")
        return 0

    new_stories, ids = [], {s["id"] for s in stories}
    for rank, pick in enumerate(picks, start=1):
        chosen = [candidates[i] for i in pick.get("candidate_ids", []) if isinstance(i, int) and 0 <= i < len(candidates)]
        if not chosen:
            continue
        articles = [dict(c, text=fetch_article(c["url"])) for c in chosen]
        try:
            story = clean_story(write_story(client, pick, articles), articles, edition, rank, now)
        except Exception as exc:
            print(f"  ! skipped '{pick['working_title']}': {exc}", file=sys.stderr)
            continue
        while story["id"] in ids:
            story["id"] += "-2"
        ids.add(story["id"])
        new_stories.append(story)
        print(f"  ✓ {story['headline']}")

    if not new_stories:
        print("No stories written; leaving data unchanged.")
        return 1

    editions[edition] = {"title": f"{now:%a} {now.day} {now:%b %Y}", "intro": selection.get("edition_intro", "")}
    save_json(STORIES_PATH, new_stories + stories)
    save_json(EDITIONS_PATH, editions)
    print(f"Wrote edition {edition} with {len(new_stories)} stories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
