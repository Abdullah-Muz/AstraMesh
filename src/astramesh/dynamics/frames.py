"""Local-orbital RIC frame (radial, in-track, cross-track).

Convention (``docs/CONVENTIONS.md`` §3), from the chief's inertial state:
``R = r/|r|``, ``C = (r x v)/|r x v|``, ``I = C x R`` (right-handed).

Relative states in RIC are expressed in the *rotating* frame: the relative
velocity removes the frame's angular velocity ``omega = (r x v)/|r|^2``
(exact for the instantaneous rotation of the R/I axes about C under
two-body motion):

    rho     = A (r_d - r_c)
    rho_dot = A ((v_d - v_c) - omega x (r_d - r_c))

where ``A`` has rows R, I, C. Earth-fixed (ITRS) transforms are in
:mod:`astramesh.dynamics.earth_frames`.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from astramesh.dynamics.state import (
    CartesianState,
    Frame,
    NonPhysicalStateError,
    cross3,
    dot3,
    matvec3,
    norm3,
)


def ric_basis(r_m: NDArray[np.float64], v_mps: NDArray[np.float64]) -> NDArray[np.float64]:
    """3x3 matrix whose rows are the R, I, C unit vectors in the inertial frame."""
    rn = float(norm3(r_m))
    h = cross3(r_m, v_mps)
    hn = float(norm3(h))
    if rn == 0.0 or hn <= 1e-12 * rn * float(norm3(v_mps)):
        raise NonPhysicalStateError("RIC frame is undefined for zero radius or rectilinear motion")
    r_hat = r_m / rn
    c_hat = h / hn
    i_hat = cross3(c_hat, r_hat)
    return np.stack((r_hat, i_hat, c_hat))


def _omega(chief: CartesianState) -> NDArray[np.float64]:
    r = chief.r_m
    return cross3(r, chief.v_mps) / float(dot3(r, r))


def eci_to_ric(chief: CartesianState, deputy: CartesianState) -> CartesianState:
    """Deputy state relative to the chief, expressed in the chief's RIC frame."""
    chief.require_frame(Frame.GCRS)
    deputy.require_frame(Frame.GCRS)
    chief.require_same_time(deputy)
    a = ric_basis(chief.r_m, chief.v_mps)
    dr = deputy.r_m - chief.r_m
    dv = deputy.v_mps - chief.v_mps - cross3(_omega(chief), dr)
    return CartesianState(Frame.RIC, chief.epoch_utc, chief.t_ns, matvec3(a, dr), matvec3(a, dv))


def ric_to_eci(chief: CartesianState, relative: CartesianState) -> CartesianState:
    """Inverse of :func:`eci_to_ric`: the deputy's inertial (GCRS) state."""
    chief.require_frame(Frame.GCRS)
    relative.require_frame(Frame.RIC)
    chief.require_same_time(relative)
    a = ric_basis(chief.r_m, chief.v_mps)
    dr = matvec3(a.T, relative.r_m)
    dv = matvec3(a.T, relative.v_mps) + cross3(_omega(chief), dr)
    return CartesianState(Frame.GCRS, chief.epoch_utc, chief.t_ns, chief.r_m + dr, chief.v_mps + dv)
