import os
from unittest import mock

import pytest

from news.scanner import NewsItem, fetch_news
from news.analyst import ScreenResult, screen_picks, apply_screening
from risk.sizing import SizedPick


def _pick(ticker: str, weight: float = 0.2) -> SizedPick:
    return SizedPick(ticker=ticker, rank=1, score=1.0, entry_ref=100.0,
                     stop=95.0, atr=2.5, weight=weight, sector="Technology")


def test_fetch_news_no_credentials_returns_empty():
    with mock.patch.dict(os.environ, {}, clear=True):
        result = fetch_news(["AAPL"])
    assert result == {"AAPL": []}


def test_screen_picks_no_api_key_passes_through():
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with mock.patch.dict(os.environ, env, clear=True):
        screens = screen_picks({"AAPL": [], "MSFT": []})
    assert screens["AAPL"].verdict == "CLEAR"
    assert not screens["AAPL"].screened


def test_apply_screening_veto_removes_pick():
    picks = [_pick("AAPL"), _pick("MSFT")]
    screens = {
        "AAPL": ScreenResult("AAPL", "VETO", "earnings tomorrow", True, True),
        "MSFT": ScreenResult("MSFT", "CLEAR", "ok", False, True),
    }
    kept, vetoed = apply_screening(picks, screens)
    assert [p.ticker for p in kept] == ["MSFT"]
    assert [p.ticker for p in vetoed] == ["AAPL"]


def test_apply_screening_caution_halves_weight():
    picks = [_pick("AAPL", weight=0.2)]
    screens = {"AAPL": ScreenResult("AAPL", "CAUTION", "analyst day soon", False, True)}
    kept, vetoed = apply_screening(picks, screens)
    assert kept[0].weight == pytest.approx(0.1)
    assert not vetoed


def test_apply_screening_never_increases_weight():
    picks = [_pick("AAPL", weight=0.2), _pick("MSFT", weight=0.2)]
    screens = {
        "AAPL": ScreenResult("AAPL", "VETO", "scandal", False, True),
        "MSFT": ScreenResult("MSFT", "CLEAR", "ok", False, True),
    }
    kept, _ = apply_screening(picks, screens)
    # vetoed capital stays in cash — MSFT weight unchanged
    assert kept[0].weight == pytest.approx(0.2)


def test_apply_screening_missing_screen_defaults_clear():
    picks = [_pick("AAPL")]
    kept, vetoed = apply_screening(picks, {})
    assert len(kept) == 1 and not vetoed
