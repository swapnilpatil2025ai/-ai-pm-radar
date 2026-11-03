# AI PM Radar

A twice-weekly briefing on what changed in AI, written for product managers. Each story has a one-line summary and a "For PMs" takeaway; expand it for hard specs (pricing, context window, benchmarks), the full technical picture, suggested actions and sources.

**Live site:** _add your `*.streamlit.app` link here_

## How it works

```
 RSS feeds (TechCrunch, The Verge, OpenAI, Google, HN, …)
        │  GitHub Actions, Mon & Thu 06:47 IST
        ▼
 pipeline/run.py
   1. collect posts since the last edition, skip URLs already covered
   2. Gemini (free tier) ranks ~150 candidates for an AI PM, groups duplicates, picks 8–12
   3. for each pick: fetch full articles → Gemini writes a structured brief
   4. append to data/stories.json + data/editions.json, commit
        │
        ▼
 Streamlit Community Cloud redeploys app.py on every commit
```

Everything runs on free tiers: GitHub, GitHub Actions (public repo), Streamlit Community Cloud and the Gemini API.

## Product decisions

- **Audience first.** The editor prompt defines what an AI PM cares about (capability, price, availability, platform shifts, policy that changes what can ship) and what to skip (event promos, minor rounds, opinion without news).
- **Summary, then depth.** Every story leads with two sentences and one PM takeaway; specs and detail sit behind an expander so the page scans in under two minutes.
- **Trustworthy sources.** The model returns *which* fetched articles it used, and the code builds the links from those URLs only. It can't cite a page it didn't read.
- **Structured output.** Stories come back through a tool schema (enums for category and impact, 2–6 specs, 2–4 detail paragraphs), so every story renders the same way and bad values are cleaned rather than shown.
- **Failure-tolerant.** A dead feed or an unreadable article is skipped; a failed story doesn't block the rest; if nothing new is written, the data is left untouched and nothing is committed.
- **No repeats.** Recent headlines are passed to the selection step, and URLs already used are filtered out before the model sees them.
- **Swappable model, zero cost.** A thin provider layer (`pipeline/llm.py`) runs on Gemini's free tier by default and switches to Claude with one setting, so quality and cost can be traded off without touching the pipeline.

## Set it up (about 20 minutes)

1. **Put the code on GitHub.** Create a new *public* repository named `ai-pm-radar` and upload these files (keep the folder structure, including `.github/` and `.streamlit/`).
2. **Get a free Gemini API key** at [aistudio.google.com/apikey](https://aistudio.google.com/apikey): sign in with a Google account → **Create API key**. Don't add billing, so the project stays on the free tier.
3. **Add the key to GitHub:** repo **Settings → Secrets and variables → Actions → New repository secret**, name `GEMINI_API_KEY`.
4. **Let the workflow commit:** **Settings → Actions → General → Workflow permissions →** "Read and write permissions".
5. **Test a run:** **Actions → Update AI PM Radar → Run workflow.** A new edition should be committed to `data/` within a few minutes. If it says "Too few new articles", that's normal right after the seed edition.
6. **Deploy:** sign in at [share.streamlit.io](https://share.streamlit.io) with GitHub → **Create app** → pick the repo, branch `main`, file `app.py`. You can choose a custom subdomain like `ai-pm-radar.streamlit.app`.
7. **Make it yours:** edit `AUTHOR_NAME`, `AUTHOR_LINK` and `REPO_LINK` at the top of `app.py`, and put the live link at the top of this README.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-pipeline.txt pytest
streamlit run app.py                                  # the site
python -m pytest -q                                   # offline pipeline test, no API key needed
GEMINI_API_KEY=... python -m pipeline.run --dry-run  # see what it would pick
```

## Customize

- **Sources:** `pipeline/sources.py`
- **Editorial voice and selection rules:** `EDITOR_BRIEF` in `pipeline/run.py`
- **Model:** `GEMINI_MODEL` in the workflow (default `gemini-3.8-flash`). To use Claude instead, set `PROVIDER: anthropic` and add an `ANTHROPIC_API_KEY` secret (paid).
- **Schedule:** the `cron` line in `.github/workflows/update.yml` (UTC)

## Good to know

- Free Streamlit apps sleep after a period without visitors; the first visitor wakes it with one click.
- GitHub pauses scheduled workflows in repos with no activity for 60 days. The bot's own commits keep it active, but if runs ever stop, re-enable the workflow in the Actions tab.
- Gemini's free tier has daily and per-minute limits (see your key's limits in AI Studio). A run makes about a dozen calls spaced a few seconds apart, well within them. Google may use free-tier prompts to improve its products; the input here is public news.
- X/Twitter has no free feed, so posts there arrive through news coverage.
