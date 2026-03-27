import { useState } from 'react'
import { G, Label } from '../components/ui'
import DonutRing from '../components/charts/DonutRing'

const PHASES = [
  { n: 'BASE', c: '#3b82f6', a: true }, { n: 'BUILD', c: '#f59e0b', a: true },
  { n: 'PEAK', c: '#ef4444', a: false }, { n: 'RACE', c: '#22c55e', a: false },
  { n: 'REC', c: '#8b5cf6', a: false },
]

const PRI_COLORS = { A: '#f59e0b', B: '#22d3ee', C: '#8b5cf6' }

export default function SeasonPage() {
  const [races, setRaces] = useState([])
  const [showAddRace, setShowAddRace] = useState(false)
  const [newRace, setNewRace] = useState({ name: '', date: '', pri: 'A', dist: '' })

  const addRace = () => {
    if (!newRace.name.trim()) return
    setRaces(prev => [...prev, { ...newRace, id: Date.now() }])
    setNewRace({ name: '', date: '', pri: 'A', dist: '' })
    setShowAddRace(false)
  }

  const removeRace = (id) => {
    setRaces(prev => prev.filter(r => r.id !== id))
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col gap-4">
      <div>
        <div className="font-mono text-slate-400 uppercase" style={{ fontSize: 13, letterSpacing: 1 }}>STAGIONE 2026</div>
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
          <span className="font-mono text-slate-400" style={{ fontSize: 8 }}>Gen</span>
          <span className="font-mono text-amber-500" style={{ fontSize: 8 }}>{'\u25BC'} Ora</span>
          <span className="font-mono text-slate-400" style={{ fontSize: 8 }}>Set</span>
        </div>
      </G>

      {/* FTP Goal */}
      <G>
        <Label>Obiettivo FTP</Label>
        <div className="flex justify-between items-center">
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono font-extralight text-slate-400" style={{ fontSize: 28 }}>265</span>
            <span className="text-slate-400" style={{ fontSize: 18 }}>{'\u2192'}</span>
            <span className="font-mono font-bold text-amber-500" style={{ fontSize: 28 }}>295</span>
            <span className="font-mono text-slate-400" style={{ fontSize: 13 }}>W</span>
          </div>
          <DonutRing value={68} max={100} color="#f59e0b" size={56} label="%" />
        </div>
        <div className="h-1 bg-[#0f172a] rounded-full mt-3">
          <div className="h-full rounded-full" style={{ width: '68%', background: 'linear-gradient(90deg, #f59e0b, #d97706)' }} />
        </div>
        <div className="font-mono text-slate-400 mt-1" style={{ fontSize: 12 }}>+30W rimanenti \u00B7 ~16 settimane</div>
      </G>

      {/* Races / Objectives */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <Label>Obiettivi</Label>
          <button
            onClick={() => setShowAddRace(true)}
            className="font-mono text-amber-400 hover:text-amber-300 transition-colors"
            style={{ fontSize: 12 }}
          >
            + Aggiungi obiettivo
          </button>
        </div>

        {/* Add race form */}
        {showAddRace && (
          <G className="!p-3 mb-2" style={{ border: '1px solid rgba(245,158,11,0.2)' }}>
            <input
              type="text" placeholder="Nome gara / obiettivo"
              value={newRace.name} onChange={e => setNewRace(p => ({ ...p, name: e.target.value }))}
              className="w-full bg-[#0f172a] border border-slate-700/50 rounded-lg px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-500/50 font-mono mb-2"
            />
            <div className="flex gap-2 mb-2">
              <input
                type="text" placeholder="Data (es. 7 Giu)"
                value={newRace.date} onChange={e => setNewRace(p => ({ ...p, date: e.target.value }))}
                className="flex-1 bg-[#0f172a] border border-slate-700/50 rounded-lg px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-500/50 font-mono"
              />
              <input
                type="text" placeholder="Distanza (es. 138km)"
                value={newRace.dist} onChange={e => setNewRace(p => ({ ...p, dist: e.target.value }))}
                className="flex-1 bg-[#0f172a] border border-slate-700/50 rounded-lg px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-500/50 font-mono"
              />
            </div>
            <div className="flex items-center gap-2 mb-2">
              <span className="font-mono text-slate-400" style={{ fontSize: 12 }}>Priorita:</span>
              {['A', 'B', 'C'].map(p => (
                <button key={p} onClick={() => setNewRace(prev => ({ ...prev, pri: p }))}
                  className="font-mono font-bold rounded px-2 py-0.5 transition-colors"
                  style={{
                    fontSize: 12,
                    color: newRace.pri === p ? PRI_COLORS[p] : '#475569',
                    background: newRace.pri === p ? `${PRI_COLORS[p]}20` : 'transparent',
                    border: `1px solid ${newRace.pri === p ? PRI_COLORS[p] + '40' : 'transparent'}`,
                  }}>
                  {p}
                </button>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowAddRace(false)}
                className="font-mono text-slate-400 hover:text-white text-xs">Annulla</button>
              <button onClick={addRace} disabled={!newRace.name.trim()}
                className="font-mono text-amber-400 hover:text-amber-300 disabled:opacity-30 text-xs">Salva</button>
            </div>
          </G>
        )}

        {races.length === 0 && !showAddRace ? (
          <G className="text-center py-6">
            <p className="text-slate-400 text-sm mb-1">Nessun obiettivo impostato</p>
            <p className="font-mono text-slate-400" style={{ fontSize: 12 }}>Aggiungi gare o traguardi per la stagione</p>
          </G>
        ) : (
          <div className="flex flex-col gap-1.5">
            {races.map(r => {
              const c = PRI_COLORS[r.pri] || PRI_COLORS.C
              return (
                <div key={r.id} className="flex items-center gap-3 px-3 py-2 rounded-r-lg"
                  style={{ background: `linear-gradient(90deg, ${c}11, transparent)`, borderLeft: `3px solid ${c}` }}>
                  <div className="flex-1">
                    <div className="text-sm font-semibold text-slate-50">{r.name}</div>
                    <div className="font-mono text-slate-400" style={{ fontSize: 12 }}>
                      {r.date}{r.dist ? ` \u00B7 ${r.dist}` : ''}
                    </div>
                  </div>
                  <span className="font-mono font-bold rounded px-1.5 py-0.5"
                    style={{ fontSize: 12, color: c, background: `${c}15` }}>{r.pri}</span>
                  <button onClick={() => removeRace(r.id)}
                    className="text-slate-400 hover:text-red-400 transition-colors" style={{ fontSize: 12 }}>{'\u00D7'}</button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Week plan — linked to "Crea workout" */}
      <G>
        <Label>Piano Settimanale</Label>
        <div className="text-center py-6">
          <p className="text-slate-400 text-sm mb-2">Nessun piano per questa settimana</p>
          <p className="font-mono text-slate-400 mb-4" style={{ fontSize: 12 }}>
            Usa &quot;Carica workout&quot; dalla Dashboard per creare il piano
          </p>
          <div className="flex items-center justify-center gap-1 text-amber-500/40">
            {['L', 'M', 'M', 'G', 'V', 'S', 'D'].map((d, i) => (
              <div key={i} className="w-8 h-8 rounded-lg flex items-center justify-center font-mono"
                style={{ fontSize: 12, background: 'rgba(148,163,184,0.04)', border: '1px solid rgba(148,163,184,0.06)' }}>
                <span className="text-slate-400">{d}</span>
              </div>
            ))}
          </div>
        </div>
      </G>
    </div>
  )
}
