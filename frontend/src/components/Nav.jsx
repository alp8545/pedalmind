import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/chat', label: 'Chat' },
  { to: '/settings', label: 'Settings' },
]

export default function Nav() {
  const { user, logout } = useAuth()

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-slate-900/95 backdrop-blur border-b border-slate-800">
      <div className="max-w-6xl mx-auto px-4 flex items-center justify-between h-14">
        <div className="flex items-center gap-6">
          <span className="text-lg font-bold text-white tracking-tight">PedalMind</span>
          <div className="hidden sm:flex gap-1">
            {links.map(l => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.to === '/'}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm transition-colors ${isActive ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-500 hidden sm:inline">{user?.name}</span>
          <button onClick={logout} className="text-sm text-slate-400 hover:text-white transition-colors">
            Logout
          </button>
        </div>
      </div>
      {/* Mobile nav */}
      <div className="sm:hidden flex border-t border-slate-800">
        {links.map(l => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.to === '/'}
            className={({ isActive }) =>
              `flex-1 text-center py-2 text-xs transition-colors ${isActive ? 'text-sky-400 border-b-2 border-sky-400' : 'text-slate-500'}`
            }
          >
            {l.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
