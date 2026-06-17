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
        "AAPL": ScreenResult("AAPL", "VETO", "earnings tomorrow", True, True,
                             event_risk_score=0),
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
        "AAPL": ScreenResult("AAPL", "VETO", "scandal", False, True,
                             leadership_score=0),
        "MSFT": ScreenResult("MSFT", "CLEAR", "ok", False, True),
    }
    kept, _ = apply_screening(picks, screens)
    assert kept[0].weight == pytest.approx(0.2)


def test_screen_result_has_subscore_fields():
    r = ScreenResult("AAPL", "CLEAR", "ok", False, True,
                     leadership_score=3, narrative_score=2,
                     macro_score=2, event_risk_score=3,
                     key_risks=["some risk"])
    assert r.leadership_score == 3
    assert r.key_risks == ["some risk"]


def test_apply_screening_missing_screen_defaults_clear():
    picks = [_pick("AAPL")]
    kept, vetoed = apply_screening(picks, {})
    assert len(kept) == 1 and not vetoed


def test_earnings_flag_no_upcoming(monkeypatch):
    """When yfinance returns no earnings within 10d, flag says 'no earnings <10d'."""
    from datetime import date
    import output.picks as op
    op._earnings_cache.clear()
    monkeypatch.setattr("output.picks._fetch_earnings_dates", lambda t: [])
    flag = op._earnings_flag("FAKE", date(2026, 6, 17))
    assert "no earnings" in flag


def test_earnings_flag_imminent(monkeypatch):
    """When yfinance returns an earnings date within 10d, flag warns."""
    from datetime import date
    import output.picks as op
    op._earnings_cache.clear()
    monkeypatch.setattr(
        "output.picks._fetch_earnings_dates",
        lambda t: [date(2026, 6, 24)],
    )
    flag = op._earnings_flag("MU", date(2026, 6, 17))
    assert "EARNINGS" in flag
    assert "7d" in flag


def test_screen_picks_no_api_key_auto_cautions_earnings():
    """Without API key, picks with imminent earnings get CAUTION not CLEAR."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with mock.patch.dict(os.environ, env, clear=True):
        screens = screen_picks(
            {"MU": [], "AAPL": []},
            earnings_flags={"MU": "⚠️ EARNINGS 2026-06-24 (7d)", "AAPL": "no earnings <10d"},
        )
    assert screens["MU"].verdict == "CAUTION"
    assert screens["MU"].earnings_risk is True
    assert screens["AAPL"].verdict == "CLEAR"
