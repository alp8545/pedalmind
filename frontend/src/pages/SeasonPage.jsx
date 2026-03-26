import { G, Label } from '../components/ui'
import DonutRing from '../components/charts/DonutRing'

const PHASES = [
  { n: 'BASE', c: '#3b82f6', a: true }, { n: 'BUILD', c: '#f59e0b', a: true },
  { n: 'PEAK', c: '#ef4444', a: false }, { n: 'RACE', c: '#22c55e', a: false },
  { n: 'REC', c: '#8b5cf6', a: false },
]
const RACES = [
  { name: 'GF Strade Bianche', date: '7 Giu', pri: 'A', dist: '138km \u00B7 2100m D+' },
  { name: 'Maratona dles Dolomites', date: '5 Lug', pri: 'A', dist: '138km \u00B7 4230m D+' },
  { name: 'GF Firenze-Mare', date: '20 Apr', pri: 'B', dist: '112km \u00B7 1450m D+' },
  { name: 'Cronoscalata Chianti', date: '10 Mag', pri: 'C', dist: '18km \u00B7 620m D+' },
]
const WEEK = [
  { d: 'Lun', w: 'Endurance Z2', t: '1h30', c: '#3b82f6', done: true },
  { d: 'Mar', w: 'Sweet Spot 4\u00D710\'', t: '1h30', c: '#f59e0b', today: true },
  { d: 'Mer', w: 'Riposo', t: '\u2014', c: '#1e293b' },
  { d: 'Gio', w: 'VO2max 5\u00D74\'', t: '1h15', c: '#ef4444' },
  { d: 'Ven', w: 'Recovery Z1', t: '0h45', c: '#22c55e' },
  { d: 'Sab', w: 'Lungo Z2-Z3', t: '3h00', c: '#f59e0b' },
  { d: 'Dom', w: 'Endurance Z2', t: '1h30', c: '#3b82f6' },
]

export default function SeasonPage() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col gap-4">
      <div>
        <div className="font-mono text-slate-500 uppercase" style={{ fontSize: 11, letterSpacing: 1 }}>STAGIONE 2026</div>
        <h1 className="text-2xl font-light text-slate-50 mt-0.5">Piano di Crescita</h1>
      </div>

      {/* Periodization */}
      <G>
        <Label>Periodizzazione</Label>
        <div className="flex gap-0.5 h-7 rounded-md overflow-hidden">
          {PHASES.map(p => (
            <div key={p.n} className="flex-1 flex items-center justify-center"
              style={{ background: p.a ? `${p.c}cc` : `${p.c}22` }}>
              <span className="font-mono font-semibold" style={{ fontSize: 8, color: p.a ? '#fff' : '#64748b' }}>{p.n}</span>
            </div>
          ))}
        </div>
        <div className="flex justify-between mt-1">
          <span className="font-mono text-slate-600" style={{ fontSize: 8 }}>Gen</span>
          <span className="font-mono text-amber-500" style={{ fontSize: 8 }}>{'\u25BC'} Ora</span>
          <span className="font-mono text-slate-600" style={{ fontSize: 8 }}>Set</span>
        </div>
      </G>

      {/* FTP Goal */}
      <G>
        <Label>Obiettivo FTP</Label>
        <div className="flex justify-between items-center">
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono font-extralight text-slate-500" style={{ fontSize: 28 }}>268</span>
            <span className="text-slate-600" style={{ fontSize: 18 }}>{'\u2192'}</span>
            <span className="font-mono font-bold text-amber-500" style={{ fontSize: 28 }}>295</span>
            <span className="font-mono text-slate-500" style={{ fontSize: 11 }}>W</span>
          </div>
          <DonutRing value={68} max={100} color="#f59e0b" size={56} label="%" />
        </div>
        <div className="h-1 bg-[#0f172a] rounded-full mt-3">
          <div className="h-full rounded-full" style={{ width: '68%', background: 'linear-gradient(90deg, #f59e0b, #d97706)' }} />
        </div>
        <div className="font-mono text-slate-500 mt-1" style={{ fontSize: 9 }}>+27W rimanenti \u00B7 ~16 settimane</div>
      </G>

      {/* Races */}
      <div>
        <Label>Gare in Programma</Label>
        <div className="flex flex-col gap-1.5 mt-1">
          {RACES.map(r => {
            const c = { A: '#f59e0b', B: '#22d3ee', C: '#8b5cf6' }[r.pri]
            return (
              <div key={r.name} className="flex items-center gap-3 px-3 py-2 rounded-r-lg"
                style={{ background: `linear-gradient(90deg, ${c}11, transparent)`, borderLeft: `3px solid ${c}` }}>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-slate-50">{r.name}</div>
                  <div className="font-mono text-slate-500" style={{ fontSize: 10 }}>{r.date} \u00B7 {r.dist}</div>
                </div>
                <span className="font-mono font-bold rounded px-1.5 py-0.5"
                  style={{ fontSize: 9, color: c, background: `${c}15` }}>{r.pri}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Week plan */}
      <G>
        <Label>Questa Settimana \u00B7 Build 3/8</Label>
        {WEEK.map((r, i) => (
          <div key={r.d} className="flex items-center gap-2 py-1.5"
            style={{ borderBottom: i < 6 ? '1px solid rgba(148,163,184,0.04)' : 'none', opacity: r.done ? 0.4 : 1 }}>
            <span className="w-6 font-mono" style={{ fontSize: 10, fontWeight: r.today ? 700 : 400, color: r.today ? '#f59e0b' : '#64748b' }}>{r.d}</span>
            <div className="w-1 h-1 rounded-full" style={{ background: r.c }} />
            <span className="flex-1 text-slate-200" style={{ fontSize: 11 }}>{r.w}</span>
            <span className="font-mono text-slate-600" style={{ fontSize: 9 }}>{r.t}</span>
          </div>
        ))}
      </G>
    </div>
  )
}
