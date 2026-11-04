"""Local protection supervisor: the five-mode machine (spec §6, DL-054, DL-056).

**Local survival takes precedence over constellation science.** The supervisor
sits between the planner and the payload: ``allows_payload()`` is True only in
NOMINAL and STORM_WATCH, and the agent's ``payload_command`` asks it before every
step. Plans and messages cannot change the mode; only the agent's own inputs can.

Inputs (own packets only):

* housekeeping: battery fraction and critical-subsystem flags;
* risk forecast: three separate ratios to modelled tolerance (radiation,
  navigation/communications, orbital disturbance), each ``None`` when invalid;
* recovery checks prepared by the agent: battery above reserve, a fresh navigation
  fix, and peer contact (when any peer is believed available).

Guards (values are settings, PROVISIONAL):

* any -> SAFE: battery <= ``safe_battery_fraction`` or any critical flag (first).
* SAFE -> RECOVERY: no flag and battery >= ``safe_exit_battery_fraction`` held
  ``safe_exit_dwell_ns``. A better forecast never clears SAFE.
* NOMINAL -> STORM_WATCH: any valid input >= ``watch_ratio``, or the forecast has
  been invalid for longer than ``invalid_to_watch_ns`` (uncertainty policy).
* STORM_WATCH -> PROTECTIVE: valid radiation >= ``protect_ratio`` (only radiation
  has a modelled vulnerable function). The NOMINAL -> STORM_WATCH -> PROTECTIVE
  chain may happen in one update; both transitions are logged.
* STORM_WATCH -> NOMINAL: all inputs valid and < ``watch_release_ratio`` for
  ``watch_release_dwell_ns``.
* PROTECTIVE -> RECOVERY: valid radiation < ``release_ratio`` for ``release_dwell_ns``.
* RECOVERY -> PROTECTIVE: valid radiation >= ``protect_ratio``.
* RECOVERY -> NOMINAL: at least ``recovery_min_dwell_ns`` in RECOVERY and all
  recovery checks pass.
* Invalid inputs never release a protected mode (dwell clocks restart) and never
  trigger PROTECTIVE on their own.

Standard library only (agent isolation rule).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

NOMINAL = "NOMINAL"
STORM_WATCH = "STORM_WATCH"
PROTECTIVE = "PROTECTIVE"
RECOVERY = "RECOVERY"
SAFE = "SAFE"
MODES = (NOMINAL, STORM_WATCH, PROTECTIVE, RECOVERY, SAFE)
SCIENCE_MODES = frozenset({NOMINAL, STORM_WATCH})  # payload allowed
TASKING_MODES = SCIENCE_MODES  # available for new tasks (peers and own bidding)
RISKS = ("radiation", "navcomms", "orbital")


@dataclass(frozen=True, slots=True)
class SupervisorSettings:
    safe_battery_fraction: float = 0.10
    safe_exit_battery_fraction: float = 0.50
    safe_exit_dwell_ns: int = 600 * 10**9
    watch_ratio: float = 0.6
    watch_release_ratio: float = 0.5
    watch_release_dwell_ns: int = 1800 * 10**9
    protect_ratio: float = 1.0
    release_ratio: float = 0.8
    release_dwell_ns: int = 1800 * 10**9
    invalid_to_watch_ns: int = 600 * 10**9
    recovery_min_dwell_ns: int = 300 * 10**9

    def __post_init__(self) -> None:
        if not 0.0 <= self.safe_battery_fraction < self.safe_exit_battery_fraction <= 1.0:
            raise ValueError("need 0 <= safe_battery_fraction < safe_exit_battery_fraction <= 1")
        if not 0.0 < self.release_ratio < self.protect_ratio:
            raise ValueError("need 0 < release_ratio < protect_ratio (hysteresis)")
        if not 0.0 < self.watch_release_ratio < self.watch_ratio <= self.protect_ratio:
            raise ValueError("need 0 < watch_release_ratio < watch_ratio <= protect_ratio")
        dwells = (self.safe_exit_dwell_ns, self.watch_release_dwell_ns, self.release_dwell_ns,
                  self.invalid_to_watch_ns, self.recovery_min_dwell_ns)  # fmt: skip
        if min(dwells) < 0:
            raise ValueError("dwell times must be >= 0")


@dataclass(slots=True)
class Supervisor:
    settings: SupervisorSettings
    mode: str = NOMINAL
    history: list[tuple[int, str, str, str]] = field(default_factory=list)  # (t, old, new, why)
    notes: list[tuple[int, str]] = field(default_factory=list)
    _entered_ns: int = 0
    _safe_ok_since: int | None = None
    _release_ok_since: int | None = None
    _invalid_since: int | None = None

    def allows_payload(self) -> bool:
        return self.mode in SCIENCE_MODES

    def accepts_tasks(self) -> bool:
        return self.mode in TASKING_MODES

    def _go(self, now_ns: int, new: str, why: str) -> None:
        if new != self.mode:
            self.history.append((now_ns, self.mode, new, why))
            self.mode = new
            self._entered_ns = now_ns
            self._safe_ok_since = None
            self._release_ok_since = None

    def _dwell(self, ok: bool, now_ns: int, need_ns: int) -> bool:
        """Track a continuous condition; True once it has held for ``need_ns``."""
        if not ok:
            self._release_ok_since = None
            return False
        if self._release_ok_since is None:
            self._release_ok_since = now_ns
        return now_ns - self._release_ok_since >= need_ns

    def update(
        self,
        now_ns: int,
        *,
        battery_fraction: float | None,
        critical_flags: tuple[str, ...],
        risks: Mapping[str, float | None],
        forecast_enabled: bool,
        recovery_checks_ok: bool = True,
    ) -> None:
        s = self.settings
        # 1. Critical local fault -> SAFE from any mode (checked first: SAFE always wins).
        low = battery_fraction is not None and battery_fraction <= s.safe_battery_fraction
        if critical_flags or low:
            why = "critical_flag:" + ",".join(critical_flags) if critical_flags else "battery_low"
            self._go(now_ns, SAFE, why)
            self._safe_ok_since = None
            return
        if self.mode == SAFE:
            ok = battery_fraction is not None and battery_fraction >= s.safe_exit_battery_fraction
            if not ok:
                self._safe_ok_since = None
                return
            if self._safe_ok_since is None:
                self._safe_ok_since = now_ns
            if now_ns - self._safe_ok_since >= s.safe_exit_dwell_ns:
                self._go(now_ns, RECOVERY, "safe_exit_conditions_met")
            return

        # 2. Environmental inputs (three separate dimensions; never averaged).
        if forecast_enabled:
            vals = {k: risks.get(k) for k in RISKS}
            invalid = [k for k, v in vals.items() if v is None]
            if invalid:
                if self._invalid_since is None:
                    self._invalid_since = now_ns
                    self.notes.append((now_ns, "forecast_invalid:" + ",".join(invalid)))
            else:
                self._invalid_since = None
            valid = {k: v for k, v in vals.items() if v is not None}
            rad = valid.get("radiation")
        else:
            invalid, valid, rad = [], {}, None
            self._invalid_since = None

        if self.mode == NOMINAL and forecast_enabled:
            high = sorted(k for k, v in valid.items() if v >= s.watch_ratio)
            stale = (self._invalid_since is not None
                     and now_ns - self._invalid_since > s.invalid_to_watch_ns)  # fmt: skip
            if high:
                self._go(now_ns, STORM_WATCH, "risk>=watch:" + ",".join(high))
            elif stale:
                self._go(
                    now_ns,
                    STORM_WATCH,
                    "forecast_invalid>" + str(s.invalid_to_watch_ns // 10**9) + "s",
                )
        if self.mode == STORM_WATCH:
            if rad is not None and rad >= s.protect_ratio:
                self._go(now_ns, PROTECTIVE, f"radiation>={s.protect_ratio}")
            else:
                calm = not invalid and all(v < s.watch_release_ratio for v in valid.values())
                if self._dwell(calm, now_ns, s.watch_release_dwell_ns):
                    self._go(now_ns, NOMINAL, "watch_released_after_dwell")
            return
        if self.mode == PROTECTIVE:
            ok = rad is not None and rad < s.release_ratio
            if self._dwell(ok, now_ns, s.release_dwell_ns):
                self._go(now_ns, RECOVERY, "radiation_released_after_dwell")
            return
        if self.mode == RECOVERY:
            if rad is not None and rad >= s.protect_ratio:
                self._go(now_ns, PROTECTIVE, "hazard_returned_during_recovery")
            elif now_ns - self._entered_ns >= s.recovery_min_dwell_ns and recovery_checks_ok:
                self._go(now_ns, NOMINAL, "recovery_checks_passed")
