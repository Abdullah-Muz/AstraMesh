"""Local protection supervisor: NOMINAL / PROTECTIVE / SAFE (spec §6, DL-054).

**Local survival takes precedence over constellation science.** The supervisor
sits between the planner and the payload: ``allows_payload()`` is True only in
NOMINAL, and the agent's ``payload_command`` asks it before every step. Nothing
the planner or a message does can change the mode; only the agent's own
housekeeping and its environmental forecast can.

Inputs (own packets only):

* housekeeping: battery and critical-subsystem flags;
* forecast: predicted exposure relative to the payload's modelled tolerance
  (1.0 = at the limit), or ``None`` when missing or invalid.

Guards (DL-054; values are settings, PROVISIONAL):

* any mode -> SAFE: battery <= ``safe_battery_fraction`` of capacity, or any
  critical flag. SAFE is checked first, so it always wins.
* SAFE -> NOMINAL: no critical flag and battery >= ``safe_exit_battery_fraction``,
  continuously for ``safe_exit_dwell_ns``. A better forecast never clears SAFE.
* NOMINAL -> PROTECTIVE: valid forecast >= ``protect_ratio``.
* PROTECTIVE -> NOMINAL: valid forecast < ``release_ratio`` continuously for
  ``release_dwell_ns`` (hysteresis + dwell). An invalid forecast restarts the
  dwell: the mode is held, never released on missing data.
* An invalid forecast never counts as zero risk; while it lasts the mode is held
  and the episode is logged once.

Standard library only (agent isolation rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field

NOMINAL = "NOMINAL"
PROTECTIVE = "PROTECTIVE"
SAFE = "SAFE"
MODES = (NOMINAL, PROTECTIVE, SAFE)


@dataclass(frozen=True, slots=True)
class SupervisorSettings:
    safe_battery_fraction: float = 0.10
    safe_exit_battery_fraction: float = 0.50
    safe_exit_dwell_ns: int = 600 * 10**9
    protect_ratio: float = 1.0
    release_ratio: float = 0.8
    release_dwell_ns: int = 1800 * 10**9

    def __post_init__(self) -> None:
        if not 0.0 <= self.safe_battery_fraction < self.safe_exit_battery_fraction <= 1.0:
            raise ValueError("need 0 <= safe_battery_fraction < safe_exit_battery_fraction <= 1")
        if not 0.0 < self.release_ratio < self.protect_ratio:
            raise ValueError("need 0 < release_ratio < protect_ratio (hysteresis)")
        if self.safe_exit_dwell_ns < 0 or self.release_dwell_ns < 0:
            raise ValueError("dwell times must be >= 0")


@dataclass(slots=True)
class Supervisor:
    settings: SupervisorSettings
    mode: str = NOMINAL
    history: list[tuple[int, str, str, str]] = field(default_factory=list)  # (t, old, new, why)
    _safe_ok_since: int | None = None
    _release_ok_since: int | None = None
    _forecast_invalid: bool = False
    notes: list[tuple[int, str]] = field(default_factory=list)  # e.g. invalid-forecast episodes

    def allows_payload(self) -> bool:
        return self.mode == NOMINAL

    def _go(self, now_ns: int, new: str, why: str) -> None:
        if new != self.mode:
            self.history.append((now_ns, self.mode, new, why))
            self.mode = new
            self._safe_ok_since = None
            self._release_ok_since = None

    def update(
        self,
        now_ns: int,
        *,
        battery_fraction: float | None,
        critical_flags: tuple[str, ...],
        exposure_ratio: float | None,
        forecast_enabled: bool,
    ) -> None:
        s = self.settings
        # 1. Critical local fault -> SAFE, from any mode (checked first: SAFE always wins).
        critical = bool(critical_flags) or (
            battery_fraction is not None and battery_fraction <= s.safe_battery_fraction
        )
        if critical:
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
                self._go(now_ns, NOMINAL, "safe_exit_conditions_met")
            return
        if not forecast_enabled:
            return  # scenario without a hazard model: the environmental input is disabled
        # 2. Environmental hazard (PROTECTIVE) with hysteresis and dwell.
        if exposure_ratio is None:
            if not self._forecast_invalid:
                self.notes.append((now_ns, "forecast_invalid_hold"))
            self._forecast_invalid = True
            self._release_ok_since = None  # never release on missing data
            return
        self._forecast_invalid = False
        if self.mode == NOMINAL:
            if exposure_ratio >= s.protect_ratio:
                self._go(now_ns, PROTECTIVE, f"exposure_ratio>={s.protect_ratio}")
            return
        # PROTECTIVE
        if exposure_ratio < s.release_ratio:
            if self._release_ok_since is None:
                self._release_ok_since = now_ns
            if now_ns - self._release_ok_since >= s.release_dwell_ns:
                self._go(now_ns, NOMINAL, "exposure_released_after_dwell")
        else:
            self._release_ok_since = None
