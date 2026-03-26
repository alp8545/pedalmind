import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api } from '../api'

const ZONE_COLORS = ['#475569', '#3b82f6', '#22c55e', '#f59e0b', '#f97316', '#ef4444', '#8b5cf6']
const ZONE_LABELS = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7']

export default function ActivityDetailPage() {
  const { activityId } = useParams()
  const [activity, setActivity] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api(`/api/garmin/activities/${activityId}`)
      .then(setActivity)
      .catch(err => {
        console.error(`Failed to load activity ${activityId}:`, err)
        setError(err.message || 'Failed to load activity')
      })
      .finally(() => setLoading(false))
  }, [activityId])

  if (loading) return <div className="text-center py-12 text-slate-500">Loading...</div>
  if (error) return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      <Link to="/" className="text-sm text-sky-400 hover:underline mb-4 inline-block">&larr; Back</Link>
      <div className="text-center py-12 text-red-400">{error}</div>
    </div>
  )
  if (!activity) return <div className="text-center py-12 text-slate-500">Activity not found</div>

  const duration = activity.duration_secs
    ? `${Math.floor(activity.duration_secs / 3600)}h${String(Math.floor((activity.duration_secs % 3600) / 60)).padStart(2, '0')}m`
    : null

  // Parse splits/laps from splits_data
  const laps = activity.splits_data?.lapDTOs || []
  const lapData = laps.map((lap, i) => ({
    lap: i + 1,
    speedKmh: lap.averageSpeed ? +(lap.averageSpeed * 3.6).toFixed(1) : 0,
    avgPower: lap.averagePower ? Math.round(lap.averagePower) : null,
    avgHR: lap.averageHR ? Math.round(lap.averageHR) : null,
    distKm: lap.distance ? +(lap.distance / 1000).toFixed(1) : null,
    durationMin: lap.duration ? Math.round(lap.duration / 60) : null,
    np: lap.normalizedPower ? Math.round(lap.normalizedPower) : null,
    cadence: lap.averageBikeCadence ? Math.round(lap.averageBikeCadence) : null,
    elevGain: lap.elevationGain ? Math.round(lap.elevationGain) : null,
  }))

  // Parse power zones from raw_data
  const powerZonesRaw = activity.raw_data?.powerTimeInZones || []
  const totalZoneSecs = powerZonesRaw.reduce((sum, z) => sum + (z.secsInZone || 0), 0)
  const powerZoneData = powerZonesRaw.map((z, i) => ({
    zone: ZONE_LABELS[i] || `Z${z.zoneNumber}`,
    seconds: z.secsInZone || 0,
    pct: totalZoneSecs > 0 ? +((z.secsInZone / totalZoneSecs) * 100).toFixed(1) : 0,
    lowBound: z.zoneLowBoundary || 0,
  }))

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      <Link to="/" className="text-sm text-sky-400 hover:underline mb-4 inline-block">&larr; Back</Link>

      <h1 className="text-2xl font-bold text-white mb-1">{activity.name}</h1>
      <p className="text-sm text-slate-500 mb-6">
        {activity.start_time ? new Date(activity.start_time).toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) : ''}
        {activity.sport ? ` — ${activity.sport}` : ''}
      </p>

      {/* 1. Metrics cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <Metric label="NP" value={activity.normalized_power ? `${activity.normalized_power}W` : null} />
        <Metric label="TSS" value={activity.tss ? Math.round(activity.tss) : null} />
        <Metric label="IF" value={activity.intensity_factor?.toFixed(2) ?? null} />
        <Metric label="Avg Power" value={activity.avg_power ? `${activity.avg_power}W` : null} />
        <Metric label="Avg HR" value={activity.avg_hr ? `${activity.avg_hr} bpm` : null} />
        <Metric label="Distance" value={activity.distance_m ? `${(activity.distance_m / 1000).toFixed(1)} km` : null} />
        <Metric label="Duration" value={duration} />
        <Metric label="Elevation" value={activity.elevation_gain ? `${Math.round(activity.elevation_gain)}m` : null} />
      </div>

      {/* 2. Splits chart */}
      {lapData.length > 1 && (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-4 mb-6">
          <h2 className="text-base font-semibold text-white mb-3">Splits ({lapData.length} laps)</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={lapData} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
              <XAxis
                dataKey="lap"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                unit=" km/h"
                width={65}
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0', fontSize: '13px' }}
                formatter={(value, name) => {
                  if (name === 'speedKmh') return [`${value} km/h`, 'Speed']
                  return [value, name]
                }}
                labelFormatter={(label) => `Lap ${label}`}
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-xs text-slate-300 shadow-xl">
                      <div className="font-semibold text-white mb-1.5">Lap {label}</div>
                      <div className="space-y-0.5">
                        <div>Speed: <span className="text-amber-400">{d.speedKmh} km/h</span></div>
                        {d.avgPower != null && <div>Avg Power: <span className="text-amber-400">{d.avgPower}W</span></div>}
                        {d.np != null && <div>NP: <span className="text-amber-400">{d.np}W</span></div>}
                        {d.avgHR != null && <div>Avg HR: <span className="text-amber-400">{d.avgHR} bpm</span></div>}
                        {d.distKm != null && <div>Distance: {d.distKm} km</div>}
                        {d.durationMin != null && <div>Duration: {d.durationMin} min</div>}
                        {d.cadence != null && <div>Cadence: {d.cadence} rpm</div>}
                        {d.elevGain != null && <div>Elev Gain: {d.elevGain}m</div>}
                      </div>
                    </div>
                  )
                }}
              />
              <Bar dataKey="speedKmh" radius={[3, 3, 0, 0]}>
                {lapData.map((d, i) => {
                  const maxPower = Math.max(...lapData.map(l => l.avgPower || 0))
                  const ratio = maxPower > 0 && d.avgPower ? d.avgPower / maxPower : 0.3
                  const r = Math.round(245 * ratio + 71 * (1 - ratio))
                  const g = Math.round(158 * ratio + 85 * (1 - ratio))
                  const b = Math.round(11 * ratio + 105 * (1 - ratio))
                  return <Cell key={i} fill={`rgb(${r},${g},${b})`} />
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-slate-600 mt-1">Bar color intensity reflects average power</p>
        </div>
      )}

      {/* 3. Power zones */}
      {powerZoneData.length > 0 && totalZoneSecs > 0 && (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-4 mb-6">
          <h2 className="text-base font-semibold text-white mb-3">Power Zones</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={powerZoneData} layout="vertical" margin={{ top: 5, right: 20, bottom: 5, left: 5 }}>
              <XAxis
                type="number"
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={v => `${v}%`}
              />
              <YAxis
                type="category"
                dataKey="zone"
                tick={{ fill: '#94a3b8', fontSize: 12, fontWeight: 600 }}
                axisLine={false}
                tickLine={false}
                width={30}
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#e2e8f0', fontSize: '13px' }}
                formatter={(value, _name, { payload }) => [
                  `${value}% (${Math.round(payload.seconds / 60)}min)  —  ${payload.lowBound}W+`,
                  payload.zone
                ]}
              />
              <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
                {powerZoneData.map((_, i) => <Cell key={i} fill={ZONE_COLORS[i] || '#64748b'} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 4. AI Analysis */}
      {activity.analysis_text && (
        <div className="bg-slate-900 rounded-xl border border-amber-500/20 p-5 mb-6">
          <h2 className="text-base font-semibold text-amber-400 mb-3">Analisi</h2>
          <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">{activity.analysis_text}</div>
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800 p-3">
      <div className="text-xs text-slate-500 mb-0.5">{label}</div>
      <div className="text-lg font-semibold text-white">{value ?? '—'}</div>
    </div>
  )
}
