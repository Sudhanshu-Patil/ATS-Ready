"""
app/services/llm_client.py
──────────────────────────
One place that talks to the LLM provider, built for free-tier limits:

  * token governor  — waits instead of sending a request that would 429
  * fallback models — Groq limits are per model, so on 429/5xx/timeouts the
                      next model in LLM_FALLBACK_MODELS answers immediately
  * Retry-After     — honoured when every model is rate-limited
  * 413             — "request too large" is raised as LLMContextTooLarge so
                      the caller can shrink the prompt (no wait can fix it)
  * truncation      — finish_reason == "length" / empty body is a failure,
                      not silently-broken JSON
"""
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from app.config import settings
from app.services.compaction import estimate_tokens

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """Every configured model failed (rate limit, outage, truncation)."""


class LLMContextTooLarge(Exception):
    """The prompt exceeds a model's request limit; shrink it and retry."""


class _BadOutput(Exception):
    pass


class TokenGovernor:
    """Sliding 60 s window of tokens sent to one model."""

    def __init__(self, budget_per_min: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.budget, self.clock, self.sleep = budget_per_min, clock, sleep
        self._entries: List[List[float]] = []     # [timestamp, tokens]
        self._lock = threading.Lock()

    def acquire(self, tokens: int) -> List[float]:
        if self.budget <= 0:
            return [0.0, 0.0]
        while True:
            with self._lock:
                now = self.clock()
                self._entries = [e for e in self._entries if now - e[0] < 60]
                used = sum(e[1] for e in self._entries)
                # An empty window always admits one request, even an oversized one.
                if not self._entries or used + tokens <= self.budget:
                    entry = [now, float(tokens)]
                    self._entries.append(entry)
                    return entry
                wait = self._entries[0][0] + 60 - now
            logger.info("LLM governor: waiting %.1fs for token budget", wait)
            self.sleep(max(wait, 0.5))

    def settle(self, entry: List[float], actual_tokens: Optional[int]) -> None:
        """Replace the reservation with what the provider actually counted."""
        if actual_tokens is not None and self.budget > 0:
            entry[1] = float(actual_tokens)


def _retry_after(exc: Exception) -> float:
    try:
        return float(exc.response.headers.get("retry-after", 0))     # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        return 0.0


class LLMClient:
    def __init__(self, client: Optional[OpenAI] = None,
                 sleep: Callable[[float], None] = time.sleep):
        # max_retries=0: retries are decided here (fallback first, then wait).
        self.client = client or OpenAI(
            api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL,
            max_retries=0, timeout=settings.LLM_TIMEOUT,
        )
        self.sleep = sleep
        self._governors: Dict[str, TokenGovernor] = {}

    def models(self) -> List[str]:
        extra = [m.strip() for m in settings.LLM_FALLBACK_MODELS.split(",") if m.strip()]
        return [settings.MODEL] + [m for m in extra if m != settings.MODEL]

    def _governor(self, model: str) -> TokenGovernor:
        if model not in self._governors:
            self._governors[model] = TokenGovernor(settings.LLM_TPM_BUDGET, sleep=self.sleep)
        return self._governors[model]

    def _once(self, model: str, system: str, user: str, max_tokens: int) -> str:
        extra_body = {}
        if settings.LLM_REASONING_EFFORT and model.startswith("openai/gpt-oss"):
            extra_body["reasoning_effort"] = settings.LLM_REASONING_EFFORT
        resp = self.client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            extra_body=extra_body,
        )
        usage = getattr(resp, "usage", None)
        self._last_usage = getattr(usage, "total_tokens", None)
        choice = resp.choices[0]
        if choice.finish_reason == "length" or not choice.message.content:
            raise _BadOutput(f"{model}: finish_reason={choice.finish_reason!r}, "
                             f"empty={not choice.message.content}")
        return choice.message.content

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        models = self.models()
        estimate = estimate_tokens(system + user) + max_tokens
        last: Optional[Exception] = None

        for rnd in range(settings.LLM_ROUNDS):
            wait_hint, too_large = 0.0, 0
            for model in models:
                gov = self._governor(model)
                entry = gov.acquire(estimate)
                self._last_usage = None
                try:
                    out = self._once(model, system, user, max_tokens)
                    gov.settle(entry, self._last_usage)
                    if model != models[0]:
                        logger.warning("LLM answered via fallback model %s", model)
                    return out
                except APIStatusError as exc:
                    last = exc
                    if exc.status_code == 413:
                        too_large += 1
                    elif exc.status_code == 429 or exc.status_code >= 500:
                        wait_hint = max(wait_hint, _retry_after(exc))
                    elif model != models[0] and exc.status_code in (400, 404, 422):
                        pass                          # fallback unsupported/unknown: skip it
                    else:
                        raise                         # 401/403/bad request on primary: a bug
                    logger.warning("LLM %s failed: HTTP %s", model, exc.status_code)
                except (APITimeoutError, APIConnectionError, _BadOutput) as exc:
                    last = exc
                    logger.warning("LLM %s failed: %r", model, exc)

            if too_large == len(models):
                raise LLMContextTooLarge(str(last)) from last
            if rnd < settings.LLM_ROUNDS - 1:
                self.sleep(min(30.0, max(wait_hint, 5.0 * (rnd + 1))))

        raise LLMUnavailable(f"All LLM models failed: {last!r}") from last
