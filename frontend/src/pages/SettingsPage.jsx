import { useEffect, useState } from 'react'
import { api } from '../api'

const POWER_METER_TYPES = [
  { value: '', label: 'Not set' },
  { value: 'dual', label: 'Dual-sided' },
  { value: 'left_only', label: 'Left only' },
  { value: 'right_only', label: 'Right only' },
  { value: 'spider', label: 'Spider' },
  { value: 'hub', label: 'Hub' },
  { value: 'pedals', label: 'Pedals' },
]

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'it', label: 'Italiano' },
  { value: 'de', label: 'Deutsch' },
  { value: 'es', label: 'Espanol' },
  { value: 'fr', label: 'Francais' },
]

export default function SettingsPage() {
  const [form, setForm] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api('/api/profile')
      .then(data => {
        setForm({
          ftp_watts: data.ftp_watts,
          max_hr: data.max_hr,
          resting_hr: data.resting_hr ?? '',
          weight_kg: data.weight_kg,
          target_ftp_watts: data.target_ftp_watts ?? '',
          target_weight_kg: data.target_weight_kg ?? '',
          weekly_hours_budget: data.weekly_hours_budget ?? '',
          power_meter_type: data.power_meter_type ?? '',
          goals_text: data.goals_text ?? '',
          preferred_language: data.preferred_language ?? 'en',
        })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function update(field, value) {
    setForm(prev => ({ ...prev, [field]: value }))
    setSaved(false)
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const body = { ...form }
      // Convert empty strings to null for optional fields
      for (const key of ['resting_hr', 'target_ftp_watts', 'target_weight_kg', 'weekly_hours_budget']) {
        if (body[key] === '') body[key] = null
        else body[key] = Number(body[key])
      }
      if (body.power_meter_type === '') body.power_meter_type = null
      body.ftp_watts = Number(body.ftp_watts)
      body.max_hr = Number(body.max_hr)
      body.weight_kg = Number(body.weight_kg)

      await api('/api/profile', { method: 'PUT', body: JSON.stringify(body) })
      setSaved(true)
    } catch { }
    setSaving(false)
  }

  if (loading || !form) return <div className="text-center py-12 text-slate-500">Loading...</div>

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold text-white mb-6">Athlete Profile</h1>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Performance */}
        <Section title="Performance">
          <div className="grid grid-cols-2 gap-4">
            <Field label="FTP (watts)" type="number" value={form.ftp_watts} onChange={v => update('ftp_watts', v)} min={50} max={500} required />
            <Field label="Max HR (bpm)" type="number" value={form.max_hr} onChange={v => update('max_hr', v)} min={120} max={230} required />
            <Field label="Resting HR (bpm)" type="number" value={form.resting_hr} onChange={v => update('resting_hr', v)} />
            <Field label="Weight (kg)" type="number" value={form.weight_kg} onChange={v => update('weight_kg', v)} min={35} max={150} step="0.1" required />
          </div>
        </Section>

        {/* Goals */}
        <Section title="Goals">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Target FTP (watts)" type="number" value={form.target_ftp_watts} onChange={v => update('target_ftp_watts', v)} />
            <Field label="Target Weight (kg)" type="number" value={form.target_weight_kg} onChange={v => update('target_weight_kg', v)} step="0.1" />
            <Field label="Weekly Hours Budget" type="number" value={form.weekly_hours_budget} onChange={v => update('weekly_hours_budget', v)} step="0.5" />
          </div>
          <div className="mt-4">
            <label className="block text-sm text-slate-400 mb-1">Goals</label>
            <textarea
              value={form.goals_text}
              onChange={e => update('goals_text', e.target.value)}
              rows={3}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-sky-500 resize-none"
              placeholder="e.g. Increase FTP from 265W to 300W, reduce weight to 64kg"
            />
          </div>
        </Section>

        {/* Equipment & Preferences */}
        <Section title="Equipment & Preferences">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Power Meter</label>
              <select
                value={form.power_meter_type}
                onChange={e => update('power_meter_type', e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-sky-500"
              >
                {POWER_METER_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Language</label>
              <select
                value={form.preferred_language}
                onChange={e => update('preferred_language', e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-sky-500"
              >
                {LANGUAGES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>
        </Section>

        {/* Save */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-medium px-6 py-2 rounded-lg transition-colors text-sm"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
          {saved && <span className="text-sm text-green-400">Saved!</span>}
        </div>
      </form>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800 p-4">
      <h2 className="text-base font-semibold text-white mb-4">{title}</h2>
      {children}
    </div>
  )
}

function Field({ label, type = 'text', value, onChange, ...props }) {
  return (
    <div>
      <label className="block text-sm text-slate-400 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-sky-500"
        {...props}
      />
    </div>
  )
}
