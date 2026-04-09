import { useEffect, useState } from 'react'
import { api } from '../api'
import { G } from '../components/ui'

const POWER_METER_TYPES = [
  { value: '', label: 'Non impostato' },
  { value: 'dual', label: 'Dual-sided' },
  { value: 'left_only', label: 'Solo sinistro' },
  { value: 'right_only', label: 'Solo destro' },
  { value: 'spider', label: 'Spider' },
  { value: 'hub', label: 'Hub' },
  { value: 'pedals', label: 'Pedali' },
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

  if (loading || !form) return <div className="text-center py-12 text-slate-500">Caricamento...</div>

  return (
    <div className="max-w-2xl mx-auto px-4 py-4 flex flex-col gap-4">
      <div>
        <div className="font-mono text-slate-400 uppercase" style={{ fontSize: 13, letterSpacing: 1 }}>IMPOSTAZIONI</div>
        <h1 className="text-2xl font-light text-slate-50 mt-0.5" style={{ letterSpacing: -0.5 }}>Profilo Atleta</h1>
      </div>

      <form onSubmit={handleSave} className="flex flex-col gap-4">
        {/* Performance */}
        <Section title="Prestazioni">
          <div className="grid grid-cols-2 gap-4">
            <Field label="FTP (watt)" type="number" value={form.ftp_watts} onChange={v => update('ftp_watts', v)} min={50} max={500} required />
            <Field label="FC Max (bpm)" type="number" value={form.max_hr} onChange={v => update('max_hr', v)} min={120} max={230} required />
            <Field label="FC Riposo (bpm)" type="number" value={form.resting_hr} onChange={v => update('resting_hr', v)} />
            <Field label="Peso (kg)" type="number" value={form.weight_kg} onChange={v => update('weight_kg', v)} min={35} max={150} step="0.1" required />
          </div>
        </Section>

        {/* Goals */}
        <Section title="Obiettivi">
          <div className="grid grid-cols-2 gap-4">
            <Field label="FTP Obiettivo (watt)" type="number" value={form.target_ftp_watts} onChange={v => update('target_ftp_watts', v)} />
            <Field label="Peso Obiettivo (kg)" type="number" value={form.target_weight_kg} onChange={v => update('target_weight_kg', v)} step="0.1" />
            <Field label="Ore Settimanali" type="number" value={form.weekly_hours_budget} onChange={v => update('weekly_hours_budget', v)} step="0.5" />
          </div>
          <div className="mt-4">
            <label className="block text-sm text-slate-400 mb-1">Note</label>
            <textarea
              value={form.goals_text}
              onChange={e => update('goals_text', e.target.value)}
              rows={3}
              className="w-full bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500/50 font-mono resize-none"
              placeholder="es. Aumentare FTP da 265W a 300W, peso a 64kg"
            />
          </div>
        </Section>

        {/* Equipment & Preferences */}
        <Section title="Equipaggiamento e Preferenze">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Misuratore di Potenza</label>
              <select
                value={form.power_meter_type}
                onChange={e => update('power_meter_type', e.target.value)}
                className="w-full bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500/50 font-mono"
              >
                {POWER_METER_TYPES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Lingua</label>
              <select
                value={form.preferred_language}
                onChange={e => update('preferred_language', e.target.value)}
                className="w-full bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500/50 font-mono"
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
            className="disabled:opacity-50 font-medium px-6 py-2 rounded-[10px] transition-colors text-sm"
            style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)', color: '#0a0e1a' }}
          >
            {saving ? 'Salvataggio...' : 'Salva'}
          </button>
          {saved && <span className="text-sm text-green-400">Salvato!</span>}
        </div>
      </form>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <G>
      <h2 className="text-base font-semibold text-white mb-4">{title}</h2>
      {children}
    </G>
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
        className="w-full bg-[#0f172a] border border-slate-700/50 rounded-[10px] px-3 py-2 text-white text-sm focus:outline-none focus:border-amber-500/50 font-mono"
        {...props}
      />
    </div>
  )
}
