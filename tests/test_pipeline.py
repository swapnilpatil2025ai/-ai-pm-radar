"""Offline test: fake feeds, fake articles and a fake Claude client.

Run with:  python -m pytest -q
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pipeline.run as run

NOW = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Lab ships Model X</title><link>https://news.example/model-x</link><pubDate>{NOW}</pubDate><description>Model X is out.</description></item>
<item><title>Model X pricing</title><link>https://news.example/model-x-price</link><pubDate>{NOW}</pubDate><description>$1 per 1M.</description></item>
<item><title>Agent toolkit 2.0</title><link>https://news.example/agents</link><pubDate>{NOW}</pubDate><description>Agents.</description></item>
</channel></rss>"""
ARTICLE = "<html><body><article><p>Model X has a 1M context window and costs $1 per million input tokens.</p></article></body></html>"


class FakeResp:
    def __init__(self, body: str):
        self.text = body
        self.content = body.encode()

    def raise_for_status(self):
        pass


def fake_get(url, **_):
    return FakeResp(RSS if "news.example" not in url else ARTICLE)


class FakeClient:
    def __init__(self):
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        name = kw["tool_choice"]["name"]
        if name == "select_stories":
            data = {
                "edition_intro": "Model X arrives.",
                "picks": [{"candidate_ids": [0, 1], "working_title": "Model X", "why": "New frontier option"}],
            }
        else:
            data = {
                "headline": "Model X launches with 1M context",
                "category": "Models",
                "impact": "high",
                "eventDate": "not-a-date",
                "summary": "s",
                "pmTake": "p",
                "specs": [{"label": "Context", "value": "1M"}, {"label": "", "value": "dropped"}],
                "details": ["d1", "d2"],
                "actions": ["a1", "a2"],
                "source_ids": [0, 99],
            }
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=data)])


def test_end_to_end(tmp_path, monkeypatch):
    stories_path, editions_path = tmp_path / "stories.json", tmp_path / "editions.json"
    stories_path.write_text("[]")
    monkeypatch.setattr(run, "STORIES_PATH", stories_path)
    monkeypatch.setattr(run, "EDITIONS_PATH", editions_path)
    monkeypatch.setattr(run, "FEEDS", [("Example News", "https://feeds.example/rss")])
    monkeypatch.setattr(run.requests, "get", fake_get)

    assert run.main([], client=FakeClient()) == 0

    stories = json.loads(stories_path.read_text())
    assert len(stories) == 1
    s = stories[0]
    assert s["category"] == "Models" and s["impact"] == "high"
    assert s["specs"] == [{"label": "Context", "value": "1M"}]          # empty spec dropped
    assert [x["url"] for x in s["sources"]] == ["https://news.example/model-x"]  # bad id 99 ignored
    assert len(s["eventDate"]) == 10                                      # invalid date replaced
    assert json.loads(editions_path.read_text())[s["edition"]]["intro"] == "Model X arrives."
