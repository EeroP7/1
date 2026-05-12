"""
Fetches top Polymarket wallets from the public data API.

Endpoints used:
  GET https://data-api.polymarket.com/profiles
      ?sortBy=profit&timeframe=all&limit=50

Returns ranked wallet addresses with their P&L and volume so the
monitor can decide which ones to follow.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import structlog

log = structlog.get_logger()

DATA_API = "https://data-api.polymarket.com"


@dataclass
class WalletProfile:
    address: str
    name: str
    profit_usdc: float
    volume_usdc: float
    positions_count: int
    rank: int


class Leaderboard:
    """
    Fetches and caches the top-N wallets by all-time profit.
    Refreshes every `refresh_interval` seconds.

    You can also pin specific wallets (e.g. Gravia) via `pinned_addresses`
    — those are always included regardless of rank.
    """

    def __init__(
        self,
        top_n: int = 20,
        refresh_interval: int = 3600,          # re-rank every hour
        pinned_addresses: list[str] | None = None,
        timeframe: str = "all",                # "all" | "1d" | "1w" | "1m"
    ) -> None:
        self._top_n = top_n
        self._refresh_interval = refresh_interval
        self._pinned = [a.lower() for a in (pinned_addresses or [])]
        self._timeframe = timeframe
        self._wallets: list[WalletProfile] = []
        self._last_refresh: float = 0.0
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        )
        await self._refresh()

    async def stop(self) -> None:
        if self._session:
            await self._session.close()

    async def get_wallets(self) -> list[WalletProfile]:
        if time.time() - self._last_refresh > self._refresh_interval:
            await self._refresh()
        return list(self._wallets)

    async def _refresh(self) -> None:
        fetched = await self._fetch_leaderboard()
        pinned = await self._fetch_pinned()

        seen = {w.address.lower() for w in fetched}
        for p in pinned:
            if p.address.lower() not in seen:
                fetched.append(p)

        self._wallets = fetched
        self._last_refresh = time.time()
        log.info("leaderboard_refreshed", count=len(self._wallets))

    async def _fetch_leaderboard(self) -> list[WalletProfile]:
        if not self._session:
            return []
        url = f"{DATA_API}/profiles"
        params = {
            "sortBy": "profit",
            "timeframe": self._timeframe,
            "limit": self._top_n,
        }
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    log.warning("leaderboard_fetch_failed", status=resp.status)
                    return []
                data = await resp.json()
            return [self._parse_profile(i + 1, p) for i, p in enumerate(data)]
        except Exception as exc:
            log.warning("leaderboard_error", error=str(exc))
            return []

    async def _fetch_pinned(self) -> list[WalletProfile]:
        if not self._pinned or not self._session:
            return []
        results = []
        for addr in self._pinned:
            profile = await self._fetch_single_profile(addr)
            if profile:
                profile.rank = 0   # pinned = always followed
                results.append(profile)
        return results

    async def _fetch_single_profile(self, address: str) -> Optional[WalletProfile]:
        url = f"{DATA_API}/profiles"
        params = {"address": address}
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
            if isinstance(data, list) and data:
                return self._parse_profile(0, data[0])
            if isinstance(data, dict):
                return self._parse_profile(0, data)
        except Exception:
            return None

    @staticmethod
    def _parse_profile(rank: int, raw: dict) -> WalletProfile:
        return WalletProfile(
            address=raw.get("proxyWallet") or raw.get("address", ""),
            name=raw.get("name") or raw.get("username") or "anonymous",
            profit_usdc=float(raw.get("profit", 0) or 0),
            volume_usdc=float(raw.get("volume", 0) or 0),
            positions_count=int(raw.get("positionsCount", 0) or 0),
            rank=rank,
        )
