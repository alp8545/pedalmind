import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

const FORM_COLORS = {
  Peaked: '#22c55e',
  Fresh: '#22c55e',
  Building: '#f59e0b',
  Fatigued: '#ef4444',
  Overreaching: '#dc2626',
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg p-3 font-mono" style={{ background: '#1e293b', border: '1px solid #475569', color: '#e2e8f0', fontSize: 13 }}>
      <div className="font-semibold text-white mb-1.5">{d.date}</div>
      <div>CTL: <span className="text-amber-400">{d.ctl}</span></div>
      <div>ATL: <span className="text-red-400">{d.atl}</span></div>
      <div>TSB: <span style={{ color: FORM_COLORS[d.form] || '#22d3ee' }}>{d.tsb}</span>
        <span className="text-slate-400 ml-1.5" style={{ fontSize: 11 }}>{d.form}</span>
      </div>
      {d.daily_tss > 0 && <div className="mt-1 text-slate-400">TSS: {d.daily_tss}</div>}
    </div>
  )
}

export default function TrendsChart({ points, height = 120 }) {
  if (!points?.length) return null

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <XAxis
          dataKey="date"
          tick={{ fill: '#64748b', fontSize: 10, fontFamily: 'monospace' }}
          axisLine={false}
          tickLine={false}
          interval="preserveStartEnd"
          tickFormatter={v => { const d = new Date(v); return `${d.getDate()}/${d.getMonth() + 1}` }}
        />
        <YAxis
          tick={{ fill: '#64748b', fontSize: 10, fontFamily: 'monospace' }}
          axisLine={false}
          tickLine={false}
          width={35}
        />
        <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
        <Tooltip content={<CustomTooltip />} />
        <Line type="monotone" dataKey="ctl" stroke="#f59e0b" strokeWidth={2} dot={false} name="Fitness" />
        <Line type="monotone" dataKey="atl" stroke="#ef4444" strokeWidth={1.5} dot={false} name="Fatica" opacity={0.8} />
        <Line type="monotone" dataKey="tsb" stroke="#22d3ee" strokeWidth={1.5} dot={false} name="Forma" opacity={0.85} />
      </LineChart>
    </ResponsiveContainer>
  )
}
