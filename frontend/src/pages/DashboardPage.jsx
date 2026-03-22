import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const RIDE_TYPE_COLORS = {
  endurance: 'bg-green-500/20 text-green-400',
  tempo: 'bg-yellow-500/20 text-yellow-400',
  threshold: 'bg-orange-500/20 text-orange-400',
  vo2max_intervals: 'bg-red-500/20 text-red-400',
  sprint_intervals: 'bg-purple-500/20 text-purple-400',
  mixed: 'bg-blue-500/20 text-blue-400',
  race: 'bg-pink-500/20 text-pink-400',
  recovery: 'bg-teal-500/20 text-teal-400',
  group_ride: 'bg-indigo-500/20 text-indigo-400',
  commute: 'bg-slate-500/20 text-slate-400',
}

function Badge({ type }) {
  if (!type) return null
  const label = type.replace(/_/g, ' ')
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${RIDE_TYPE_COLORS[type] || RIDE_TYPE_COLORS.mixed}`}>
      {label}
    </span>
  )
}

export default function DashboardPage() {
  const [rides, setRides] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [toast, setToast] = useState(null)
  const perPage = 20

  // Garmin garth sync state
  const [garminActivities, setGarminActivities] = useState([])
  const [garminLoading, setGarminLoading] = useState(false)
  const [garminSyncing, setGarminSyncing] = useState(false)
  const [analyzing, setAnalyzing] = useState(null)

  const fetchRides = () => {
    setLoading(true)
    api(`/api/rides?page=${page}&per_page=${perPage}`)
      .then(data => { setRides(data.rides); setTotal(data.total) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  const fetchGarminActivities = () => {
    setGarminLoading(true)
    api('/api/garmin/activities')
      .then(data => setGarminActivities(data))
      .catch(() => {})
      .finally(() => setGarminLoading(false))
  }

  useEffect(() => { fetchRides() }, [page])
  useEffect(() => { fetchGarminActivities() }, [])

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 5000)
  }

  const handleSync = async (endpoint) => {
    setSyncing(true)
    try {
      const result = await api(endpoint, { method: 'POST' })
      const parts = []
      if (result.imported > 0) parts.push(`${result.imported} imported`)
      if (result.skipped > 0) parts.push(`${result.skipped} skipped`)
      if (result.failed > 0) parts.push(`${result.failed} failed`)
      showToast(parts.length ? parts.join(', ') : 'No new activities found')
      if (result.imported > 0) fetchRides()
    } catch (err) {
      showToast(err.message || 'Sync failed', 'error')
    } finally {
      setSyncing(false)
    }
  }

  const handleGarminSync = async (endpoint) => {
    setGarminSyncing(true)
    try {
      const result = await api(endpoint, { method: 'POST' })
      if (result.skipped) {
        showToast('Attivita gia scaricata')
      } else if (result.synced !== undefined) {
        showToast(`${result.synced} attivita scaricate, ${result.skipped} gia presenti`)
      } else if (result.metrics) {
        const name = result.metrics.name || 'Activity'
        const tss = result.metrics.tss ? ` — TSS: ${result.metrics.tss}` : ''
        showToast(`${name} scaricata${tss}`)
      }
      fetchGarminActivities()
    } catch (err) {
      showToast(err.message || 'Errore sync Garmin', 'error')
    } finally {
      setGarminSyncing(false)
    }
  }

  const handleAnalyze = async (activityId) => {
    setAnalyzing(activityId)
    try {
      const result = await api(`/api/garmin/activities/${activityId}/analyze`, { method: 'POST' })
      showToast('Analisi completata')
      fetchGarminActivities()
    } catch (err) {
      showToast(err.message || 'Errore analisi', 'error')
    } finally {
      setAnalyzing(null)
    }
  }

  const totalPages = Math.ceil(total / perPage)

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg text-sm font-medium shadow-lg ${
          toast.type === 'error' ? 'bg-red-500/90 text-white' : 'bg-green-500/90 text-white'
        }`}>
          {toast.message}
        </div>
      )}

      {/* Garmin Direct Sync (garth) */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Garmin Activities</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleGarminSync('/api/garmin/sync/last')}
              disabled={garminSyncing}
              className="px-3 py-1.5 rounded-lg text-sm bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-50 flex items-center gap-1.5"
            >
              {garminSyncing ? <Spinner /> : null}
              Scarica ultima uscita
            </button>
            <button
              onClick={() => handleGarminSync('/api/garmin/sync/weeks/3')}
              disabled={garminSyncing}
              className="px-3 py-1.5 rounded-lg text-sm bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-50 flex items-center gap-1.5"
            >
              {garminSyncing ? <Spinner /> : null}
              Scarica ultime 3 settimane
            </button>
          </div>
        </div>

        {garminLoading ? (
          <div className="text-slate-500 text-center py-8">Loading Garmin activities...</div>
        ) : garminActivities.length === 0 ? (
          <div className="text-center py-8 bg-slate-900 rounded-xl border border-slate-800">
            <p className="text-slate-500 mb-1">Nessuna attivita Garmin</p>
            <p className="text-sm text-slate-600">Premi &quot;Scarica ultima uscita&quot; per iniziare</p>
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-500 text-left">
                    <th className="px-4 py-3 font-medium">Date</th>
                    <th className="px-4 py-3 font-medium">Name</th>
                    <th className="px-4 py-3 font-medium">Distance</th>
                    <th className="px-4 py-3 font-medium">Duration</th>
                    <th className="px-4 py-3 font-medium">NP</th>
                    <th className="px-4 py-3 font-medium">TSS</th>
                    <th className="px-4 py-3 font-medium">IF</th>
                    <th className="px-4 py-3 font-medium">Avg HR</th>
                    <th className="px-4 py-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {garminActivities.map(a => (
                    <tr key={a.id} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                      <td className="px-4 py-3 text-slate-300">
                        {a.start_time ? new Date(a.start_time).toLocaleDateString() : '-'}
                      </td>
                      <td className="px-4 py-3 text-white font-medium">{a.name}</td>
                      <td className="px-4 py-3 text-slate-300">
                        {a.distance_m ? (a.distance_m / 1000).toFixed(1) : '-'} km
                      </td>
                      <td className="px-4 py-3 text-slate-300">
                        {a.duration_secs ? `${Math.floor(a.duration_secs / 3600)}h${String(Math.floor((a.duration_secs % 3600) / 60)).padStart(2, '0')}m` : '-'}
                      </td>
                      <td className="px-4 py-3 text-slate-300">{a.normalized_power ?? '-'}</td>
                      <td className="px-4 py-3 text-slate-300">{a.tss ? Math.round(a.tss) : '-'}</td>
                      <td className="px-4 py-3 text-slate-300">{a.intensity_factor?.toFixed(2) ?? '-'}</td>
                      <td className="px-4 py-3 text-slate-300">{a.avg_hr ?? '-'}</td>
                      <td className="px-4 py-3">
                        {a.analyzed ? (
                          <span className="text-xs text-green-400">Analyzed</span>
                        ) : (
                          <button
                            onClick={() => handleAnalyze(a.id)}
                            disabled={analyzing === a.id}
                            className="px-2 py-1 rounded text-xs bg-sky-600/20 text-sky-400 hover:bg-sky-600/40 disabled:opacity-50"
                          >
                            {analyzing === a.id ? 'Analyzing...' : 'Analyze'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden space-y-3">
              {garminActivities.map(a => (
                <div key={a.id} className="bg-slate-900 rounded-xl border border-slate-800 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-white font-medium">{a.name}</span>
                    <span className="text-xs text-slate-500">
                      {a.start_time ? new Date(a.start_time).toLocaleDateString() : ''}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-sm mb-3">
                    <div><span className="text-slate-500">Dist</span><br /><span className="text-slate-300">{a.distance_m ? (a.distance_m / 1000).toFixed(1) : '-'} km</span></div>
                    <div><span className="text-slate-500">NP</span><br /><span className="text-slate-300">{a.normalized_power ?? '-'}W</span></div>
                    <div><span className="text-slate-500">TSS</span><br /><span className="text-slate-300">{a.tss ? Math.round(a.tss) : '-'}</span></div>
                  </div>
                  {a.analyzed ? (
                    <span className="text-xs text-green-400">Analyzed</span>
                  ) : (
                    <button
                      onClick={() => handleAnalyze(a.id)}
                      disabled={analyzing === a.id}
                      className="px-3 py-1.5 rounded-lg text-xs bg-sky-600/20 text-sky-400 hover:bg-sky-600/40 disabled:opacity-50 w-full"
                    >
                      {analyzing === a.id ? 'Analyzing...' : 'Analyze'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Existing Rides (OAuth sync + uploads) */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Rides</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSync('/api/sync/latest')}
            disabled={syncing}
            className="px-3 py-1.5 rounded-lg text-sm bg-sky-600 text-white hover:bg-sky-500 disabled:opacity-50 flex items-center gap-1.5"
          >
            {syncing ? <Spinner /> : null}
            Sync Last Ride
          </button>
          <button
            onClick={() => handleSync('/api/sync/recent?weeks=3')}
            disabled={syncing}
            className="px-3 py-1.5 rounded-lg text-sm bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-50 flex items-center gap-1.5"
          >
            {syncing ? <Spinner /> : null}
            Sync Last 3 Weeks
          </button>
          <span className="text-sm text-slate-500">{total} total</span>
        </div>
      </div>

      {loading ? (
        <div className="text-slate-500 text-center py-12">Loading rides...</div>
      ) : rides.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-slate-500 mb-2">No rides yet</p>
          <p className="text-sm text-slate-600">Upload rides or connect Garmin to get started</p>
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-slate-500 text-left">
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Distance</th>
                  <th className="px-4 py-3 font-medium">Duration</th>
                  <th className="px-4 py-3 font-medium">NP</th>
                  <th className="px-4 py-3 font-medium">TSS</th>
                  <th className="px-4 py-3 font-medium">IF</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                </tr>
              </thead>
              <tbody>
                {rides.map(ride => (
                  <RideRow key={ride.id} ride={ride} />
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {rides.map(ride => (
              <RideCard key={ride.id} ride={ride} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-lg text-sm bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30"
              >
                Prev
              </button>
              <span className="text-sm text-slate-500">{page} / {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-lg text-sm bg-slate-800 text-slate-400 hover:bg-slate-700 disabled:opacity-30"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function RideRow({ ride }) {
  return (
    <tr className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
      <td className="px-4 py-3">
        <Link to={`/rides/${ride.id}`} className="text-sky-400 hover:underline">
          {new Date(ride.ride_date).toLocaleDateString()}
        </Link>
      </td>
      <td className="px-4 py-3 text-slate-300">{ride.distance_km?.toFixed(1)} km</td>
      <td className="px-4 py-3 text-slate-300">{Math.round(ride.duration_sec / 60)} min</td>
      <td className="px-4 py-3 text-slate-300">{ride.np ?? '-'}</td>
      <td className="px-4 py-3 text-slate-300">{ride.tss ?? '-'}</td>
      <td className="px-4 py-3 text-slate-300">{ride.if_val ?? '-'}</td>
      <td className="px-4 py-3"><Badge type={ride.ride_type} /></td>
    </tr>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function RideCard({ ride }) {
  return (
    <Link to={`/rides/${ride.id}`} className="block bg-slate-900 rounded-xl border border-slate-800 p-4 hover:border-slate-700 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <span className="text-white font-medium">{new Date(ride.ride_date).toLocaleDateString()}</span>
        <Badge type={ride.ride_type} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <div><span className="text-slate-500">Dist</span><br /><span className="text-slate-300">{ride.distance_km?.toFixed(1)} km</span></div>
        <div><span className="text-slate-500">Time</span><br /><span className="text-slate-300">{Math.round(ride.duration_sec / 60)} min</span></div>
        <div><span className="text-slate-500">TSS</span><br /><span className="text-slate-300">{ride.tss ?? '-'}</span></div>
      </div>
    </Link>
  )
}
