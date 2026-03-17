import { createContext, useContext, useState, useEffect } from 'react'
import { api, setToken, clearToken, getToken } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const saved = sessionStorage.getItem('pm_token')
    if (saved) {
      setToken(saved)
      api('/api/auth/me')
        .then(setUser)
        .catch(() => { clearToken(); sessionStorage.removeItem('pm_token') })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  async function login(email, password) {
    const data = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
    setToken(data.access_token)
    sessionStorage.setItem('pm_token', data.access_token)
    const me = await api('/api/auth/me')
    setUser(me)
  }

  async function register(email, password, name) {
    const data = await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    })
    setToken(data.access_token)
    sessionStorage.setItem('pm_token', data.access_token)
    const me = await api('/api/auth/me')
    setUser(me)
  }

  function logout() {
    clearToken()
    sessionStorage.removeItem('pm_token')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
