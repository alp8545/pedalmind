import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const tabs = [
  { to: '/', icon: '\u25C9', label: 'Home' },
  { to: '/chat', icon: '\u25C8', label: 'Coach' },
  { to: '/season', icon: '\u25CE', label: 'Piano' },
  { to: '/settings', icon: '\u25B3', label: 'Settings' },
]

export default function Nav() {
  const { user, logout } = useAuth()

  return (
    <>
      {/* Top bar — below status bar safe area */}
      <div className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-4 font-mono text-slate-400"
        style={{ fontSize: 12, paddingTop: 'env(safe-area-inset-top, 12px)', paddingBottom: 6 }}>
        <span>{user?.name || ''}</span>
        <span className="text-amber-500 font-bold text-base tracking-tight" style={{ letterSpacing: -0.5 }}>PedalMind</span>
        <button onClick={logout} className="text-slate-400 hover:text-white transition-colors font-mono" style={{ fontSize: 12 }}>
          Logout
        </button>
      </div>

      {/* Bottom nav bar */}
      <nav
        className="fixed bottom-0 left-0 right-0 z-50 flex justify-around"
        style={{
          background: 'linear-gradient(180deg, transparent 0%, rgba(6,10,20,0.97) 30%)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          paddingTop: 6,
          paddingBottom: 'env(safe-area-inset-bottom, 16px)',
        }}
      >
        {tabs.map(t => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.to === '/'}
            className="flex flex-col items-center gap-1 transition-all"
            style={({ isActive }) => ({ opacity: isActive ? 1 : 0.4, padding: '6px 0' })}
          >
            {({ isActive }) => (
              <>
                <span style={{ fontSize: 20 }}>{t.icon}</span>
                <span
                  className="font-mono uppercase"
                  style={{
                    fontSize: 9,
                    letterSpacing: 1.5,
                    color: isActive ? '#f59e0b' : '#94a3b8',
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  {t.label}
                </span>
                {isActive && <div className="w-1 h-1 rounded-full bg-amber-500 -mt-0.5" />}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </>
  )
}
