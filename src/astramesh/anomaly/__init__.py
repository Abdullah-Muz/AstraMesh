"""Anomaly detection on real spacecraft telemetry (Phase 4, DL-064).

Simulator-side and independent of the multi-spacecraft simulation (spec §7.2): agents
never import this package. Needs the ``ml`` dependency group (scikit-learn, PyOD,
xgboost-cpu and CPU-only PyTorch).
"""
