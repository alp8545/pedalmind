import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { BarChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ComposedChart } from 'recharts'
import { api } from '../api'
import { G, Label } from '../components/ui'
import ZoneBar, { ZONE_COLORS } from '../components/charts/ZoneBar'

const ZONE_LABELS = ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7']

function fmtDuration(secs) {
  if (!secs) return '\u2014'
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  const s = Math.floor(secs % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

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

  if (loading) return <div className="text-center py-12 text-slate-400" style={{ fontSize: 14 }}>Loading...</div>
  if (error) return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <Link to="/" className="text-amber-400 hover:underline mb-4 inline-block font-mono" style={{ fontSize: 14 }}>{'\u2190'} Back</Link>
      <div className="text-center py-12 text-red-400" style={{ fontSize: 14 }}>{error}</div>
    </div>
  )
  if (!activity) return <div className="text-center py-12 text-slate-400" style={{ fontSize: 14 }}>Activity not found</div>

  const duration = activity.duration_secs ? fmtDuration(activity.duration_secs) : null

  const laps = activity.splits_data?.lapDTOs || []
  const lapData = laps.map((lap, i) => ({
    lap: i + 1,
    avgPower: lap.averagePower ? Math.round(lap.averagePower) : 0,
    avgHR: lap.averageHR ? Math.round(lap.averageHR) : null,
    np: lap.normalizedPower ? Math.round(lap.normalizedPower) : null,
    speedKmh: lap.averageSpeed ? +(lap.averageSpeed * 3.6).toFixed(1) : null,
    distKm: lap.distance ? +(lap.distance / 1000).toFixed(1) : null,
    durationSecs: lap.duration || 0,
    cadence: lap.averageBikeCadence || lap.averageBikingCadence ? Math.round(lap.averageBikeCadence || lap.averageBikingCadence) : null,
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

  const FTP = 265
  const powerToColor = (w) => {
    if (!w || w === 0) return '#475569'
    const pct = w / FTP
    if (pct < 0.55) return ZONE_COLORS[0]
    if (pct < 0.75) return ZONE_COLORS[1]
    if (pct < 0.90) return ZONE_COLORS[2]
    if (pct < 1.05) return ZONE_COLORS[3]
    if (pct < 1.20) return ZONE_COLORS[4]
    if (pct < 1.50) return ZONE_COLORS[5]
    return ZONE_COLORS[6]
  }

  // Decoupling from raw_data or analysis
  const decoupling = activity.raw_data?.decoupling_pct
  const decAssessment = decoupling != null
    ? (decoupling < 5 ? 'Ottimo' : decoupling < 8 ? 'Accettabile' : 'Elevato')
    : null

  return (
    <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col gap-4">
      <Link to="/" className="text-amber-400 hover:underline inline-block font-mono" style={{ fontSize: 13 }}>{'\u2190'} Back</Link>

      {/* Header */}
      <div>
        <div className="font-mono text-slate-400 uppercase" style={{ fontSize: 12, letterSpacing: 1 }}>
          {activity.start_time ? new Date(activity.start_time).toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric' }).toUpperCase() : ''}
        </div>
        <h1 className="text-xl font-normal text-slate-50 mt-0.5">{activity.name}</h1>
        <div className="font-mono text-slate-400 mt-0.5" style={{ fontSize: 13 }}>
          {duration}{activity.distance_m ? ` \u00B7 ${(activity.distance_m / 1000).toFixed(1)}km` : ''}
          {activity.elevation_gain ? ` \u00B7 ${Math.round(activity.elevation_gain)}m D+` : ''}
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-2">
        {[
          { l: 'Potenza Media', v: activity.avg_power ? `${activity.avg_power}W` : null, s: activity.normalized_power && activity.normalized_power !== activity.avg_power ? `NP: ${activity.normalized_power}W` : null },
          { l: 'FC Media', v: activity.avg_hr ? `${activity.avg_hr}bpm` : null, s: activity.max_hr ? `Max: ${activity.max_hr}` : null },
          { l: 'TSS', v: activity.tss ? Math.round(activity.tss) : null, s: activity.intensity_factor ? `IF: ${activity.intensity_factor.toFixed(2)}` : null },
          { l: 'Cadenza', v: activity.avg_cadence ? `${activity.avg_cadence}rpm` : null },
        ].map(m => (
          <G key={m.l} className="!p-3">
            <div className="font-mono text-slate-400 uppercase" style={{ fontSize: 10, letterSpacing: 1 }}>{m.l}</div>
            <div className="font-mono font-bold text-slate-50 mt-0.5" style={{ fontSize: 22 }}>{m.v ?? '\u2014'}</div>
            {m.s && <div className="font-mono text-slate-400" style={{ fontSize: 11 }}>{m.s}</div>}
          </G>
        ))}
      </div>

      {/* Power blocks — time-proportional width */}
      {lapData.length > 1 && (() => {
        const totalSecs = lapData.reduce((s, d) => s + d.durationSecs, 0) || 1
        const maxPower = Math.max(...lapData.map(d => d.avgPower).filter(Boolean), 1)
        const chartHeight = 160
        return (
        <G>
          <Label>Blocchi di Potenza ({lapData.length} laps)</Label>
          <div className="flex items-end gap-px mt-1" style={{ height: chartHeight }}>
            {lapData.map((d, i) => {
              const widthPct = (d.durationSecs / totalSecs) * 100
              const heightPct = d.avgPower > 0 ? Math.max((d.avgPower / maxPower) * 100, 8) : 8
              const color = powerToColor(d.avgPower)
              return (
                <div key={i} className="relative group flex flex-col justify-end"
                  style={{ width: `${widthPct}%`, height: '100%' }}>
                  {/* Bar */}
                  <div className="rounded-t-sm transition-opacity group-hover:opacity-80"
                    style={{ height: `${heightPct}%`, background: color, minHeight: 4 }} />
                  {/* Time label (only show if block is wide enough) */}
                  {widthPct > 6 && (
                    <div className="font-mono text-center text-slate-500 mt-0.5" style={{ fontSize: 8 }}>
                      {fmtDuration(d.durationSecs)}
                    </div>
                  )}
                  {/* Hover tooltip */}
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-10 pointer-events-none">
                    <div className="rounded-lg p-2 font-mono whitespace-nowrap"
                      style={{ background: '#1e293b', border: '1px solid #475569', color: '#e2e8f0', fontSize: 11 }}>
                      <div className="font-semibold text-white">Lap {i + 1}</div>
                      <div>Potenza: <span style={{ color }}>{d.avgPower}W</span></div>
                      {d.avgHR != null && <div>FC: <span className="text-red-400">{d.avgHR}bpm</span></div>}
                      <div>Durata: {fmtDuration(d.durationSecs)}</div>
                      {d.cadence != null && <div>Cadenza: {d.cadence}rpm</div>}
                      {d.elevGain != null && <div>Disliv: {d.elevGain}m</div>}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
          {/* Legend */}
          <div className="flex gap-3 mt-1.5 flex-wrap items-center">
            {['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7'].map((z, i) => (
              <div key={z} className="flex items-center gap-1">
                <div className="rounded-sm" style={{ width: 8, height: 8, background: ZONE_COLORS[i] }} />
                <span className="font-mono text-slate-400" style={{ fontSize: 9 }}>{z}</span>
              </div>
            ))}
          </div>
        </G>
        )
      })()}

      {/* Power Zones */}
      {powerZoneData.length > 0 && totalZoneSecs > 0 && (
        <G>
          <Label>Zone di Potenza</Label>
          {powerZoneData.map(z => (
            <ZoneBar key={z.zone} zone={z.zone} pct={z.pct} time={fmtDuration(z.seconds)} color={ZONE_COLORS[z.zone - 1]} />
          ))}
        </G>
      )}

      {/* Decoupling + HR Recovery cards */}
      {(activity.decoupling != null || activity.hr_recovery_30s != null || activity.hr_recovery_60s != null) && (
        <div className="grid grid-cols-2 gap-2">
          {/* Decoupling card */}
          {activity.decoupling != null && (() => {
            const dec = activity.decoupling
            const decColor = dec < 3 ? '#22c55e' : dec <= 5 ? '#f59e0b' : '#ef4444'
            return (
              <G className="!p-3">
                <Label>DECOUPLING Pw:Hr</Label>
                <div className="font-mono font-bold mt-0.5" style={{ fontSize: 24, color: decColor }}>
                  {dec.toFixed(1)}%
                </div>
                <div className="font-mono text-slate-500 mt-1" style={{ fontSize: 10 }}>
                  {'< 3% ottimo | 3-5% buono | > 5% da migliorare'}
                </div>
              </G>
            )
          })()}

          {/* HR Recovery card */}
          {(activity.hr_recovery_30s != null || activity.hr_recovery_60s != null) && (() => {
            const drop60 = activity.hr_recovery_60s ?? activity.hr_recovery_30s ?? 0
            const recColor = drop60 > 30 ? '#22c55e' : drop60 >= 20 ? '#f59e0b' : '#ef4444'
            const quality = drop60 > 30 ? 'Ottimo' : drop60 >= 20 ? 'Buono' : 'Da migliorare'
            return (
              <G className="!p-3">
                <Label>RECUPERO HR</Label>
                <div className="font-mono font-bold mt-0.5" style={{ fontSize: 24, color: recColor }}>
                  -{drop60} bpm
                </div>
                <div className="font-mono text-slate-400 mt-0.5" style={{ fontSize: 11 }}>
                  in ~60s dopo sforzo max
                </div>
                <div className="font-mono mt-1.5" style={{ fontSize: 11, color: recColor }}>
                  {quality}
                </div>
                <div className="font-mono text-slate-500 mt-1" style={{ fontSize: 10 }}>
                  {'>'}30bpm ottimo | 20-30 buono | {'<'}20 da migliorare
                </div>
              </G>
            )
          })()}
        </div>
      )}

      {/* AI Analysis + Decoupling (legacy raw_data fallback) */}
      {(activity.analysis_text || (decoupling != null && activity.decoupling == null)) && (
        <G style={{ borderLeft: '3px solid #f59e0b', borderRadius: '3px 14px 14px 3px' }}>
          <div className="flex items-center gap-1.5 mb-2">
            <span style={{ fontSize: 14 }}>{'\uD83D\uDEB4'}</span>
            <span className="font-mono text-amber-500 uppercase" style={{ fontSize: 10, letterSpacing: 1.5 }}>Insight PedalMind</span>
          </div>
          {decoupling != null && activity.decoupling == null && (
            <div className="flex items-center gap-3 mb-3 p-2 rounded-lg" style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.15)' }}>
              <div>
                <div className="font-mono text-slate-400 uppercase" style={{ fontSize: 10 }}>Decoupling Cardiaco</div>
                <div className="font-mono font-bold text-amber-400" style={{ fontSize: 20 }}>{decoupling.toFixed(1)}%</div>
              </div>
              <div className="font-mono text-slate-300" style={{ fontSize: 13 }}>{decAssessment}</div>
            </div>
          )}
          {activity.analysis_text && (
            <p className="text-slate-300 leading-relaxed whitespace-pre-wrap" style={{ fontSize: 14 }}>{activity.analysis_text}</p>
          )}
        </G>
      )}
    </div>
  )
}
