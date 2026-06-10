import pytest

from execution.alpaca_paper import place_basket
from risk.sizing import SizedPick


def _pick(ticker: str, weight: float) -> SizedPick:
    return SizedPick(ticker=ticker, rank=1, score=1.0, entry_ref=100.0,
                     stop=95.0, atr=2.5, weight=weight, sector="Technology")


def test_place_basket_buys_delta_when_underweight():
    results = place_basket([_pick("AAPL", 0.2)], 100_000, dry_run=True,
                           current_positions={"AAPL": 15_000.0})
    assert len(results) == 1
    assert results[0].side == "buy"
    assert results[0].notional == pytest.approx(5_000.0)


def test_place_basket_sells_delta_when_overweight():
    results = place_basket([_pick("AAPL", 0.2)], 100_000, dry_run=True,
                           current_positions={"AAPL": 25_000.0})
    assert results[0].side == "sell"
    assert results[0].notional == pytest.approx(5_000.0)


def test_place_basket_skips_when_at_target():
    results = place_basket([_pick("AAPL", 0.2)], 100_000, dry_run=True,
                           current_positions={"AAPL": 20_000.0})
    assert results == []


def test_place_basket_full_size_without_positions():
    results = place_basket([_pick("AAPL", 0.2)], 100_000, dry_run=True)
    assert results[0].side == "buy"
    assert results[0].notional == pytest.approx(20_000.0)
