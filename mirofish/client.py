"""
MiroFish REST API client.

Runs the full MiroFish pipeline against a generated BTC market context doc:

  1. POST /ontology/generate   — upload context doc + requirement
  2. POST /graph/build         — build GraphRAG knowledge graph
  3. POST /simulation/create   — create simulation
  4. POST /simulation/prepare  — generate agent profiles (async, poll)
  5. POST /simulation/run      — start OASIS swarm simulation (async, poll)
  6. POST /api/report/generate — generate analysis report  (async, poll)
  7. POST /api/report/chat     — ask for numerical UP probability

Results are cached for MIROFISH_REFRESH_MIN minutes.  Callers should
check `client.signal` which is updated in a background task.

If MiroFish is not reachable the client falls back gracefully: signal
stays NEUTRAL with confidence=0 so the execution engine never blocks.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from config import (
    MIROFISH_HOST, MIROFISH_ENABLED, MIROFISH_REFRESH_MIN,
    MIROFISH_MIN_CONFIDENCE,
)
from feeds.binance_ws import BtcSnapshot
from feeds.indicators import IndicatorSet
from mirofish.context_builder import build_context, build_requirement
from signal.force_graph import Bias

log = logging.getLogger(__name__)

POLL_INTERVAL   = 5     # seconds between status polls
POLL_TIMEOUT    = 600   # give up after 10 minutes


@dataclass
class MirofishSignal:
    bias: Bias          = Bias.NEUTRAL
    confidence: float   = 0.0          # 0-1
    agent_count: int    = 0
    reasoning: str      = ""
    last_updated: float = 0.0          # time.time()
    available: bool     = False        # False if MiroFish unreachable

    @property
    def age_seconds(self) -> float:
        return time.time() - self.last_updated if self.last_updated else 9999.0

    @property
    def stale(self) -> bool:
        return self.age_seconds > MIROFISH_REFRESH_MIN * 60


class MirofishClient:
    """
    Manages the MiroFish simulation pipeline and exposes a cached signal.
    Runs as a long-lived background task refreshing every MIROFISH_REFRESH_MIN.
    """

    def __init__(self) -> None:
        self.signal   = MirofishSignal()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, snap: BtcSnapshot, ind: IndicatorSet) -> None:
        if not MIROFISH_ENABLED:
            log.info("MiroFish disabled in config — skipping")
            return
        self._session = aiohttp.ClientSession(base_url=MIROFISH_HOST)
        # run an initial simulation immediately, then refresh on schedule
        self._task = asyncio.create_task(
            self._refresh_loop(snap, ind)
        )

    async def update_context(self, snap: BtcSnapshot, ind: IndicatorSet) -> None:
        """Called by main loop so the client always has the latest snapshot."""
        self._latest_snap = snap
        self._latest_ind  = ind

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._session:
            await self._session.close()

    # ── background refresh loop ───────────────────────────────────────────────

    async def _refresh_loop(self, snap: BtcSnapshot, ind: IndicatorSet) -> None:
        self._latest_snap = snap
        self._latest_ind  = ind
        while True:
            try:
                await self._run_simulation(self._latest_snap, self._latest_ind)
            except Exception as exc:
                log.warning(f"MiroFish simulation failed: {exc}")
                self.signal.available = False
            await asyncio.sleep(MIROFISH_REFRESH_MIN * 60)

    # ── full simulation pipeline ──────────────────────────────────────────────

    async def _run_simulation(self, snap: BtcSnapshot, ind: IndicatorSet) -> None:
        context_doc = build_context(snap, ind)
        requirement = build_requirement(snap)

        log.info("MiroFish: uploading context document…")
        project_id, graph_id = await self._upload_and_build_graph(
            context_doc, requirement
        )

        log.info(f"MiroFish: graph built (project={project_id}), creating simulation…")
        sim_id = await self._create_and_prepare_simulation(project_id, graph_id)

        log.info(f"MiroFish: running swarm simulation (sim={sim_id})…")
        await self._run_oasis(sim_id)

        log.info("MiroFish: generating report…")
        report_id = await self._generate_report(sim_id)

        log.info(f"MiroFish: querying report for probability (report={report_id})…")
        bias, confidence, reasoning = await self._extract_probability(report_id)

        self.signal = MirofishSignal(
            bias=bias,
            confidence=confidence,
            agent_count=MIROFISH_REFRESH_MIN,  # proxy; real count from sim metadata
            reasoning=reasoning,
            last_updated=time.time(),
            available=True,
        )
        log.info(
            f"MiroFish signal: {bias.value} {confidence:.0%}  —  {reasoning[:80]}"
        )

    # ── step 1+2: upload doc → build graph ───────────────────────────────────

    async def _upload_and_build_graph(
        self, context_doc: str, requirement: str
    ) -> tuple[str, str]:
        # Upload document as multipart
        form = aiohttp.FormData()
        form.add_field("files", context_doc.encode(),
                       filename="btc_context.md",
                       content_type="text/markdown")
        form.add_field("simulation_requirement", requirement)
        form.add_field("project_name", "BTC_5MIN_SCALPER")

        async with self._session.post("/ontology/generate", data=form) as r:
            r.raise_for_status()
            data = await r.json()
        project_id = data["project_id"]

        # Build graph
        async with self._session.post("/graph/build", json={
            "project_id": project_id,
            "graph_name": "btc_graph",
            "chunk_size": 300,
            "chunk_overlap": 30,
        }) as r:
            r.raise_for_status()
            bdata = await r.json()
        task_id = bdata["task_id"]
        graph_id = await self._poll_task(f"/graph/build/status/{task_id}",
                                         result_key="graph_id")
        return project_id, graph_id

    # ── step 3+4: create + prepare simulation ────────────────────────────────

    async def _create_and_prepare_simulation(
        self, project_id: str, graph_id: str
    ) -> str:
        async with self._session.post("/simulation/create", json={
            "project_id": project_id,
            "graph_id":   graph_id,
        }) as r:
            r.raise_for_status()
            data = await r.json()
        sim_id = data["simulation_id"]

        async with self._session.post("/simulation/prepare", json={
            "simulation_id": sim_id,
        }) as r:
            r.raise_for_status()
            pdata = await r.json()
        task_id = pdata["task_id"]
        await self._poll_task(f"/simulation/prepare/status",
                              post_body={"task_id": task_id})
        return sim_id

    # ── step 5: run OASIS simulation ──────────────────────────────────────────

    async def _run_oasis(self, sim_id: str) -> None:
        """
        Triggers the OASIS swarm run.  The exact endpoint varies by MiroFish
        version — we try /simulation/run first, then /simulation/<id>/run.
        Polls until status == 'completed'.
        """
        for endpoint in (
            "/simulation/run",
            f"/simulation/{sim_id}/run",
        ):
            try:
                async with self._session.post(endpoint, json={
                    "simulation_id": sim_id,
                    "max_rounds": 10,
                    "platform": "twitter",
                }) as r:
                    if r.status == 404:
                        continue
                    r.raise_for_status()
                    rdata = await r.json()
                task_id = rdata.get("task_id")
                if task_id:
                    await self._poll_task(f"/simulation/run/status",
                                          post_body={"task_id": task_id})
                else:
                    # Might be synchronous or already running — poll sim status
                    await self._poll_simulation_status(sim_id)
                return
            except aiohttp.ClientError:
                continue

        # Fallback: just wait for simulation status to be completed
        await self._poll_simulation_status(sim_id)

    async def _poll_simulation_status(self, sim_id: str) -> None:
        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            async with self._session.get(f"/simulation/{sim_id}") as r:
                if r.status == 200:
                    data = await r.json()
                    status = data.get("status", "")
                    if status in ("completed", "done", "finished"):
                        return
                    if status in ("failed", "error"):
                        raise RuntimeError(f"Simulation failed: {data}")
            await asyncio.sleep(POLL_INTERVAL)
        raise TimeoutError("MiroFish simulation timed out")

    # ── step 6: generate report ───────────────────────────────────────────────

    async def _generate_report(self, sim_id: str) -> str:
        async with self._session.post("/api/report/generate", json={
            "simulation_id": sim_id,
        }) as r:
            r.raise_for_status()
            data = await r.json()
        report_id = data["report_id"]
        task_id   = data.get("task_id")
        if task_id:
            await self._poll_task("/api/report/generate/status",
                                  post_body={"task_id": task_id})
        else:
            await self._poll_report_status(report_id)
        return report_id

    async def _poll_report_status(self, report_id: str) -> None:
        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            async with self._session.get(f"/api/report/{report_id}") as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("status") == "completed":
                        return
                    if data.get("status") == "failed":
                        raise RuntimeError(f"Report failed: {data.get('error')}")
            await asyncio.sleep(POLL_INTERVAL)
        raise TimeoutError("MiroFish report generation timed out")

    # ── step 7: chat with report agent to extract probability ─────────────────

    async def _extract_probability(
        self, report_id: str
    ) -> tuple[Bias, float, str]:
        """
        Asks the report agent a precise probability question and parses the
        number out of the response.
        """
        prompt = (
            "Based on your analysis, what is the exact probability (as a "
            "percentage, 0-100) that Bitcoin's price will be HIGHER at the "
            "end of the current 5-minute candle than at its open? "
            "Reply with ONLY a single integer or decimal number, nothing else."
        )
        async with self._session.post("/api/report/chat", json={
            "report_id": report_id,
            "message":   prompt,
        }) as r:
            r.raise_for_status()
            data = await r.json()

        reply = data.get("reply") or data.get("message") or data.get("content") or ""
        prob = self._parse_probability(reply)
        reasoning = reply[:200]

        if prob > 0.5 + MIROFISH_MIN_CONFIDENCE / 2:
            return Bias.BULL, prob, reasoning
        elif prob < 0.5 - MIROFISH_MIN_CONFIDENCE / 2:
            return Bias.BEAR, 1.0 - prob, reasoning
        else:
            return Bias.NEUTRAL, max(prob, 1.0 - prob), reasoning

    @staticmethod
    def _parse_probability(text: str) -> float:
        """
        Extracts a 0-1 probability from a string that may contain
        '72', '72%', '0.72', 'approximately 68 percent', etc.
        """
        text = text.strip()
        # match a bare number optionally followed by %
        m = re.search(r"(\d+(?:\.\d+)?)\s*%?", text)
        if not m:
            return 0.5
        val = float(m.group(1))
        if val > 1.0:
            val /= 100.0   # was a percentage
        return max(0.0, min(1.0, val))

    # ── generic task poller ───────────────────────────────────────────────────

    async def _poll_task(
        self,
        status_endpoint: str,
        result_key: Optional[str] = None,
        post_body: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Polls a status endpoint (POST or GET) until task is completed.
        Returns result_key value if provided.
        """
        deadline = time.time() + POLL_TIMEOUT
        while time.time() < deadline:
            if post_body is not None:
                async with self._session.post(status_endpoint, json=post_body) as r:
                    if r.status == 200:
                        data = await r.json()
                    else:
                        await asyncio.sleep(POLL_INTERVAL)
                        continue
            else:
                async with self._session.get(status_endpoint) as r:
                    if r.status == 200:
                        data = await r.json()
                    else:
                        await asyncio.sleep(POLL_INTERVAL)
                        continue

            status = (data.get("status") or data.get("state") or "").lower()
            if status in ("completed", "done", "finished", "success"):
                return data.get(result_key) if result_key else None
            if status in ("failed", "error"):
                raise RuntimeError(f"Task failed: {data}")
            await asyncio.sleep(POLL_INTERVAL)

        raise TimeoutError(f"Task timed out at {status_endpoint}")
