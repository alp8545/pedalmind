# TODOS.md — PedalMind Deferred Work

## P2

### Create DESIGN.md (design system documentation)
- **Why:** Design system is strong but undocumented. Lives in ui.jsx (G, Label, MetricCard) and Nav.jsx. A formal DESIGN.md prevents drift as new components are added.
- **Effort:** S (CC: ~10min)
- **Context:** Color palette (amber-500 primary, cyan TSB, red fatigue, slate-400 secondary), typography (font-mono, uppercase labels 11px), glass cards (rounded-[14px], backdrop-blur), spacing (gap-4 sections, gap-2 within). Consider running `/design-consultation`.
- **Source:** Design review, 2026-03-30

### Add auth to garmin_sync endpoints
- **Why:** garmin_sync.py endpoints have no `Depends(get_current_user)`. All other routers have auth.
- **Effort:** S (CC: ~5min)
- **Context:** Single-user app, but consistency matters. Prevents unauthorized sync triggers.
- **Source:** CEO review outside voice, 2026-03-29

## P3

### Migrate garth -> garminconnect library
- **Why:** garth is marked deprecated on GitHub. garminconnect is the maintained wrapper.
- **Effort:** S (CC: ~20min)
- **Context:** garth v0.6.3 released 2026-03-19, still functional. garminconnect wraps garth internally. Only migrate if garth actually stops working or Garmin changes auth again.
- **Source:** CEO review, 2026-03-29

### Clean up duplicate garmin_client.py
- **Why:** Two Garmin client files: garth_client.py (active, garth-based) and garmin_client.py (older OAuth1 version). Verify garmin_client.py is unused, then delete.
- **Effort:** S (CC: ~5min)
- **Context:** garmin_client.py has OAuth1 support predating the garth approach. Check if any router imports it.
- **Source:** CEO review outside voice, 2026-03-29
