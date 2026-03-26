import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api } from '../api'
import { G, Label } from '../components/ui'
import ZoneBar, { ZONE_COLORS } from '../components/charts/ZoneBar'

const ZONE_LABELS = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7']

export default function ActivityDetailPage() {
  const { activityId } = useParams()
  const [activity, setActivity] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api(`/api/garmin/activities/${activityId}`)
      .then(setActivity)
      .catch(err => { console.error(`Failed to load activity ${activityId}:`, err); setError(err.message || 'Failed to load activity') })
      .finally(() => setLoading(false))
  }, [activityId])

  if (loading) return <div className="text-center py-12 text-slate-500">Loading...</div>
  if (error) return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <Link to="/" className="text-sm text-amber-400 hover:underline mb-4 inline-block font-mono">{'\u2190'} Back</Link>
      <div className="text-center py-12 text-red-400">{error}</div>
    </div>
  )
  if (!activity) return <div className="text-center py-12 text-slate-500">Activity not found</div>

  const duration = activity.duration_secs
    ? `${Math.floor(activity.duration_secs / 3600)}h${String(Math.floor((activity.duration_secs % 3600) / 60)).padStart(2, '0')}m`
    : null

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

  const powerZonesRaw = activity.raw_data?.powerTimeInZones || []
  const totalZoneSecs = powerZonesRaw.reduce((sum, z) => sum + (z.secsInZone || 0), 0)
  const powerZoneData = powerZonesRaw.map((z, i) => ({
    zone: i + 1,
    label: ZONE_LABELS[i] || `Z${z.zoneNumber}`,
    seconds: z.secsInZone || 0,
    pct: totalZoneSecs > 0 ? +((z.secsInZone / totalZoneSecs) * 100).toFixed(1) : 0,
    lowBound: z.zoneLowBoundary || 0,
  }))

  const fmtTime = (secs) => { const m = Math.floor(secs / 60); const s = Math.floor(secs % 60); return `${m}:${String(s).padStart(2, '0')}` }

  return (
    <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col gap-4">
      <Link to="/" className="text-sm text-amber-400 hover:underline inline-block font-mono" style={{ fontSize: 10 }}>{'\u2190'} Back</Link>

      {/* Header */}
      <div>
        <div className="font-mono text-slate-500 uppercase" style={{ fontSize: 11, letterSpacing: 1 }}>
          {activity.start_time ? new Date(activity.start_time).toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric' }).toUpperCase() : ''}
        </div>
        <h1 className="text-xl font-normal text-slate-50 mt-0.5">{activity.name}</h1>
        <div className="font-mono text-slate-600 mt-0.5" style={{ fontSize: 11 }}>
          {duration}{activity.distance_m ? ` \u00B7 ${(activity.distance_m / 1000).toFixed(1)}km` : ''}
          {activity.elevation_gain ? ` \u00B7 ${Math.round(activity.elevation_gain)}m D+` : ''}
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-2">
        {[
          { l: 'Potenza Media', v: activity.avg_power ? `${activity.avg_power}W` : null, s: activity.normalized_power ? `NP: ${activity.normalized_power}W` : null },
          { l: 'FC Media', v: activity.avg_hr ? `${activity.avg_hr}bpm` : null, s: activity.max_hr ? `Max: ${activity.max_hr}` : null },
          { l: 'TSS', v: activity.tss ? Math.round(activity.tss) : null, s: activity.intensity_factor ? `IF: ${activity.intensity_factor.toFixed(2)}` : null },
          { l: 'Cadenza', v: activity.avg_cadence ? `${activity.avg_cadence}rpm` : null },
        ].map(m => (
          <G key={m.l} className="!p-3">
            <div className="font-mono text-slate-500 uppercase" style={{ fontSize: 8, letterSpacing: 1 }}>{m.l}</div>
            <div className="font-mono font-bold text-slate-50 mt-0.5" style={{ fontSize: 20 }}>{m.v ?? '\u2014'}</div>
            {m.s && <div className="font-mono text-slate-600" style={{ fontSize: 9 }}>{m.s}</div>}
          </G>
        ))}
      </div>

      {/* Splits chart */}
      {lapData.length > 1 && (
        <G>
          <Label>Splits ({lapData.length} laps)</Label>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={lapData} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
              <XAxis dataKey="lap" tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'DM Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'DM Mono' }} axisLine={false} tickLine={false} unit=" km/h" width={55} />
              <Tooltip content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload
                return (
                  <div className="rounded-lg p-2.5 text-xs font-mono" style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}>
                    <div className="font-semibold text-white mb-1">Lap {label}</div>
                    <div>Speed: <span className="text-amber-400">{d.speedKmh} km/h</span></div>
                    {d.avgPower != null && <div>Power: <span className="text-amber-400">{d.avgPower}W</span></div>}
                    {d.avgHR != null && <div>HR: <span className="text-amber-400">{d.avgHR} bpm</span></div>}
                    {d.distKm != null && <div>Dist: {d.distKm}km</div>}
                  </div>
                )
              }} />
              <Bar dataKey="speedKmh" radius={[3, 3, 0, 0]}>
                {lapData.map((d, i) => {
                  const maxP = Math.max(...lapData.map(l => l.avgPower || 0))
                  const ratio = maxP > 0 && d.avgPower ? d.avgPower / maxP : 0.3
                  const r = Math.round(245 * ratio + 71 * (1 - ratio))
                  const g = Math.round(158 * ratio + 85 * (1 - ratio))
                  const b = Math.round(11 * ratio + 105 * (1 - ratio))
                  return <Cell key={i} fill={`rgb(${r},${g},${b})`} />
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </G>
      )}

      {/* Power Zones — ZoneBar style */}
      {powerZoneData.length > 0 && totalZoneSecs > 0 && (
        <G>
          <Label>Zone di Potenza</Label>
          {powerZoneData.map(z => (
            <ZoneBar key={z.zone} zone={z.zone} pct={z.pct} time={fmtTime(z.seconds)} color={ZONE_COLORS[z.zone - 1]} />
          ))}
        </G>
      )}

      {/* AI Analysis — amber insight box */}
      {activity.analysis_text && (
        <G style={{ borderLeft: '3px solid #f59e0b', borderRadius: '3px 14px 14px 3px' }}>
          <div className="flex items-center gap-1.5 mb-2">
            <span style={{ fontSize: 13 }}>{'\u26A1'}</span>
            <span className="font-mono text-amber-500 uppercase" style={{ fontSize: 9, letterSpacing: 1.5 }}>Insight PedalMind</span>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">{activity.analysis_text}</p>
        </G>
      )}
    </div>
  )
}
