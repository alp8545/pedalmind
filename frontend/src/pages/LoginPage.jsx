import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { G } from '../components/ui'

export default function LoginPage() {
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login, register, user } = useAuth()
  const navigate = useNavigate()

  if (user) {
    navigate('/', { replace: true })
    return null
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (isRegister) {
        await register(email, password, name)
      } else {
        await login(email, password)
      }
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-3xl font-bold text-amber-500 text-center mb-2" style={{ letterSpacing: -0.5 }}>PedalMind</h1>
        <p className="text-slate-400 text-center text-sm font-mono mb-8">AI-powered cycling analytics</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <G className="!p-6 space-y-4">
          <h2 className="text-lg font-semibold text-white">{isRegister ? 'Crea Account' : 'Accedi'}</h2>

          {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 text-sm text-red-400">{error}</div>}

          {isRegister && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">Nome</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                required
                className="w-full bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500/50 font-mono"
              />
            </div>
          )}

          <div>
            <label className="block text-sm text-slate-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              className="w-full bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500/50 font-mono"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              minLength={6}
              className="w-full bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500/50 font-mono"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full disabled:opacity-50 font-medium py-2 rounded-[10px] transition-colors text-sm"
            style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)', color: '#0a0e1a' }}
          >
            {loading ? '...' : isRegister ? 'Registrati' : 'Accedi'}
          </button>

          <p className="text-center text-sm text-slate-500">
            {isRegister ? 'Hai gia un account?' : 'Non hai un account?'}{' '}
            <button type="button" onClick={() => { setIsRegister(!isRegister); setError('') }} className="text-amber-400 hover:underline font-mono">
              {isRegister ? 'Accedi' : 'Registrati'}
            </button>
          </p>
          </G>
        </form>
      </div>
    </div>
  )
}
