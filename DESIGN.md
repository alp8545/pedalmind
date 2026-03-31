# DESIGN.md — PedalMind Design System

## Dark Theme Background Colors

| Token          | Hex       | Usage                              |
|----------------|-----------|------------------------------------|
| `base`         | `#0f172a` | Body background, input fields      |
| `card-solid`   | `rgba(15,23,42,0.8)` → `rgba(15,23,42,0.5)` | G card gradient (135deg) |
| `nav-bg`       | `rgba(6,10,20,0.97)` | Bottom nav gradient end            |
| `tooltip`      | `#1e293b` | Chart tooltip background           |
| `surface-dim`  | `rgba(15,23,42,0.6)` | Expanded detail panels             |

## Color Palette

| Name           | Hex       | Tailwind class     | Usage                        |
|----------------|-----------|--------------------|------------------------------|
| Amber-500      | `#f59e0b` | `text-amber-500`   | Brand accent, CTL line, FTP  |
| Amber-400      | `#f59e0b` | `text-amber-400`   | Active nav, interactive text |
| Amber-600      | `#d97706` | —                  | Gradient end on CTA buttons  |
| Cyan-400       | `#22d3ee` | `text-cyan-400`    | TSB / Forma line             |
| Red-400        | `#ef4444` | `text-red-400`     | ATL / Fatica line, HR        |
| Red-600        | `#dc2626` | —                  | Overreaching form badge      |
| Green-400      | `#22c55e` | `text-green-400`   | Sub-text, Fresh/Peaked badge |
| Green-500      | `#22c55e` | —                  | Fresh/Peaked form color      |
| Purple-500     | `#8b5cf6` | —                  | Z7 zone, Recovery phase      |
| Blue-500       | `#3b82f6` | —                  | Z2 zone, Base phase          |
| Orange-500     | `#f97316` | —                  | Z5 zone, theme-color meta    |
| Slate-50       | `#f8fafc` | `text-slate-50`    | Primary text, headings       |
| Slate-200      | `#e2e8f0` | —                  | Body text color, tooltip     |
| Slate-300      | `#cbd5e1` | `text-slate-300`   | Secondary content text       |
| Slate-400      | `#94a3b8` | `text-slate-400`   | Labels, muted text           |
| Slate-500      | `#64748b` | `text-slate-500`   | Axis ticks, tertiary text    |
| Slate-600      | `#475569` | —                  | Z1 zone, reference lines     |
| Slate-700      | `rgba(148,163,184,0.08)` | — | Card border (low alpha) |

## Power Zone Colors (Z1–Z7)

```js
const ZONE_COLORS = ['#475569', '#3b82f6', '#22c55e', '#f59e0b', '#f97316', '#ef4444', '#8b5cf6']
```

| Zone | Name       | Hex       |
|------|------------|-----------|
| Z1   | Recovery   | `#475569` |
| Z2   | Endurance  | `#3b82f6` |
| Z3   | Tempo      | `#22c55e` |
| Z4   | Threshold  | `#f59e0b` |
| Z5   | VO2max     | `#f97316` |
| Z6   | Anaerobic  | `#ef4444` |
| Z7   | Sprint     | `#8b5cf6` |

## Form Indicator Colors

| State        | Color     | Background alpha | Label (IT)     |
|--------------|-----------|------------------|----------------|
| Peaked       | `#22c55e` | `0.15`           | Peaked         |
| Fresh        | `#22c55e` | `0.15`           | Fresh          |
| Building     | `#f59e0b` | `0.15`           | Building       |
| Fatigued     | `#ef4444` | `0.15`           | Faticato       |
| Overreaching | `#dc2626` | `0.20`           | Sovraccarico   |

## Typography

| Property        | Value                                             |
|-----------------|---------------------------------------------------|
| Font family     | `DM Sans` (body/headings), `DM Mono` (data/labels)|
| Loaded via      | Google Fonts (`300;400;500;600;700` Sans, `300;400;500` Mono) |
| Heading style   | `font-light` (300), `text-2xl`, `letterSpacing: -0.5` |
| Label style     | `font-mono`, `uppercase`, `fontSize: 11`, `letterSpacing: 1.5` |
| Metric value    | `font-mono`, `font-bold`, `fontSize: 24`          |
| Sub text        | `font-mono`, `fontSize: 11`                       |
| Nav label       | `font-mono`, `uppercase`, `fontSize: 9`, `letterSpacing: 1.5` |
| Axis tick       | `fontSize: 10`, `fontFamily: 'monospace'`          |
| Brand wordmark  | `text-amber-500`, `font-bold`, `text-base`, `letterSpacing: -0.5` |

## Card Component Specs (G)

| Property         | Value                                                      |
|------------------|------------------------------------------------------------|
| Border radius    | `14px` (`rounded-[14px]`)                                  |
| Padding          | `1rem` (p-4), variants use `!p-3`                          |
| Background       | `linear-gradient(135deg, rgba(15,23,42,0.8), rgba(15,23,42,0.5))` |
| Backdrop blur    | `blur(12px)` (both `-webkit-` and standard)                |
| Border           | `1px solid rgba(148,163,184,0.08)`                         |
| Hover variant    | `border-amber-500/20`                                      |
| Accent variant   | `borderLeft: 3px solid #f59e0b`, `borderRadius: 3px 14px 14px 3px` |

## Spacing Scale

Follows Tailwind defaults. Common usage:

| Token   | Value  | Where used                    |
|---------|--------|-------------------------------|
| `gap-1` | 4px    | Icon + label pairs            |
| `gap-2` | 8px    | Grid cells, card lists        |
| `gap-3` | 12px   | Metric row items              |
| `gap-4` | 16px   | Page sections, main container |
| `px-4`  | 16px   | Page horizontal padding       |
| `py-4`  | 16px   | Page vertical padding         |
| `p-3`   | 12px   | Compact card variant          |
| `p-4`   | 16px   | Default card padding          |
| `mb-1.5`| 6px    | Label bottom margin           |
| `mt-0.5`| 2px    | Heading top margin            |

## Component Catalog

### `G` — Glass card container
```jsx
<G className="p-3 text-center">…</G>
```
Base wrapper for all card-like surfaces. Accepts `className`, `style`, and spread props.

### `Label` — Section/metric label
```jsx
<Label>POTENZA MEDIA</Label>
```
Renders an uppercase mono label (`fontSize: 11`, `letterSpacing: 1.5`, `text-slate-400`).

### `MetricCard` — Single stat display
```jsx
<MetricCard label="FTP" value="265" color="#f59e0b" sub="target" />
```
Props: `label` (string), `value` (string|number), `sub` (optional string, green-400), `color` (hex, default `#f8fafc`). Wraps in a centered `G`.

### `ZoneBar` — Power zone progress bar
```jsx
<ZoneBar zone={3} pct={24.5} time="12:30" color="#22c55e" />
```
Horizontal bar with zone label, percentage fill, and duration. Exports `ZONE_COLORS` array.

### `TrendsChart` — Performance Manager line chart
```jsx
<TrendsChart points={trends.points} height={120} />
```
Recharts `LineChart` with CTL (amber), ATL (red), TSB (cyan) lines. Includes custom tooltip with form badge colors.

### `DonutRing` — Circular progress indicator
```jsx
<DonutRing value={68} max={100} color="#f59e0b" size={56} label="%" />
```

## Italian Copy Convention

All user-facing text is in Italian:
- Greetings: `Buongiorno`, `Buon pomeriggio`, `Buonasera`
- Labels: `Potenza Media`, `FC Media`, `Cadenza`, `Zone di Potenza`
- Actions: `Scarica`, `Analizza`, `Carica`, `Annulla`, `Salva`
- Status: `Caricamento…`, `Analisi completata`, `Nessun dato`
- Date format: `it-IT` locale (`day: 'numeric', month: 'long'`)
- Navigation labels: `Home`, `Coach`, `Piano`, `Settings`

Form states use English names (Peaked, Fresh, Building) but contextual labels translate: `Faticato` (Fatigued), `Sovraccarico` (Overreaching).
