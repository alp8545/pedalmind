import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'

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
    : '-'

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      <Link to="/" className="text-sm text-sky-400 hover:underline mb-4 inline-block">&larr; Back</Link>

      <h1 className="text-2xl font-bold text-white mb-1">{activity.name}</h1>
      <p className="text-sm text-slate-500 mb-6">
        {activity.start_time ? new Date(activity.start_time).toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) : ''}
        {activity.sport ? ` — ${activity.sport}` : ''}
      </p>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <Metric label="Distance" value={activity.distance_m ? `${(activity.distance_m / 1000).toFixed(1)} km` : '-'} />
        <Metric label="Duration" value={duration} />
        <Metric label="Avg Power" value={activity.avg_power ? `${activity.avg_power}W` : '-'} />
        <Metric label="NP" value={activity.normalized_power ? `${activity.normalized_power}W` : '-'} />
        <Metric label="TSS" value={activity.tss ? Math.round(activity.tss) : '-'} />
        <Metric label="IF" value={activity.intensity_factor?.toFixed(2) ?? '-'} />
        <Metric label="Avg HR" value={activity.avg_hr ? `${activity.avg_hr} bpm` : '-'} />
        <Metric label="Max HR" value={activity.max_hr ? `${activity.max_hr} bpm` : '-'} />
        <Metric label="Max Power" value={activity.max_power ? `${activity.max_power}W` : '-'} />
        <Metric label="Cadence" value={activity.avg_cadence ? `${activity.avg_cadence} rpm` : '-'} />
        <Metric label="Elevation" value={activity.elevation_gain ? `${Math.round(activity.elevation_gain)}m` : '-'} />
        <Metric label="Calories" value={activity.calories ?? '-'} />
        <Metric label="Avg Speed" value={activity.avg_speed ? `${(activity.avg_speed * 3.6).toFixed(1)} km/h` : '-'} />
      </div>

      {/* Analysis */}
      {activity.analysis_text ? (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-4 mb-6">
          <h2 className="text-base font-semibold text-white mb-3">Analysis</h2>
          <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans">{activity.analysis_text}</pre>
        </div>
      ) : (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-6 text-center text-slate-500 text-sm mb-6">
          No analysis available. Use the &quot;Analyze&quot; button on the dashboard.
        </div>
      )}

      {/* Splits */}
      {activity.splits_data && (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-4">
          <h2 className="text-base font-semibold text-white mb-3">Splits</h2>
          <pre className="text-xs text-slate-400 whitespace-pre-wrap overflow-auto max-h-64 font-mono">
            {JSON.stringify(activity.splits_data, null, 2)}
          </pre>
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
