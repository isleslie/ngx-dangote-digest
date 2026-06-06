"""Optional LLM narrative for the daily report, via GitHub Models.

Best-effort by design: if no token is configured or the call fails, the caller
keeps the report and simply omits the narrative paragraph. Prompt building is a
pure function (unit-tested), and the HTTP client is isolated so tests mock it
rather than hitting the network.

GitHub Models is used because the project already runs in GitHub Actions, where
the built-in ``GITHUB_TOKEN`` (with ``permissions: models: read``) authenticates
inference with no extra secret to manage.
"""
from __future__ import annotations

import requests

from .report import ReportData, _fmt_naira_compact, _fmt_int, _fmt_pct, _fmt_price

_SYSTEM_PROMPT = (
    "You are a concise financial data assistant. Given end-of-day figures for "
    "a few Nigerian Exchange (NGX) stocks, write a neutral 2-3 sentence summary "
    "of the day's moves. State facts only — no predictions, no buy/sell advice. "
    "Prices are in Nigerian naira. Do not invent numbers not given to you."
)


def build_summary_prompt(data: ReportData) -> list[dict]:
    """Build the chat messages from the report data. Pure and deterministic."""
    lines = [f"NGX Dangote stocks for {data.as_of.isoformat()}:"]
    for t in data.tickers:
        if not t.latest:
            lines.append(f"- {t.ticker} ({t.name}): no data")
            continue
        vol = t.latest.get("volume")
        mcap = t.latest.get("market_cap")
        lines.append(
            f"- {t.ticker} ({t.name}): close ₦{_fmt_price(t.close)}, "
            f"change {_fmt_price(t.change)} ({_fmt_pct(t.pct_change)}), "
            f"volume {_fmt_int(vol)}, market cap {_fmt_naira_compact(mcap)}"
        )
    user = "\n".join(lines)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


class GitHubModelsClient:
    """Minimal GitHub Models chat-completions client (OpenAI-compatible)."""

    DEFAULT_ENDPOINT = "https://models.github.ai/inference/chat/completions"
    API_VERSION = "2026-03-10"

    def __init__(
        self,
        token: str,
        model: str = "openai/gpt-4o-mini",
        endpoint: str | None = None,
        timeout: int = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.token = token
        self.model = model
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT
        self.timeout = timeout
        self.session = session or requests.Session()

    def complete(
        self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 300
    ) -> str:
        resp = self.session.post(
            self.endpoint,
            timeout=self.timeout,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": self.API_VERSION,
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


def summarize(data: ReportData, client: GitHubModelsClient, max_tokens: int = 300) -> str | None:
    """Return a one-paragraph narrative, or ``None`` if generation fails.

    Never raises — summarization is an optional enhancement, so any error
    (no network, bad token, malformed response) degrades to no narrative.
    """
    try:
        text = client.complete(build_summary_prompt(data), max_tokens=max_tokens)
        return text or None
    except Exception:
        return None
