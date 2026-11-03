"""Model providers for the pipeline.

Pick one with the PROVIDER environment variable:
  PROVIDER=gemini     (default) Google Gemini API, free tier. Needs GEMINI_API_KEY.
  PROVIDER=anthropic  Claude API, paid. Needs ANTHROPIC_API_KEY.

Both expose the same call: client.call_tool(system, tool, prompt, max_tokens) -> dict,
where `tool` is a JSON-schema tool definition and the model is forced to call it.
"""

from __future__ import annotations

import os
import sys
import time

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Keys Gemini's function-calling schema accepts; anything else is dropped.
GEMINI_SCHEMA_KEYS = {"type", "description", "properties", "required", "items", "enum"}


def _gemini_schema(node):
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key not in GEMINI_SCHEMA_KEYS:
                continue
            if key == "properties":
                out[key] = {name: _gemini_schema(v) for name, v in value.items()}
            elif key == "items":
                out[key] = _gemini_schema(value)
            else:
                out[key] = value
        return out
    return node


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, pause: float = 5.0):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise SystemExit("GEMINI_API_KEY is not set. Create a free key at https://aistudio.google.com/apikey")
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        self.pause = pause  # spacing between calls keeps us under free-tier per-minute limits

    def call_tool(self, system: str, tool: dict, prompt: str, max_tokens: int = 4000) -> dict:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": _gemini_schema(tool["input_schema"]),
                        }
                    ]
                }
            ],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [tool["name"]]}},
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
        }
        for attempt in range(4):
            time.sleep(self.pause)
            resp = requests.post(
                GEMINI_URL.format(model=self.model),
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=body,
                timeout=120,
            )
            if resp.status_code in (429, 500, 503) and attempt < 3:
                wait = 30 * (attempt + 1)
                print(f"  ! Gemini {resp.status_code}, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    call = part.get("functionCall")
                    if call and call.get("name") == tool["name"]:
                        return call.get("args", {})
            if attempt < 3:
                print("  ! Gemini returned no tool call, retrying", file=sys.stderr)
                continue
            raise RuntimeError(f"Gemini returned no tool call: {str(data)[:300]}")
        raise RuntimeError("Gemini call failed")


class AnthropicClient:
    def __init__(self, model: str | None = None):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    def call_tool(self, system: str, tool: dict, prompt: str, max_tokens: int = 4000) -> dict:
        for attempt in range(3):
            try:
                msg = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    tools=[tool],
                    tool_choice={"type": "tool", "name": tool["name"]},
                    messages=[{"role": "user", "content": prompt}],
                )
                for block in msg.content:
                    if getattr(block, "type", "") == "tool_use":
                        return block.input
                raise RuntimeError("model returned no tool call")
            except Exception as exc:
                if attempt == 2:
                    raise
                print(f"  ! retrying after error: {exc}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("Claude call failed")


def make_client():
    provider = os.environ.get("PROVIDER", "gemini").lower()
    if provider == "anthropic":
        return AnthropicClient()
    if provider == "gemini":
        return GeminiClient()
    raise SystemExit(f"Unknown PROVIDER '{provider}'. Use 'gemini' or 'anthropic'.")
