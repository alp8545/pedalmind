import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../context/AuthContext'
import { G, Label, MetricCard } from '../components/ui'
import PMChart from '../components/charts/PMChart'

// Placeholder PMC data (until real historical TSS)
const MOCK_CTL = [42,44,45,47,48,46,49,51,53,55,54,56,58,57,59,61,60,62,63,65,64,66,68,67,69,71,70,72,74,73]
const MOCK_ATL = [50,55,60,52,48,65,70,58,55,72,68,60,75,70,65,80,72,68,78,75,70,82,78,72,85,80,75,88,82,78]
const MOCK_TSB = MOCK_CTL.map((c, i) => c - MOCK_ATL[i])

export default function DashboardPage() {
  const { user } = useAuth()
  const [rides, setRides] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState(null)
  const perPage = 20

  const [garminActivities, setGarminActivities] = useState([])
  const [garminLoading, setGarminLoading] = useState(false)
  const [garminSyncing, setGarminSyncing] = useState(null)
  const [analyzing, setAnalyzing] = useState(null)

  const [workoutModalOpen, setWorkoutModalOpen] = useState(false)
  const [workoutText, setWorkoutText] = useState('')
  const [workoutDate, setWorkoutDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().split('T')[0]
  })
  const [workoutUploading, setWorkoutUploading] = useState(false)

  const fetchRides = () => {
    setLoading(true)
    api(`/api/rides?page=${page}&per_page=${perPage}`)
      .then(data => { setRides(data.rides); setTotal(data.total) })
      .catch(() => {}).finally(() => setLoading(false))
  }
  const fetchGarminActivities = () => {
    setGarminLoading(true)
    api('/api/garmin/activities').then(data => setGarminActivities(data))
      .catch(() => {}).finally(() => setGarminLoading(false))
  }
  useEffect(() => { fetchRides() }, [page])
  useEffect(() => { fetchGarminActivities() }, [])

  const showToast = (msg, type = 'success') => { setToast({ message: msg, type }); setTimeout(() => setToast(null), 5000) }

  const handleGarminSync = async (endpoint, key) => {
    setGarminSyncing(key)
    try {
      const r = await api(endpoint, { method: 'POST' })
      if (r.skipped === true) showToast('Attivita gia scaricata')
      else if (r.synced !== undefined) showToast(`${r.synced} scaricate, ${r.skipped} gia presenti`)
      else if (r.metrics) showToast(`${r.metrics.name || 'Activity'} scaricata${r.metrics.tss ? ` — TSS: ${r.metrics.tss}` : ''}`)
      else showToast('Sync completato')
      fetchGarminActivities()
    } catch (err) { showToast(err.message || 'Errore sync Garmin', 'error') }
    finally { setGarminSyncing(null) }
  }
  const handleWorkoutUpload = async () => {
    if (!workoutText.trim()) return
    setWorkoutUploading(true)
    try {
      await api('/api/garmin/workout/upload', { method: 'POST', body: JSON.stringify({ text: workoutText.trim(), date: workoutDate }) })
      showToast('Workout caricato su Garmin'); setWorkoutModalOpen(false); setWorkoutText('')
    } catch (err) { showToast(err.message || 'Errore caricamento workout', 'error') }
    finally { setWorkoutUploading(false) }
  }
  const handleAnalyze = async (activityId) => {
    setAnalyzing(activityId)
    try { await api(`/api/garmin/activities/${activityId}/analyze`, { method: 'POST' }); showToast('Analisi completata'); fetchGarminActivities() }
    catch (err) { showToast(err.message || 'Errore analisi', 'error') }
    finally { setAnalyzing(null) }
  }

  const totalPages = Math.ceil(total / perPage)
  const now = new Date()
  const dateStr = now.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' }).toUpperCase()
  const hour = now.getHours()
  const greeting = hour < 12 ? 'Buongiorno' : hour < 18 ? 'Buon pomeriggio' : 'Buonasera'

  return (
    <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col gap-4">
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-[14px] text-sm font-medium shadow-lg font-mono ${toast.type === 'error' ? 'bg-red-500/90 text-white' : 'bg-green-500/90 text-white'}`}>
          {toast.message}
        </div>
      )}

      {/* Header */}
      <div>
        <div className="font-mono text-slate-500 uppercase" style={{ fontSize: 11, letterSpacing: 1 }}>{dateStr}</div>
        <h1 className="text-2xl font-light text-slate-50 mt-0.5" style={{ letterSpacing: -0.5 }}>
          {greeting}, {user?.name?.split(' ')[0] || 'Atleta'}
        </h1>
      </div>

      {/* Three Garmin buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => handleGarminSync('/api/garmin/sync/last', 'last')} disabled={garminSyncing !== null}
          className="px-3 py-1.5 rounded-lg text-sm bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 disabled:opacity-50 flex items-center gap-1.5 transition-colors">
          {garminSyncing === 'last' ? <Spinner /> : <DownloadIcon />} Scarica ultima attivita
        </button>
        <button onClick={() => handleGarminSync('/api/garmin/sync/weeks/3', 'weeks')} disabled={garminSyncing !== null}
          className="px-3 py-1.5 rounded-lg text-sm bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 disabled:opacity-50 flex items-center gap-1.5 transition-colors">
          {garminSyncing === 'weeks' ? <Spinner /> : <DownloadIcon />} Scarica ultime 3 settimane
        </button>
        <button onClick={() => setWorkoutModalOpen(true)}
          className="px-3 py-1.5 rounded-lg text-sm bg-amber-600/20 text-amber-300 border border-amber-600/30 hover:bg-amber-600/30 flex items-center gap-1.5 transition-colors">
          <UploadIcon /> Carica workout
        </button>
      </div>

      {/* FTP / CTL / TSB */}
      <div className="grid grid-cols-3 gap-2">
        <MetricCard label="FTP" value="265" color="#f59e0b" sub="target" />
        <MetricCard label="CTL" value={MOCK_CTL[MOCK_CTL.length - 1]} color="#f8fafc" sub={`+${MOCK_CTL[MOCK_CTL.length - 1] - MOCK_CTL[0]} \u2191`} />
        <MetricCard label="TSB" value={MOCK_TSB[MOCK_TSB.length - 1]} color="#22d3ee" sub="ottimale" />
      </div>

      {/* PMC */}
      <G>
        <div className="flex justify-between items-center mb-2.5">
          <Label>Performance Manager</Label>
          <span className="font-mono text-slate-600" style={{ fontSize: 9 }}>30gg</span>
        </div>
        <PMChart ctl={MOCK_CTL} atl={MOCK_ATL} tsb={MOCK_TSB} />
        <div className="flex gap-4 mt-2">
          {[{ c: '#f59e0b', l: 'Fitness' }, { c: '#ef4444', l: 'Fatica' }, { c: '#22d3ee', l: 'Forma' }].map(x => (
            <div key={x.l} className="flex items-center gap-1">
              <div className="rounded-sm" style={{ width: 8, height: 3, background: x.c }} />
              <span className="font-mono text-slate-500" style={{ fontSize: 8 }}>{x.l}</span>
            </div>
          ))}
        </div>
      </G>

      {/* Garmin Activities */}
      <div>
        <Label>Attivita Garmin</Label>
        {garminLoading ? (
          <div className="text-slate-500 text-center py-8 font-mono text-xs">Caricamento...</div>
        ) : garminActivities.length === 0 ? (
          <G className="text-center py-6">
            <p className="text-slate-500 text-sm mb-1">Nessuna attivita</p>
            <p className="text-slate-600 font-mono" style={{ fontSize: 10 }}>Premi &quot;Scarica ultima attivita&quot;</p>
          </G>
        ) : (
          <div className="flex flex-col gap-2">
            {garminActivities.map(a => (
              <Link key={a.id} to={`/activities/${a.id}`} className="block">
                <G className="!p-3 hover:border-amber-500/20 transition-colors">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-slate-50 font-medium text-sm">{a.name}</span>
                    <span className="font-mono text-slate-500" style={{ fontSize: 9 }}>
                      {a.start_time ? new Date(a.start_time).toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }) : ''}
                    </span>
                  </div>
                  <div className="flex gap-4 font-mono" style={{ fontSize: 11 }}>
                    {a.distance_m && <span className="text-slate-400">{(a.distance_m / 1000).toFixed(1)}km</span>}
                    {a.duration_secs && <span className="text-slate-400">{Math.floor(a.duration_secs / 3600)}h{String(Math.floor((a.duration_secs % 3600) / 60)).padStart(2, '0')}m</span>}
                    {a.normalized_power && <span className="text-amber-400">NP {a.normalized_power}W</span>}
                    {a.tss && <span className="text-slate-400">TSS {Math.round(a.tss)}</span>}
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <div className="flex gap-2 font-mono" style={{ fontSize: 10 }}>
                      {a.avg_hr && <span className="text-slate-500">{a.avg_hr}bpm</span>}
                      {a.intensity_factor && <span className="text-slate-500">IF {a.intensity_factor.toFixed(2)}</span>}
                    </div>
                    {a.analyzed ? (
                      <span className="font-mono text-green-400" style={{ fontSize: 9 }}>Analizzata</span>
                    ) : (
                      <button onClick={(e) => { e.preventDefault(); handleAnalyze(a.id) }} disabled={analyzing === a.id}
                        className="font-mono text-amber-400 hover:text-amber-300 disabled:opacity-50" style={{ fontSize: 9 }}>
                        {analyzing === a.id ? 'Analisi...' : 'Analizza'}
                      </button>
                    )}
                  </div>
                </G>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Rides */}
      {rides.length > 0 && (
        <div>
          <div className="flex justify-between items-center mb-2">
            <Label>Rides Importate</Label>
            <span className="font-mono text-slate-600" style={{ fontSize: 9 }}>{total} totali</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {rides.map(ride => (
              <Link key={ride.id} to={`/rides/${ride.id}`}>
                <G className="!p-3 hover:border-amber-500/20 transition-colors">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-50 text-sm">{new Date(ride.ride_date).toLocaleDateString('it-IT', { day: 'numeric', month: 'short' })}</span>
                    <div className="flex gap-3 font-mono text-slate-400" style={{ fontSize: 10 }}>
                      <span>{ride.distance_km?.toFixed(1)}km</span>
                      <span>{Math.round(ride.duration_sec / 60)}min</span>
                      <span>{ride.tss ?? '\u2014'} TSS</span>
                    </div>
                  </div>
                </G>
              </Link>
            ))}
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 mt-4">
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                className="font-mono text-slate-500 hover:text-white disabled:opacity-30 text-xs">Prev</button>
              <span className="font-mono text-slate-600" style={{ fontSize: 10 }}>{page}/{totalPages}</span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                className="font-mono text-slate-500 hover:text-white disabled:opacity-30 text-xs">Next</button>
            </div>
          )}
        </div>
      )}

      {/* Workout Modal */}
      {workoutModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <G className="w-full max-w-lg !p-6" style={{ border: '1px solid rgba(148,163,184,0.15)' }}>
            <h3 className="text-lg font-semibold text-white mb-4">Carica workout su Garmin</h3>
            <textarea value={workoutText} onChange={e => setWorkoutText(e.target.value)}
              placeholder="Es: 15min WU Z2, 4x8min sweet spot 90rpm, 10min CD" rows={5}
              className="w-full bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-amber-500/50 resize-y font-mono" />
            <div className="mt-3">
              <label className="block font-mono text-slate-500 mb-1 uppercase" style={{ fontSize: 9, letterSpacing: 1.5 }}>Data</label>
              <input type="date" value={workoutDate} onChange={e => setWorkoutDate(e.target.value)}
                className="bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-1.5 text-sm text-white focus:outline-none focus:border-amber-500/50 font-mono" />
            </div>
            <div className="flex items-center justify-end gap-2 mt-5">
              <button onClick={() => { setWorkoutModalOpen(false); setWorkoutText('') }}
                className="px-4 py-2 rounded-[10px] text-sm text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">Annulla</button>
              <button onClick={handleWorkoutUpload} disabled={!workoutText.trim() || workoutUploading}
                className="px-4 py-2 rounded-[10px] text-sm font-medium disabled:opacity-50 flex items-center gap-1.5 transition-colors"
                style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)', color: '#0a0e1a' }}>
                {workoutUploading ? <Spinner /> : <UploadIcon />} Carica su Garmin
              </button>
            </div>
          </G>
        </div>
      )}
    </div>
  )
}

function Spinner() {
  return <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
}
function DownloadIcon() {
  return <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path d="M10 3a1 1 0 011 1v7.586l2.293-2.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 111.414-1.414L9 11.586V4a1 1 0 011-1z" /><path d="M3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" /></svg>
}
function UploadIcon() {
  return <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor"><path d="M10 17a1 1 0 01-1-1V8.414L6.707 10.707a1 1 0 01-1.414-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 8.414V16a1 1 0 01-1 1z" /><path d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" /></svg>
}
