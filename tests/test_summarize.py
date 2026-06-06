from datetime import date

from ngx_digest.report import ReportData, TickerReport
from ngx_digest.summarize import (
    GitHubModelsClient,
    build_summary_prompt,
    summarize,
)


def _data():
    return ReportData(
        as_of=date(2026, 6, 5),
        tickers=[
            TickerReport(
                "DANGCEM", "Dangote Cement",
                latest={"close": 1180.0, "prev_close": 1180.0,
                        "volume": 1_136_842, "market_cap": 1.99e13},
                closes=[1170.0, 1180.0],
            ),
        ],
    )


# --- prompt building (pure) -------------------------------------------------


def test_build_prompt_has_system_and_facts():
    msgs = build_summary_prompt(_data())
    assert msgs[0]["role"] == "system"
    assert "advice" in msgs[0]["content"].lower()  # guardrail present
    user = msgs[1]["content"]
    assert "DANGCEM" in user
    assert "1,180.00" in user        # formatted close present
    assert "2026-06-05" in user      # session date present


# --- client (mocked transport) ---------------------------------------------


class _FakePostSession:
    def __init__(self, payload):
        self.payload = payload
        self.last = None

    def post(self, url, timeout=None, headers=None, json=None):
        self.last = {"url": url, "headers": headers, "json": json}

        class _Resp:
            def __init__(s, p):
                s._p = p

            def raise_for_status(s):
                pass

            def json(s):
                return s._p

        return _Resp(self.payload)


def test_client_parses_completion_and_sets_auth():
    payload = {"choices": [{"message": {"content": "  Markets were calm.  "}}]}
    sess = _FakePostSession(payload)
    client = GitHubModelsClient("tok", model="openai/gpt-4o-mini", session=sess)
    out = client.complete([{"role": "user", "content": "hi"}])
    assert out == "Markets were calm."  # trimmed
    assert sess.last["headers"]["Authorization"] == "Bearer tok"
    assert sess.last["headers"]["X-GitHub-Api-Version"] == GitHubModelsClient.API_VERSION
    assert sess.last["json"]["model"] == "openai/gpt-4o-mini"


# --- summarize() is best-effort --------------------------------------------


class _OkClient:
    def complete(self, messages, max_tokens=300):
        return "All three closed flat on light volume."


class _BoomClient:
    def complete(self, messages, max_tokens=300):
        raise RuntimeError("network down")


class _EmptyClient:
    def complete(self, messages, max_tokens=300):
        return ""


def test_summarize_returns_text_on_success():
    assert summarize(_data(), _OkClient()) == "All three closed flat on light volume."


def test_summarize_returns_none_on_failure():
    assert summarize(_data(), _BoomClient()) is None


def test_summarize_returns_none_on_empty_response():
    assert summarize(_data(), _EmptyClient()) is None
