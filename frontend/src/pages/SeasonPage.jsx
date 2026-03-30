import { useEffect, useState } from 'react'
import { api } from '../api'
import { G, Label } from '../components/ui'
import DonutRing from '../components/charts/DonutRing'

const PHASES = [
  { n: 'BASE', c: '#3b82f6', a: true }, { n: 'BUILD', c: '#f59e0b', a: true },
  { n: 'PEAK', c: '#ef4444', a: false }, { n: 'RACE', c: '#22c55e', a: false },
  { n: 'REC', c: '#8b5cf6', a: false },
]

const PRI_COLORS = { A: '#f59e0b', B: '#22d3ee', C: '#8b5cf6' }
const DAY_LABELS = ['L', 'M', 'M', 'G', 'V', 'S', 'D']
const DAY_NAMES = ['Lunedi', 'Martedi', 'Mercoledi', 'Giovedi', 'Venerdi', 'Sabato', 'Domenica']

const STEP_TYPE_COLORS = {
  'power.zone': '#f59e0b',
  'power.range': '#f59e0b',
  'heart.rate.zone': '#ef4444',
}

function formatDuration(secs) {
  if (!secs) return ''
  const m = Math.floor(secs / 60)
  return m >= 60 ? `${Math.floor(m / 60)}h${m % 60 > 0 ? m % 60 + 'm' : ''}` : `${m}m`
}

function StepBar({ step, totalSecs }) {
  const pct = totalSecs > 0 ? Math.max((step.duration_secs || 0) / totalSecs * 100, 4) : 10
  const color = step.target ? (STEP_TYPE_COLORS[step.target.type] || '#64748b') : '#334155'
  const isRecovery = step.target?.type === 'power.zone' && step.target?.value <= 2

  return (
    <div title={step.description || ''}
      className="rounded-sm flex items-end justify-center overflow-hidden"
      style={{
        width: `${pct}%`,
        minWidth: 6,
        height: isRecovery ? 16 : 28,
        background: isRecovery ? `${color}30` : `${color}90`,
      }}>
      {step.duration_secs >= 300 && (
        <span className="font-mono text-white/70 leading-none" style={{ fontSize: 7 }}>
          {formatDuration(step.duration_secs)}
        </span>
      )}
    </div>
  )
}

function WorkoutCard({ workout, onToggle, expanded }) {
  // Flatten steps for the visual bar
  const flatSteps = []
  const totalSecs = workout.estimated_duration_secs || 0
  for (const step of (workout.steps || [])) {
    if (step.type === 'repeat') {
      for (let i = 0; i < (step.iterations || 1); i++) {
        for (const sub of (step.steps || [])) flatSteps.push(sub)
      }
    } else {
      flatSteps.push(step)
    }
  }

  return (
    <div className="mb-1.5">
      <button onClick={onToggle} className="w-full text-left">
        <G className="!p-3 transition-colors hover:bg-white/[0.02]"
          style={expanded ? { border: '1px solid rgba(245,158,11,0.2)' } : {}}>
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-mono font-semibold text-slate-50 text-sm">{workout.name}</span>
            <div className="flex items-center gap-2">
              {workout.tss_estimate && (
                <span className="font-mono text-amber-500" style={{ fontSize: 11 }}>
                  TSS {workout.tss_estimate}
                </span>
              )}
              <span className="font-mono text-slate-500" style={{ fontSize: 11 }}>
                {formatDuration(totalSecs)}
              </span>
            </div>
          </div>
          {/* Visual step composition bar */}
          <div className="flex gap-px items-end" style={{ height: 28 }}>
            {flatSteps.map((s, i) => <StepBar key={i} step={s} totalSecs={totalSecs} />)}
          </div>
        </G>
      </button>

      {/* Expanded detail view */}
      {expanded && (
        <div className="mt-1 mx-1 rounded-lg p-3" style={{ background: 'rgba(15,23,42,0.6)' }}>
          {(workout.steps || []).map((step, i) => (
            <WorkoutStepDetail key={i} step={step} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}

function WorkoutStepDetail({ step, index }) {
  if (step.type === 'repeat') {
    return (
      <div className="mb-2">
        <div className="font-mono text-amber-400 mb-1" style={{ fontSize: 11 }}>
          {step.iterations}x Ripetizioni
        </div>
        <div className="ml-3 border-l border-amber-500/20 pl-2">
          {(step.steps || []).map((s, i) => (
            <WorkoutStepDetail key={i} step={s} index={i} />
          ))}
        </div>
      </div>
    )
  }

  const target = step.target
  let targetText = ''
  if (target?.type === 'power.zone') targetText = `Z${target.value}`
  else if (target?.type === 'power.range') targetText = `${target.value_low}-${target.value_high}W`
  else if (target?.type === 'heart.rate.zone') targetText = `HR Z${target.value}`

  const cadence = step.cadence
  const cadenceText = cadence ? `${cadence.low}-${cadence.high}rpm` : ''

  return (
    <div className="flex items-center gap-3 py-1 border-b border-slate-700/20 last:border-0">
      <span className="font-mono text-slate-500 w-10 text-right" style={{ fontSize: 11 }}>
        {formatDuration(step.duration_secs)}
      </span>
      <span className="font-mono font-semibold text-amber-400" style={{ fontSize: 12 }}>
        {targetText || '—'}
      </span>
      {cadenceText && (
        <span className="font-mono text-cyan-400/70" style={{ fontSize: 10 }}>
          {cadenceText}
        </span>
      )}
      <span className="font-mono text-slate-400 flex-1 text-right" style={{ fontSize: 10 }}>
        {step.description || ''}
      </span>
    </div>
  )
}

function WeekPlan() {
  const [workouts, setWorkouts] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)

  useEffect(() => {
    api('/api/garmin/workout/week')
      .then(data => setWorkouts(data.workouts || []))
      .catch(() => setWorkouts([]))
      .finally(() => setLoading(false))
  }, [])

  // Group workouts by day of week (0=Mon ... 6=Sun)
  const byDay = {}
  for (const w of workouts) {
    if (w.schedule_date) {
      const d = new Date(w.schedule_date)
      const dow = (d.getDay() + 6) % 7 // Mon=0
      if (!byDay[dow]) byDay[dow] = []
      byDay[dow].push(w)
    }
  }

  const hasWorkouts = workouts.length > 0

  return (
    <G>
      <Label>Piano Settimanale</Label>

      {loading ? (
        <div className="text-center py-4">
          <span className="font-mono text-slate-500 text-xs">Caricamento...</span>
        </div>
      ) : !hasWorkouts ? (
        <div className="text-center py-4">
          <p className="text-slate-400 text-sm mb-2">Nessun workout questa settimana</p>
          <p className="font-mono text-slate-500" style={{ fontSize: 11 }}>
            Carica un workout dalla Dashboard con una data per vederlo qui
          </p>
          {/* Empty day indicators */}
          <div className="flex items-center justify-center gap-1 mt-3">
            {DAY_LABELS.map((d, i) => (
              <div key={i} className="w-8 h-8 rounded-lg flex items-center justify-center font-mono"
                style={{ fontSize: 12, background: 'rgba(148,163,184,0.04)', border: '1px solid rgba(148,163,184,0.06)' }}>
                <span className="text-slate-400">{d}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-2">
          {/* Day header row */}
          <div className="flex gap-1 mb-2">
            {DAY_LABELS.map((d, i) => {
              const has = byDay[i]?.length > 0
              return (
                <div key={i} className="flex-1 text-center">
                  <div className={`font-mono rounded-md py-1 ${has ? 'bg-amber-500/15 text-amber-400' : 'text-slate-500'}`}
                    style={{ fontSize: 11 }}>{d}</div>
                </div>
              )
            })}
          </div>
          {/* Workouts listed by day */}
          {[0, 1, 2, 3, 4, 5, 6].map(dow => {
            const dayWorkouts = byDay[dow]
            if (!dayWorkouts) return null
            return (
              <div key={dow}>
                <div className="font-mono text-slate-500 mb-1 mt-2" style={{ fontSize: 10 }}>
                  {DAY_NAMES[dow].toUpperCase()}
                </div>
                {dayWorkouts.map(w => (
                  <WorkoutCard key={w.id} workout={w}
                    expanded={expandedId === w.id}
                    onToggle={() => setExpandedId(expandedId === w.id ? null : w.id)} />
                ))}
              </div>
            )
          })}
        </div>
      )}
    </G>
  )
}

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

      {/* Piano Settimanale */}
      <WeekPlan />
    </div>
  )
}
