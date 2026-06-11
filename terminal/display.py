"""
Rich terminal UI — live 6-panel dashboard.
Panels: BTC Feed | Force Graph | MiroFish Swarm | Polymarket CLOB | Copy Trading | Risk/P&L
"""
import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from copytrading.engine import CopyTradeRecord
from execution.engine import RiskState, TradeRecord
from feeds.binance_ws import BtcSnapshot
from feeds.indicators import IndicatorSet
from polymarket.clob_client import MarketState
from forcegraph.force_graph import Bias, GraphSignal

if TYPE_CHECKING:
    from copytrading.engine import CopyEngine
    from copytrading.tracker import WalletTracker
    from mirofish.client import MirofishSignal

console = Console()


def _colour_pct(v: float) -> Text:
    style = "green" if v > 0 else "red" if v < 0 else "white"
    return Text(f"{v:+.2%}", style=style)


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
    mf_signal: Optional["MirofishSignal"],
    risk: RiskState,
    history: list[TradeRecord],
    copy_tracker: Optional["WalletTracker"],
    copy_engine: Optional["CopyEngine"],
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
        Layout(name="mid"),
        Layout(name="right"),
    )
    layout["body"]["left"].split_column(
        Layout(name="price_panel"),
    )
    layout["body"]["mid"].split_column(
        Layout(name="signal_panel", ratio=1),
        Layout(name="mirofish_panel", ratio=1),
    )
    layout["body"]["right"].split_column(
        Layout(name="market_panel", ratio=2),
        Layout(name="copy_panel", ratio=3),
        Layout(name="risk_panel", ratio=2),
    )

    # ── header ────────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hdr = Text()
    hdr.append("  POLYMARKET BTC 5MIN SCALPER + COPY TRADING  ", style="bold white on blue")
    hdr.append(f"  {ts}", style="dim white")
    hdr.append(f"  {status_msg}", style="yellow")
    layout["header"].update(Panel(hdr, style="blue"))

    # ── BTC feed panel ────────────────────────────────────────────────────────
    price_table = Table.grid(padding=(0, 2))
    price_table.add_column(style="dim")
    price_table.add_column(style="bold")
    if snap:
        mark_style = "green" if snap.mark_price >= snap.price else "red"
        price_table.add_row("BTC Spot",     f"${snap.price:,.2f}")
        price_table.add_row("Mark Price",   Text(f"${snap.mark_price:,.2f}", style=mark_style))
        price_table.add_row("Mark Premium", f"{snap.mark_spot_spread:+.4%}")
        price_table.add_row("Funding Rate", f"{snap.funding_rate:+.5f}")
        price_table.add_row("Bid/Ask",      f"${snap.bid:,.2f} / ${snap.ask:,.2f}")
        price_table.add_row("OFI",          f"{snap.order_flow_imbalance:+.3f}")
        price_table.add_row("aggTrade",     f"{snap.flow_ratio:.1%} buy "
                                            f"({snap.agg_buy_vol:.2f}B/{snap.agg_sell_vol:.2f}S)")
        if snap.bids and snap.asks:
            price_table.add_row("Depth Bid1",  f"${snap.bids[0].price:,.0f}  {snap.bids[0].qty:.3f}")
            price_table.add_row("Depth Ask1",  f"${snap.asks[0].price:,.0f}  {snap.asks[0].qty:.3f}")
    else:
        price_table.add_row("Status", "Connecting to Binance…")
    layout["price_panel"].update(Panel(price_table, title="[cyan]Binance Feed[/cyan]"))

    # ── force-graph panel ─────────────────────────────────────────────────────
    sig_table = Table.grid(padding=(0, 2))
    sig_table.add_column(style="dim")
    sig_table.add_column()
    if ind and signal:
        sig_table.add_row("Signal",       _bias_text(signal.bias, signal.confidence))
        conv_text = Text("YES", style="green") if signal.converged else Text("NO", style="red")
        sig_table.add_row("Converged",    conv_text)
        sig_table.add_row("Separation",   f"{signal.separation:.2f}x")
        sig_table.add_row("Active Nodes", str(signal.active_nodes))
        sig_table.add_row("Bull/Bear Wt", f"{signal.bull_weight:.2f} / {signal.bear_weight:.2f}")
        lag_style = "bold yellow" if signal.mark_price_lag > 0.003 else "dim"
        sig_table.add_row("Mark Lag",     Text(f"{signal.mark_price_lag:.4f}", style=lag_style))
        sig_table.add_row("RSI",          f"{ind.rsi_14:.1f}")
        sig_table.add_row("StochRSI K/D", f"{ind.stoch_rsi_k:.1f} / {ind.stoch_rsi_d:.1f}")
        sig_table.add_row("MACD Hist",    f"{ind.macd_hist:+.2f}")
        sig_table.add_row("Bull score",   f"{ind.bull_score:.0%}")
        sig_table.add_row("Bear score",   f"{ind.bear_score:.0%}")
    else:
        sig_table.add_row("Status", "Waiting for data…")
    layout["signal_panel"].update(Panel(sig_table, title="[cyan]Force Graph (Mirofish)[/cyan]"))

    # ── MiroFish swarm panel ──────────────────────────────────────────────────
    mf_table = Table.grid(padding=(0, 2))
    mf_table.add_column(style="dim")
    mf_table.add_column()
    if mf_signal is not None:
        if mf_signal.available:
            age_s = mf_signal.age_seconds
            age_str = f"{age_s:.0f}s ago"
            stale_style = "red" if mf_signal.stale else "green"
            mf_table.add_row("Swarm Signal",  _bias_text(mf_signal.bias, mf_signal.confidence))
            mf_table.add_row("Confidence",    Text(f"{mf_signal.confidence:.0%}",
                             style="green" if mf_signal.confidence >= 0.65 else "yellow"))
            mf_table.add_row("Last Run",      Text(age_str, style=stale_style))
            mf_table.add_row("Status",        Text("LIVE", style="green"))
            if mf_signal.reasoning:
                reason = mf_signal.reasoning[:120].replace("\n", " ")
                mf_table.add_row("Reasoning",    Text(reason, style="dim"))
        else:
            mf_table.add_row("Status",   Text("Simulating…", style="yellow"))
            mf_table.add_row("",         Text("(first run takes ~10 min)", style="dim"))
    else:
        mf_table.add_row("Status",   Text("Disabled", style="dim"))
        mf_table.add_row("",         Text("Set MIROFISH_ENABLED=true", style="dim"))
    layout["mirofish_panel"].update(Panel(mf_table, title="[magenta]MiroFish Swarm[/magenta]"))

    # ── Polymarket CLOB panel ─────────────────────────────────────────────────
    mkt_table = Table.grid(padding=(0, 2))
    mkt_table.add_column(style="dim")
    mkt_table.add_column(style="bold")
    if market:
        mkt_table.add_row("YES Bid/Ask", f"{market.yes_bid:.3f} / {market.yes_ask:.3f}")
        mkt_table.add_row("NO  Bid/Ask", f"{market.no_bid:.3f} / {market.no_ask:.3f}")
        mkt_table.add_row("YES Mid",     f"{market.mid_yes:.3f}")
        mkt_table.add_row("NO  Mid",     f"{market.mid_no:.3f}")
        mkt_table.add_row("YES Liq",     f"${market.yes_ask_size * market.yes_ask:.0f}")
        mkt_table.add_row("NO  Liq",     f"${market.no_ask_size * market.no_ask:.0f}")
    else:
        mkt_table.add_row("Status", "Connecting…")
    layout["market_panel"].update(Panel(mkt_table, title="[cyan]Polymarket CLOB[/cyan]"))

    # ── Copy trading panel ────────────────────────────────────────────────────
    copy_table = Table.grid(padding=(0, 1))
    copy_table.add_column(style="dim", width=3)   # rank
    copy_table.add_column(width=10)               # username
    copy_table.add_column(width=8)                # market (truncated)
    copy_table.add_column(width=5)                # side/outcome
    copy_table.add_column(style="bold", width=7)  # size

    if copy_tracker is not None:
        wallets = copy_tracker.wallets
        n_wallets = len(wallets)
        copy_table.add_row(
            Text(f"Tracking {n_wallets} wallets", style="bold cyan"),
            "", "", "", "",
        )
        copy_table.add_row("", "", "", "", "")  # spacer
    else:
        copy_table.add_row(Text("Disabled", style="dim"), "", "", "", "")

    if copy_engine is not None:
        ch = copy_engine.history
        executed = [r for r in ch if not r.skipped]
        skipped  = [r for r in ch if r.skipped]
        copy_table.add_row(
            Text(f"Copied: {len(executed)}  Skipped: {len(skipped)}", style="dim"),
            "", "", "", "",
        )
        copy_table.add_row("", "", "", "", "")  # spacer

        # show last 5 executed trades, newest first
        recent = list(reversed(executed[-5:])) if executed else []
        if recent:
            copy_table.add_row(
                Text("#", style="dim"), Text("Wallet", style="dim"),
                Text("Market", style="dim"), Text("Side", style="dim"),
                Text("$Size", style="dim"),
            )
            for rec in recent:
                side_style = "green" if rec.side == "BUY" else "red"
                copy_table.add_row(
                    Text(str(rec.source_rank), style="dim"),
                    Text(rec.source_username[:10], style="cyan"),
                    Text(rec.market_title[:8], style="dim"),
                    Text(f"{rec.side[:1]} {rec.outcome[:2]}", style=side_style),
                    Text(f"${rec.size_usd:.0f}", style="bold green"),
                )
        else:
            copy_table.add_row(
                Text("No trades yet", style="dim"), "", "", "", "",
            )

        # last skipped reason
        if skipped:
            last_skip = skipped[-1]
            copy_table.add_row("", "", "", "", "")
            copy_table.add_row(
                Text(f"Last skip: {last_skip.skip_reason[:28]}", style="dim yellow"),
                "", "", "", "",
            )
    layout["copy_panel"].update(
        Panel(copy_table, title="[yellow]Copy Trading[/yellow]")
    )

    # ── Risk / P&L panel ──────────────────────────────────────────────────────
    risk_table = Table.grid(padding=(0, 2))
    risk_table.add_column(style="dim")
    risk_table.add_column()
    risk_table.add_row("Balance",  f"${risk.balance:,.2f}")
    risk_table.add_row("Day P&L",  _colour_pct(risk.daily_pnl_pct))
    risk_table.add_row("Trades",   str(risk.trades_today))
    risk_table.add_row("W / L",    f"{risk.wins} / {risk.losses}")
    win_rate = risk.wins / risk.trades_today if risk.trades_today > 0 else 0.0
    risk_table.add_row("Win rate", f"{win_rate:.0%}")

    if history:
        last = history[-1]
        pnl_pct = last.pnl / (last.entry_price * last.size + 1e-9)
        risk_table.add_row("Last trade",  _colour_pct(pnl_pct))
        risk_table.add_row("Hold time",   f"{last.hold_ms / 1000:.1f}s")
        risk_table.add_row("Lag@entry",   f"{last.lag_at_entry:.3f}")
        risk_table.add_row("Edge age",    f"{last.edge_age_ms}ms")
        risk_table.add_row("Exit reason", last.reason[:28])

    if risk.halted:
        risk_table.add_row("HALTED", Text(risk.halt_reason, style="bold red"))

    layout["risk_panel"].update(Panel(risk_table, title="[cyan]Risk / P&L[/cyan]"))

    # ── footer ────────────────────────────────────────────────────────────────
    footer = Text(
        "  Ctrl-C: quit  |  Arb: Binance mark price + MiroFish  |  "
        "Copy: top-20 leaderboard wallets  |  0.5% risk  |  2% daily cap  |  -0.4% stop",
        style="dim"
    )
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
        mf_signal: Optional["MirofishSignal"],
        risk: RiskState,
        history: list[TradeRecord],
        copy_tracker: Optional["WalletTracker"] = None,
        copy_engine: Optional["CopyEngine"] = None,
        status: str = "",
    ) -> None:
        if self._live:
            layout = build_layout(snap, ind, market, signal, mf_signal,
                                  risk, history, copy_tracker, copy_engine, status)
            self._live.update(layout)
