"""B2: basic one-shot sealed-bid auction (spec §9.1 "basic distributed auction", DL-045).

At t = 0 every agent broadcasts one ``task_bid`` message with its bid for every
task it can do (bid = priority; the same score as CBBA, but per task, with no
bundle). At the first round at or after the deadline, each agent decides every
winner from its own bid and the bids it actually received: highest bid, ties
to the lower agent ID. There is no consensus step, so a lost bid message can
leave two agents believing they won a task, or none.

The agent then keeps the tasks it believes it won, greedily by priority and
then slot start, dropping any that overlap a kept slot or exceed storage.
Standard library only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from astramesh.agents.cbba import outbids
from astramesh.agents.packets import CatalogUplink, OwnTask


@dataclass(slots=True)
class AuctionState:
    me: str
    catalog: CatalogUplink
    deadline_ns: int
    sent: bool = False
    decided: bool = False
    received: dict[str, dict[str, float]] = field(default_factory=dict)
    won: tuple[OwnTask, ...] = ()

    def own_bids(self) -> dict[str, float]:
        return {t.task_id: float(t.priority) for t in self.catalog.own if t.start_ns > 0}

    @staticmethod
    def valid_payload(p: Mapping[str, Any]) -> bool:
        bids = p.get("bids")
        return isinstance(bids, Mapping) and all(
            isinstance(v, int | float) and not isinstance(v, bool) and v > 0 for v in bids.values()
        )

    def receive(self, k: str, p: Mapping[str, Any], now_ns: int) -> None:
        if not self.decided:  # bids after the decision are ignored (sealed, one shot)
            self.received[k] = {t: float(v) for t, v in p["bids"].items()}

    def decide(self) -> None:
        mine = self.own_bids()
        own = {t.task_id: t for t in self.catalog.own}
        believed: list[OwnTask] = []
        for tid in self.catalog.task_order:
            if tid not in mine:
                continue
            best_y, best_z = mine[tid], self.me
            for k, bids in sorted(self.received.items()):
                if tid in bids and outbids(bids[tid], k, best_y, best_z):
                    best_y, best_z = bids[tid], k
            if best_z == self.me:
                believed.append(own[tid])
        kept: list[OwnTask] = []
        data = 0.0
        for t in sorted(believed, key=lambda t: (-t.priority, t.start_ns, t.task_id)):
            if any(o.start_ns < t.stop_ns and t.start_ns < o.stop_ns for o in kept):
                continue
            if data + t.data_mb > self.catalog.storage_capacity_mb:
                continue
            kept.append(t)
            data += t.data_mb
        self.won = tuple(sorted(kept, key=lambda t: t.start_ns))
        self.decided = True
