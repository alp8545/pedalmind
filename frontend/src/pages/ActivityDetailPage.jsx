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
    avgPower: lap.averagePower ? Math.round(lap.averagePower) : 0,
    avgHR: lap.averageHR ? Math.round(lap.averageHR) : null,
    np: lap.normalizedPower ? Math.round(lap.normalizedPower) : null,
    speedKmh: lap.averageSpeed ? +(lap.averageSpeed * 3.6).toFixed(1) : null,
    distKm: lap.distance ? +(lap.distance / 1000).toFixed(1) : null,
    durationMin: lap.duration ? +(lap.duration / 60).toFixed(1) : null,
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

  // Color bar by power zone (based on FTP 265)
  const FTP = 265
  const powerToColor = (w) => {
    if (!w || w === 0) return '#334155'
    const pct = w / FTP
    if (pct < 0.55) return ZONE_COLORS[0]  // Z1
    if (pct < 0.75) return ZONE_COLORS[1]  // Z2
    if (pct < 0.90) return ZONE_COLORS[2]  // Z3
    if (pct < 1.05) return ZONE_COLORS[3]  // Z4
    if (pct < 1.20) return ZONE_COLORS[4]  // Z5
    if (pct < 1.50) return ZONE_COLORS[5]  // Z6
    return ZONE_COLORS[6]                   // Z7
  }

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

      {/* Power blocks chart — shows avg power per lap, colored by zone */}
      {lapData.length > 1 && (
        <G>
          <Label>Blocchi di Potenza ({lapData.length} laps)</Label>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={lapData} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
              <XAxis dataKey="lap" tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'DM Mono' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 10, fontFamily: 'DM Mono' }} axisLine={false} tickLine={false} unit="W" width={45} />
              <Tooltip content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null
                const d = payload[0].payload
                return (
                  <div className="rounded-lg p-2.5 text-xs font-mono" style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}>
                    <div className="font-semibold text-white mb-1">Lap {label}</div>
                    <div>Potenza: <span className="text-amber-400">{d.avgPower}W</span></div>
                    {d.np != null && <div>NP: <span className="text-amber-400">{d.np}W</span></div>}
                    {d.avgHR != null && <div>FC: <span className="text-red-400">{d.avgHR} bpm</span></div>}
                    {d.durationMin != null && <div>Durata: {d.durationMin} min</div>}
                    {d.speedKmh != null && <div>Vel: {d.speedKmh} km/h</div>}
                    {d.cadence != null && <div>Cadenza: {d.cadence} rpm</div>}
                    {d.elevGain != null && <div>Disliv: {d.elevGain}m</div>}
                  </div>
                )
              }} />
              <Bar dataKey="avgPower" radius={[3, 3, 0, 0]}>
                {lapData.map((d, i) => (
                  <Cell key={i} fill={powerToColor(d.avgPower)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-3 mt-1.5 flex-wrap">
            {['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7'].map((z, i) => (
              <div key={z} className="flex items-center gap-1">
                <div className="rounded-sm" style={{ width: 8, height: 8, background: ZONE_COLORS[i] }} />
                <span className="font-mono text-slate-500" style={{ fontSize: 7 }}>{z}</span>
              </div>
            ))}
          </div>
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
