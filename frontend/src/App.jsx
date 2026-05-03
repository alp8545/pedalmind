import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Nav from './components/Nav'
import UpdateBanner from './components/UpdateBanner'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import RideDetailPage from './pages/RideDetailPage'
import ActivityDetailPage from './pages/ActivityDetailPage'
import ChatPage from './pages/ChatPage'
import SeasonPage from './pages/SeasonPage'
import SettingsPage from './pages/SettingsPage'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="flex items-center justify-center h-screen text-slate-400">Loading...</div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const { user } = useAuth()

  // Wake the Render free-tier backend in the background so that by the time
  // the user fills the login form, the cold start is already over.
  useEffect(() => {
    const base = import.meta.env.VITE_API_URL || ''
    if (!base) return
    fetch(`${base}/api/health`, { method: 'GET', cache: 'no-store' }).catch(() => {})
  }, [])

  return (
    <div
      className="min-h-screen relative"
      style={{
        background: 'linear-gradient(180deg, #060a14 0%, #0a0e1a 30%, #0c1220 100%)',
        fontFamily: "'DM Sans', system-ui, -apple-system, sans-serif",
      }}
    >
      {/* Ambient glow */}
      {user && (
        <>
          <div className="fixed pointer-events-none" style={{ top: -80, right: -80, width: 250, height: 250, background: 'radial-gradient(circle, rgba(245,158,11,0.06) 0%, transparent 70%)' }} />
          <div className="fixed pointer-events-none" style={{ bottom: 40, left: -60, width: 200, height: 200, background: 'radial-gradient(circle, rgba(34,211,238,0.04) 0%, transparent 70%)' }} />
        </>
      )}

      {user && <Nav />}
      <UpdateBanner />
      <main className={user ? 'pb-28' : ''} style={user ? { paddingTop: 'calc(env(safe-area-inset-top, 12px) + 36px)' } : undefined}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/rides/:rideId" element={<ProtectedRoute><RideDetailPage /></ProtectedRoute>} />
          <Route path="/activities/:activityId" element={<ProtectedRoute><ActivityDetailPage /></ProtectedRoute>} />
          <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
          <Route path="/season" element={<ProtectedRoute><SeasonPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
