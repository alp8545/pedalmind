import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api } from '../api'

const ZONE_COLORS = ['#22c55e', '#84cc16', '#eab308', '#f97316', '#ef4444', '#a855f7', '#ec4899']
const ZONE_LABELS = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7']
const ZONE_KEYS = ['z1_recovery', 'z2_endurance', 'z3_tempo', 'z4_threshold', 'z5_vo2max', 'z6_anaerobic', 'z7_neuromuscular']

const SCORE_COLORS = { 1: '#ef4444', 2: '#ef4444', 3: '#f97316', 4: '#f97316', 5: '#eab308', 6: '#eab308', 7: '#84cc16', 8: '#22c55e', 9: '#22c55e', 10: '#22c55e' }
const FLAG_STYLES = {
  warning: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
  positive: 'bg-green-500/10 border-green-500/30 text-green-400',
  info: 'bg-blue-500/10 border-blue-500/30 text-blue-400',
}

export default function RideDetailPage() {
  const { rideId } = useParams()
  const [ride, setRide] = useState(null)
  const [loading, setLoading] = useState(true)
  const [reanalyzing, setReanalyzing] = useState(false)

  useEffect(() => {
    api(`/api/rides/${rideId}`)
      .then(setRide)
      .catch(err => {
        console.error(`Failed to load ride ${rideId}:`, err)
      })
      .finally(() => setLoading(false))
  }, [rideId])

  async function handleReanalyze() {
    setReanalyzing(true)
    try {
      const result = await api(`/api/rides/${rideId}/reanalyze`, { method: 'POST' })
      setRide(prev => ({ ...prev, analysis_json: result.analysis }))
    } catch { }
    setReanalyzing(false)
  }

  if (loading) return <div className="text-center py-12 text-slate-500">Loading...</div>
  if (!ride) return <div className="text-center py-12 text-slate-500">Ride not found</div>

  const s = ride.ride_data_json?.summary || {}
  const analysis = ride.analysis_json
  const powerZones = ride.ride_data_json?.zones?.power_zones
  const powerCurve = ride.ride_data_json?.power_curve

  // Build power zone chart data
  const zoneData = powerZones ? ZONE_KEYS.map((key, i) => ({
    name: ZONE_LABELS[i],
    seconds: powerZones[key] || 0,
  })) : []
  const totalZoneSec = zoneData.reduce((a, b) => a + b.seconds, 0)

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      <Link to="/" className="text-sm text-sky-400 hover:underline mb-4 inline-block">&larr; Back to rides</Link>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">
          {new Date(ride.ride_date).toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
        </h1>
        <button
          onClick={handleReanalyze}
          disabled={reanalyzing}
          className="text-sm bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
        >
          {reanalyzing ? 'Analyzing...' : 'Reanalyze'}
        </button>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <Metric label="Distance" value={`${s.distance_km?.toFixed(1)} km`} />
        <Metric label="Duration" value={`${Math.round((s.duration_sec || 0) / 60)} min`} />
        <Metric label="Avg Power" value={s.avg_power_w ? `${s.avg_power_w}W` : '-'} />
        <Metric label="NP" value={s.normalized_power_w ? `${s.normalized_power_w}W` : '-'} />
        <Metric label="TSS" value={s.training_stress_score?.toFixed(0) ?? '-'} />
        <Metric label="IF" value={s.intensity_factor?.toFixed(2) ?? '-'} />
        <Metric label="Avg HR" value={s.avg_hr ? `${s.avg_hr} bpm` : '-'} />
        <Metric label="Max HR" value={s.max_hr ? `${s.max_hr} bpm` : '-'} />
        <Metric label="Elevation" value={s.elevation_gain_m ? `${s.elevation_gain_m}m` : '-'} />
        <Metric label="Cadence" value={s.avg_cadence ? `${s.avg_cadence} rpm` : '-'} />
        <Metric label="Decoupling" value={ride.ride_data_json?.cardiac_decoupling_pct != null ? `${ride.ride_data_json.cardiac_decoupling_pct.toFixed(1)}%` : '-'} />
      </div>

      {/* Power curve */}
      {powerCurve && Object.values(powerCurve).some(v => v != null) && (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-4 mb-6">
          <h2 className="text-base font-semibold text-white mb-3">Power Curve</h2>
          <div className="grid grid-cols-3 sm:grid-cols-7 gap-2 text-sm text-center">
            {Object.entries(powerCurve).filter(([, v]) => v != null).map(([k, v]) => (
              <div key={k} className="bg-slate-800 rounded-lg p-2">
                <div className="text-slate-500 text-xs">{k.replace('best_', '')}</div>
                <div className="text-white font-medium">{v}W</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Power zones chart */}
      {zoneData.length > 0 && totalZoneSec > 0 && (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-4 mb-6">
          <h2 className="text-base font-semibold text-white mb-3">Power Zones</h2>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={zoneData}>
              <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} tickFormatter={v => `${Math.round(v / totalZoneSec * 100)}%`} />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0', fontSize: '13px' }}
                formatter={(v) => [`${Math.round(v / totalZoneSec * 100)}% (${Math.round(v / 60)}min)`, 'Time']}
              />
              <Bar dataKey="seconds" radius={[4, 4, 0, 0]}>
                {zoneData.map((_, i) => <Cell key={i} fill={ZONE_COLORS[i]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* AI Analysis */}
      {analysis && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-white">AI Analysis</h2>

          {/* Summary + ride type */}
          <div className="bg-slate-900 rounded-xl border border-slate-800 p-4">
            {analysis.ride_type_detected && (
              <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-sky-500/20 text-sky-400 mb-2">
                {analysis.ride_type_detected.replace(/_/g, ' ')}
              </span>
            )}
            <p className="text-slate-300 text-sm">{analysis.summary_text}</p>
          </div>

          {/* Scores */}
          {analysis.scores && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {Object.entries(analysis.scores).map(([key, val]) => (
                <div key={key} className="bg-slate-900 rounded-xl border border-slate-800 p-3 text-center">
                  <div className="text-xs text-slate-500 mb-1">{key.replace(/_/g, ' ')}</div>
                  <div className="text-2xl font-bold" style={{ color: SCORE_COLORS[val] || '#94a3b8' }}>{val}</div>
                  <div className="text-xs text-slate-600">/10</div>
                </div>
              ))}
            </div>
          )}

          {/* Sections */}
          {analysis.sections?.map((sec, i) => (
            <div key={i} className="bg-slate-900 rounded-xl border border-slate-800 p-4">
              <h3 className="text-sm font-semibold text-white mb-1">{sec.title}</h3>
              <p className="text-sm text-slate-400">{sec.content}</p>
            </div>
          ))}

          {/* Flags */}
          {analysis.flags?.length > 0 && (
            <div className="space-y-2">
              {analysis.flags.map((flag, i) => (
                <div key={i} className={`border rounded-lg px-3 py-2 text-sm ${FLAG_STYLES[flag.type] || FLAG_STYLES.info}`}>
                  {flag.message}
                </div>
              ))}
            </div>
          )}

          <div className="text-xs text-slate-600">
            Model: {analysis.model_used} | Tokens: {(analysis.tokens_input || 0) + (analysis.tokens_output || 0)}
          </div>
        </div>
      )}

      {!analysis && (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-6 text-center text-slate-500 text-sm">
          No AI analysis available. Click "Reanalyze" to generate one.
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800 p-3">
      <div className="text-xs text-slate-500 mb-0.5">{label}</div>
      <div className="text-lg font-semibold text-white">{value}</div>
    </div>
  )
}
