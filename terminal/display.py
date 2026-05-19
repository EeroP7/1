"""
Rich terminal UI — live dashboard showing price feed, graph signal,
active position, and P&L summary.
"""
import time
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from execution.engine import RiskState, TradeRecord
from feeds.binance_ws import BtcSnapshot
from feeds.indicators import IndicatorSet
from polymarket.clob_client import MarketState
from signal.force_graph import Bias, GraphSignal


console = Console()


def _colour_pct(v: float) -> Text:
    pct = f"{v:+.2%}"
    style = "green" if v > 0 else "red" if v < 0 else "white"
    return Text(pct, style=style)


def _bias_text(bias: Bias, conf: float) -> Text:
    if bias == Bias.BULL:
        return Text(f"BULL  {conf:.0%}", style="bold green")
    if bias == Bias.BEAR:
        return Text(f"BEAR  {conf:.0%}", style="bold red")
    return Text("NEUTRAL", style="dim white")


def build_layout(
    snap: Optional[BtcSnapshot],
    ind: Optional[IndicatorSet],
    market: Optional[MarketState],
    signal: Optional[GraphSignal],
    risk: RiskState,
    history: list[TradeRecord],
    status_msg: str,
) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )
    layout["body"]["left"].split_column(
        Layout(name="price_panel", ratio=2),
        Layout(name="signal_panel", ratio=3),
    )
    layout["body"]["right"].split_column(
        Layout(name="market_panel", ratio=2),
        Layout(name="risk_panel", ratio=3),
    )

    # ── header ────────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    header_text = Text()
    header_text.append("  POLYMARKET BTC 5MIN SCALPER  ", style="bold white on blue")
    header_text.append(f"  {ts}", style="dim white")
    header_text.append(f"  {status_msg}", style="yellow")
    layout["header"].update(Panel(header_text, style="blue"))

    # ── price panel ───────────────────────────────────────────────────────────
    price_table = Table.grid(padding=(0, 2))
    price_table.add_column(style="dim")
    price_table.add_column(style="bold")
    if snap:
        price_table.add_row("BTC Spot",   f"${snap.price:,.2f}")
        price_table.add_row("Bid/Ask",    f"${snap.bid:,.2f} / ${snap.ask:,.2f}")
        price_table.add_row("Bid Qty",    f"{snap.bid_qty:.4f}")
        price_table.add_row("Ask Qty",    f"{snap.ask_qty:.4f}")
        price_table.add_row("OFI",        f"{snap.order_flow_imbalance:+.3f}")
        price_table.add_row("Buy Ratio",  f"{snap.buy_ratio:.1%}")
    else:
        price_table.add_row("Status", "Connecting…")
    layout["price_panel"].update(Panel(price_table, title="[cyan]BTC Feed[/cyan]"))

    # ── signal panel ──────────────────────────────────────────────────────────
    sig_table = Table.grid(padding=(0, 2))
    sig_table.add_column(style="dim")
    sig_table.add_column()
    if ind and signal:
        sig_table.add_row("Signal",     _bias_text(signal.bias, signal.confidence))
        sig_table.add_row("Active Nodes", str(signal.active_nodes))
        sig_table.add_row("Bull/Bear Wt",
                          f"{signal.bull_weight:.2f} / {signal.bear_weight:.2f}")
        sig_table.add_row("RSI",        f"{ind.rsi_14:.1f}")
        sig_table.add_row("StochRSI K/D", f"{ind.stoch_rsi_k:.1f} / {ind.stoch_rsi_d:.1f}")
        sig_table.add_row("MACD Hist",  f"{ind.macd_hist:+.2f}")
        sig_table.add_row("BB %B",      f"{ind.bb_pct_b:.2f}")
        sig_table.add_row("OBV delta",  f"{ind.obv:+.3f}")
        sig_table.add_row("Bull score", f"{ind.bull_score:.0%}")
        sig_table.add_row("Bear score", f"{ind.bear_score:.0%}")
    else:
        sig_table.add_row("Status", "Waiting for data…")
    layout["signal_panel"].update(Panel(sig_table, title="[cyan]Force Graph[/cyan]"))

    # ── market panel ──────────────────────────────────────────────────────────
    mkt_table = Table.grid(padding=(0, 2))
    mkt_table.add_column(style="dim")
    mkt_table.add_column(style="bold")
    if market:
        mkt_table.add_row("YES Bid/Ask",
                          f"{market.yes_bid:.3f} / {market.yes_ask:.3f}")
        mkt_table.add_row("NO  Bid/Ask",
                          f"{market.no_bid:.3f} / {market.no_ask:.3f}")
        mkt_table.add_row("YES Mid",    f"{market.mid_yes:.3f}")
        mkt_table.add_row("NO  Mid",    f"{market.mid_no:.3f}")
        mkt_table.add_row("YES Liq",    f"${market.yes_ask_size * market.yes_ask:.0f}")
        mkt_table.add_row("NO  Liq",    f"${market.no_ask_size * market.no_ask:.0f}")
    else:
        mkt_table.add_row("Status", "Connecting…")
    layout["market_panel"].update(Panel(mkt_table, title="[cyan]Polymarket CLOB[/cyan]"))

    # ── risk / P&L panel ──────────────────────────────────────────────────────
    risk_table = Table.grid(padding=(0, 2))
    risk_table.add_column(style="dim")
    risk_table.add_column()
    risk_table.add_row("Balance",   f"${risk.balance:,.2f}")
    risk_table.add_row("Day P&L",   _colour_pct(risk.daily_pnl_pct))
    risk_table.add_row("Trades",    str(risk.trades_today))
    risk_table.add_row("W / L",     f"{risk.wins} / {risk.losses}")
    win_rate = (
        risk.wins / risk.trades_today if risk.trades_today > 0 else 0.0
    )
    risk_table.add_row("Win rate",  f"{win_rate:.0%}")

    if history:
        last = history[-1]
        risk_table.add_row("Last trade",
                           _colour_pct(last.pnl / (last.entry_price * last.size)))
        risk_table.add_row("Hold time",  f"{last.hold_ms / 1000:.1f}s")
        risk_table.add_row("Exit reason", last.reason[:30])

    if risk.halted:
        risk_table.add_row("⛔ HALTED", Text(risk.halt_reason, style="bold red"))

    layout["risk_panel"].update(Panel(risk_table, title="[cyan]Risk / P&L[/cyan]"))

    # ── footer ────────────────────────────────────────────────────────────────
    footer = Text("  q: quit  |  Polymarket BTC UP/DOWN 5MIN scalper  "
                  "|  per-trade risk 0.5%  |  daily cap 2%  |  hard stop -0.4%",
                  style="dim")
    layout["footer"].update(Panel(footer, style="dim"))

    return layout


class Dashboard:
    def __init__(self) -> None:
        self._live: Optional[Live] = None

    def __enter__(self):
        self._live = Live(console=console, refresh_per_second=10,
                          screen=True, transient=False)
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.__exit__(*args)

    def update(
        self,
        snap: Optional[BtcSnapshot],
        ind: Optional[IndicatorSet],
        market: Optional[MarketState],
        signal: Optional[GraphSignal],
        risk: RiskState,
        history: list[TradeRecord],
        status: str = "",
    ) -> None:
        if self._live:
            layout = build_layout(snap, ind, market, signal,
                                  risk, history, status)
            self._live.update(layout)
