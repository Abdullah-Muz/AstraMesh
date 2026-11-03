# Autonomy Architecture

> **Owner:** Abdullah Muzher · **Status:** NOT STARTED — placeholder · **Spec:** §5, §14.1 · **Target phase:** 2 · **Last updated:** 2026-11-03

## Purpose

Specify the `SpacecraftAgent` components, interfaces, message schema, network model, and health-belief semantics in implementation detail.

## Requirements to satisfy (from spec)

- Each agent holds independent estimators, resource manager, task database, inbox/outbox, allocation logic, guidance interface, safety supervisor, and audit log (§5.1).
- Agents never share writable mission state or read hidden truth or undelivered messages (§5.1, §14.1 hard stop).
- Message fields: sender ID, sequence ID, creation time, expiry, type, plan version, payload; duplicate, expiry, ordering, and reconciliation rules (§5.3).
- Health beliefs (`HEALTHY` … `UNKNOWN`) are distinct from simulator ground truth; evidence rules for `CONFIRMED_FAILED` (§5.4).

## Content

Not yet written.
