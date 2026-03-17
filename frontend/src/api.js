const API_BASE = import.meta.env.VITE_API_URL || ''

let _token = null

export function setToken(token) {
  _token = token
}

export function getToken() {
  return _token
}

export function clearToken() {
  _token = null
}

export async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (_token) {
    headers['Authorization'] = `Bearer ${_token}`
  }
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const res = await fetch(url, { ...options, headers })
  if (res.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}
