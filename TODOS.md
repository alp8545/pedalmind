# TODOS.md — PedalMind Deferred Work

## P3

### Migrate garth -> garminconnect library
- **Why:** garth is marked deprecated on GitHub. garminconnect is the maintained wrapper.
- **Effort:** S (CC: ~20min)
- **Context:** garth v0.6.3 released 2026-03-19, still functional. garminconnect wraps garth internally. Only migrate if garth actually stops working or Garmin changes auth again.
- **Source:** CEO review, 2026-03-29

### Clean up duplicate garmin_client.py
- **Why:** Two Garmin client files: garth_client.py (active, garth-based) and garmin_client.py (older OAuth1 version). garmin_client.py is imported by sync.py — can't delete without migrating sync.py first.
- **Effort:** S (CC: ~10min)
- **Blocked by:** sync.py still imports garmin_client.py for OAuth1 flow
- **Source:** CEO review outside voice, 2026-03-29

## Completed

### ~~P1: Dati secondo-per-secondo (decoupling + HR recovery)~~
Completed 2026-03-31. ride_metrics.py, backfill endpoint, chat context, frontend cards.

### ~~P2: Create DESIGN.md~~
Completed 2026-03-31. Full design system documentation.

### ~~P2: Add auth to garmin_sync endpoints~~
Completed 2026-03-31. Depends(get_current_user) on all endpoints.
