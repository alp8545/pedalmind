# TODOS.md — PedalMind Deferred Work

## P1

### Dati secondo-per-secondo per analisi AI e metriche avanzate
- **Why:** L'AI coach attualmente vede solo metriche aggregate (NP, TSS, avg power). Per dare consigli reali da coach serve accesso ai dati secondo per secondo: andamento potenza, HR, cadenza durante la ride. Questo abilita due feature chiave:
  1. **Decoupling cardiaco (Pw:Hr):** rapporto potenza/frequenza cardiaca nella prima vs seconda meta di uno sforzo steady-state. Se HR sale a parita di potenza, l'atleta non e' aerobicamente efficiente. Metrica chiave per valutare la forma aerobica.
  2. **Recupero cardiaco post-intervallo:** quanto velocemente scende l'HR dopo i blocchi intensi (es. dopo VO2max intervals). Tempo per scendere di 30bpm = indicatore di fitness cardiovascolare. Monitorare il trend nel tempo.
- **Effort:** M (CC: ~30min)
- **Context:** Garmin restituisce dati secondo per secondo nei dettagli attivita (endpoint `/activity-service/activity/{id}/details`). Opzioni: (A) scaricare e salvare in un campo JSON sull'Activity (pesante ma semplice), (B) calcolare decoupling e HR recovery al momento del sync e salvare solo i risultati (leggero, sufficiente per il chat context), (C) ibrido: calcolare le metriche al sync, scaricare il raw data on-demand quando l'utente apre il dettaglio ride. Raccomandato: opzione B per il chat AI + opzione C per la visualizzazione dettagliata.
- **Depends on:** Garmin sync stabile (completato)
- **Source:** Alessio, 2026-03-30

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
