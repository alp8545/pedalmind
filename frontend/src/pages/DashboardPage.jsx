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
  const [toast, setToast] = useState(null)
  const perPage = 20

  // Garmin garth activities state
  const [garminActivities, setGarminActivities] = useState([])
  const [garminLoading, setGarminLoading] = useState(false)
  const [garminSyncing, setGarminSyncing] = useState(null) // 'last' | 'weeks' | null
  const [analyzing, setAnalyzing] = useState(null)

  // Workout upload modal state
  const [workoutModalOpen, setWorkoutModalOpen] = useState(false)
  const [workoutText, setWorkoutText] = useState('')
  const [workoutDate, setWorkoutDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 1)
    return d.toISOString().split('T')[0]
  })
  const [workoutUploading, setWorkoutUploading] = useState(false)

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

  const handleGarminSync = async (endpoint, key) => {
    setGarminSyncing(key)
    try {
      const result = await api(endpoint, { method: 'POST' })
      if (result.skipped === true) {
        showToast('Attivita gia scaricata')
      } else if (result.synced !== undefined) {
        showToast(`${result.synced} scaricate, ${result.skipped} gia presenti`)
      } else if (result.metrics) {
        const name = result.metrics.name || 'Activity'
        const tss = result.metrics.tss ? ` — TSS: ${result.metrics.tss}` : ''
        showToast(`${name} scaricata${tss}`)
      } else {
        showToast('Sync completato')
      }
      fetchGarminActivities()
    } catch (err) {
      showToast(err.message || 'Errore sync Garmin', 'error')
    } finally {
      setGarminSyncing(null)
    }
  }

  const handleWorkoutUpload = async () => {
    if (!workoutText.trim()) return
    setWorkoutUploading(true)
    try {
      await api('/api/garmin/workout/upload', {
        method: 'POST',
        body: JSON.stringify({ text: workoutText.trim(), date: workoutDate }),
      })
      showToast('Workout caricato su Garmin')
      setWorkoutModalOpen(false)
      setWorkoutText('')
    } catch (err) {
      showToast(err.message || 'Errore caricamento workout', 'error')
    } finally {
      setWorkoutUploading(false)
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

      {/* Garmin Activities */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h2 className="text-xl font-bold text-white">Garmin Activities</h2>
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => handleGarminSync('/api/garmin/sync/last', 'last')}
              disabled={garminSyncing !== null}
              className="px-3 py-1.5 rounded-lg text-sm bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 disabled:opacity-50 flex items-center gap-1.5 transition-colors"
            >
              {garminSyncing === 'last' ? <Spinner /> : <DownloadIcon />}
              Scarica ultima attivita
            </button>
            <button
              onClick={() => handleGarminSync('/api/garmin/sync/weeks/3', 'weeks')}
              disabled={garminSyncing !== null}
              className="px-3 py-1.5 rounded-lg text-sm bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 disabled:opacity-50 flex items-center gap-1.5 transition-colors"
            >
              {garminSyncing === 'weeks' ? <Spinner /> : <DownloadIcon />}
              Scarica ultime 3 settimane
            </button>
            <button
              onClick={() => setWorkoutModalOpen(true)}
              className="px-3 py-1.5 rounded-lg text-sm bg-amber-600/20 text-amber-300 border border-amber-600/30 hover:bg-amber-600/30 flex items-center gap-1.5 transition-colors"
            >
              <UploadIcon />
              Carica workout
            </button>
          </div>
        </div>

        {garminLoading ? (
          <div className="text-slate-500 text-center py-8">Loading Garmin activities...</div>
        ) : garminActivities.length === 0 ? (
          <div className="text-center py-8 bg-slate-900 rounded-xl border border-slate-800">
            <p className="text-slate-500 mb-1">Nessuna attivita Garmin</p>
            <p className="text-sm text-slate-600">Le attivita verranno sincronizzate automaticamente</p>
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

      {/* Existing Rides */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Rides</h1>
        <span className="text-sm text-slate-500">{total} total</span>
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

      {/* Workout Upload Modal */}
      {workoutModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl w-full max-w-lg p-6">
            <h3 className="text-lg font-bold text-white mb-4">Carica workout su Garmin</h3>
            <textarea
              value={workoutText}
              onChange={e => setWorkoutText(e.target.value)}
              placeholder="Es: 15min WU Z2, 4x8min sweet spot 90rpm, 10min CD"
              rows={5}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-500/50 resize-y"
            />
            <div className="mt-3">
              <label className="block text-xs text-slate-500 mb-1">Data (opzionale)</label>
              <input
                type="date"
                value={workoutDate}
                onChange={e => setWorkoutDate(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-amber-500/50"
              />
            </div>
            <div className="flex items-center justify-end gap-2 mt-5">
              <button
                onClick={() => { setWorkoutModalOpen(false); setWorkoutText('') }}
                className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                Annulla
              </button>
              <button
                onClick={handleWorkoutUpload}
                disabled={!workoutText.trim() || workoutUploading}
                className="px-4 py-2 rounded-lg text-sm bg-amber-500 text-slate-900 font-medium hover:bg-amber-400 disabled:opacity-50 flex items-center gap-1.5 transition-colors"
              >
                {workoutUploading ? <Spinner /> : <UploadIcon />}
                Carica su Garmin
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
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

function DownloadIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
      <path d="M10 3a1 1 0 011 1v7.586l2.293-2.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 11.586V4a1 1 0 011-1z" />
      <path d="M3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" />
    </svg>
  )
}

function UploadIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
      <path d="M10 17a1 1 0 01-1-1V8.414L6.707 10.707a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 8.414V16a1 1 0 01-1 1z" />
      <path d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" />
    </svg>
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
