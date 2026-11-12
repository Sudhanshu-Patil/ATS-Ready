"""LLM client: fallback models, Retry-After, 413, truncation, token governor."""
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError, APITimeoutError, RateLimitError

from app.config import settings
from app.services.llm_client import (
    LLMClient, LLMContextTooLarge, LLMUnavailable, TokenGovernor,
)

REQ = httpx.Request("POST", "https://llm.test/v1/chat/completions")


def status_error(code, retry_after=None):
    headers = {"retry-after": str(retry_after)} if retry_after else {}
    resp = httpx.Response(code, request=REQ, headers=headers)
    cls = RateLimitError if code == 429 else APIStatusError
    return cls(f"http {code}", response=resp, body=None)


def reply(text="{}", finish="stop", tokens=100):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=finish)],
                           usage=SimpleNamespace(total_tokens=tokens))


class FakeProvider:
    """script: {model: [outcome, ...]} - Exception instances are raised."""
    def __init__(self, script):
        self.script, self.calls = script, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, **kw):
        self.calls.append(model)
        outcome = self.script[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "MODEL", "main")
    monkeypatch.setattr(settings, "LLM_FALLBACK_MODELS", "backup")
    monkeypatch.setattr(settings, "LLM_TPM_BUDGET", 0)
    monkeypatch.setattr(settings, "LLM_ROUNDS", 3)


def client(script):
    sleeps = []
    c = LLMClient(client=FakeProvider(script), sleep=sleeps.append)
    return c, sleeps


def test_primary_ok():
    c, sleeps = client({"main": [reply('{"a":1}')]})
    assert c.complete("s", "u") == '{"a":1}'
    assert c.client.calls == ["main"] and sleeps == []


def test_rate_limit_falls_back_without_waiting():
    c, sleeps = client({"main": [status_error(429)], "backup": [reply("ok")]})
    assert c.complete("s", "u") == "ok"
    assert c.client.calls == ["main", "backup"] and sleeps == []


def test_all_rate_limited_waits_retry_after_then_succeeds():
    c, sleeps = client({"main": [status_error(429, 12), reply("late")],
                        "backup": [status_error(429, 7)]})
    assert c.complete("s", "u") == "late"
    assert sleeps == [12.0]


def test_wait_is_capped():
    c, sleeps = client({"main": [status_error(429, 500), reply("x")], "backup": [status_error(429)]})
    c.complete("s", "u")
    assert sleeps == [30.0]


def test_timeout_and_5xx_are_retryable():
    c, _ = client({"main": [APITimeoutError(request=REQ)], "backup": [status_error(503), ]})
    c.client.script["main"].append(reply("recovered"))
    assert c.complete("s", "u") == "recovered"


def test_413_everywhere_raises_context_too_large_without_waiting():
    c, sleeps = client({"main": [status_error(413)], "backup": [status_error(413)]})
    with pytest.raises(LLMContextTooLarge):
        c.complete("s", "u")
    assert sleeps == []


def test_truncated_output_moves_to_next_model():
    c, _ = client({"main": [reply('{"cut', finish="length")], "backup": [reply("full")]})
    assert c.complete("s", "u") == "full"


def test_empty_body_is_a_failure():
    c, _ = client({"main": [reply(None)], "backup": [reply("full")]})
    assert c.complete("s", "u") == "full"


def test_auth_error_on_primary_is_not_swallowed():
    c, _ = client({"main": [status_error(401)], "backup": [reply("never")]})
    with pytest.raises(APIStatusError):
        c.complete("s", "u")
    assert c.client.calls == ["main"]


def test_unknown_fallback_model_is_skipped():
    c, _ = client({"main": [status_error(429), reply("again")], "backup": [status_error(404)]})
    assert c.complete("s", "u") == "again"


def test_everything_down_raises_unavailable():
    script = {"main": [status_error(503)] * 3, "backup": [status_error(503)] * 3}
    c, sleeps = client(script)
    with pytest.raises(LLMUnavailable):
        c.complete("s", "u")
    assert len(sleeps) == 2        # between the 3 rounds, none after the last


def test_governor_waits_for_window_then_admits():
    now, slept = [0.0], []

    def sleep(s):
        slept.append(s)
        now[0] += s

    g = TokenGovernor(1000, clock=lambda: now[0], sleep=sleep)
    g.acquire(800)
    now[0] = 10
    g.acquire(800)                      # 800 + 800 > 1000: must wait for the first to age out
    assert slept == [50.0]


def test_governor_settle_frees_unused_reservation():
    now = [0.0]
    g = TokenGovernor(1000, clock=lambda: now[0], sleep=lambda s: pytest.fail("should not wait"))
    entry = g.acquire(900)
    g.settle(entry, 100)                # the call really used 100
    g.acquire(800)


def test_governor_admits_oversized_request_on_empty_window():
    g = TokenGovernor(1000, sleep=lambda s: pytest.fail("should not wait"))
    g.acquire(5000)
