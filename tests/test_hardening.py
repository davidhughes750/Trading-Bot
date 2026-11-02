"""Tests for secret redaction in logs and tolerant parsing of AI responses."""

from __future__ import annotations

import logging

import pytest

from bot.ai_manager import AIPortfolioManager, _coerce_number
from bot.config import Config
from bot.models import Side, Signal, SignalAction, StockRecommendation
from bot.utils import RedactSecretsFilter, redact_secrets

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIzaSyD-FAKEFAKEFAKEFAKEFAKE12345"
TELEGRAM_URL = "https://api.telegram.org/bot123456789:AAEFAKEFAKEFAKEFAKEFAKEFAKEFAKE12345/getUpdates"


def test_redact_secrets_blanks_keys_and_tokens_but_keeps_the_rest():
    out = redact_secrets(f"HTTPSConnectionPool: Max retries exceeded with url: {GEMINI_URL} (Caused by timeout)")
    assert "AIzaSy" not in out and "key=***" in out and "Caused by timeout" in out
    out = redact_secrets(f"POST {TELEGRAM_URL} failed")
    assert "AAEFAKE" not in out and "/bot***/getUpdates" in out
    assert redact_secrets("Total Equity=£474.61 | Free Cash=£474.61") == "Total Equity=£474.61 | Free Cash=£474.61"
    assert redact_secrets("a=1&key=abc&b=2").endswith("&b=2")  # only the secret value is replaced


def test_log_filter_scrubs_messages_arguments_and_tracebacks():
    logger = logging.getLogger("redaction-test")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(self.format(record))

    handler = Capture()
    handler.addFilter(RedactSecretsFilter())
    logger.addHandler(handler)
    try:
        logger.warning("Gemini call failed (%s)", GEMINI_URL)
        try:
            raise RuntimeError(f"request to {TELEGRAM_URL} failed")
        except RuntimeError:
            logger.exception("Telegram poll failed")
    finally:
        logger.removeHandler(handler)
    text = "\n".join(records)
    assert "AIzaSy" not in text and "AAEFAKE" not in text
    assert "Gemini call failed" in text and "Traceback" in text  # the useful parts survive


@pytest.mark.parametrize("raw,expected", [(None, 80), ("92", 92), (95.7, 95), ("high", 80), (250, 100), (-5, 1), (float("nan"), 80)])
def test_coerce_number_survives_bad_model_output(raw, expected):
    assert _coerce_number(raw, 80, 1, 100, as_int=True) == expected


def test_gemini_answer_with_null_fields_is_still_used(tmp_path, monkeypatch):
    cfg = Config(execution_mode="paper", gemini_api_key="AIzaFake", ai_decisions_file=str(tmp_path / "ai.json"))
    ai = AIPortfolioManager(cfg)
    sig = Signal("NVDA_US_EQ", SignalAction.BUY, "t", 200.0, 201.0, 200.0, 60.0, 2.0, "x", Side.LONG)
    pick = StockRecommendation(
        symbol="NVDA_US_EQ", score=90.0, rating="STRONG BUY", actionable=True, close_price=200.0, ema_fast=201.0,
        ema_slow=200.0, rsi=60.0, atr=2.0, rvol=1.5, roc_10_pct=1.0, suggested_stop_loss=197.0,
        suggested_take_profit=204.0, thesis="t", signal=sig,
    )
    monkeypatch.setattr(ai, "_invoke_gemini_json", lambda prompt: {"decision": "VETO", "confidence": None, "size_multiplier": None, "reasoning": None})
    monkeypatch.setattr(ai, "fetch_recent_headlines", lambda symbol, max_items=5: [])
    dec = ai.evaluate_entry_candidate(pick, {}, 10_000.0)
    # Before the fix this raised inside Gemini parsing and silently fell back to the keyword engine
    assert dec.engine == cfg.gemini_model
    assert dec.decision == "VETO" and dec.confidence == 80 and dec.size_multiplier == 1.0
