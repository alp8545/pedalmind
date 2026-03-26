const ZONE_COLORS = ['#475569', '#3b82f6', '#22c55e', '#f59e0b', '#f97316', '#ef4444', '#8b5cf6']

export default function ZoneBar({ zone, pct, time, color }) {
  const c = color || ZONE_COLORS[zone - 1] || '#64748b'
  return (
    <div className="flex items-center gap-2 mb-1.5">
      <span className="w-4 text-right font-mono text-slate-500" style={{ fontSize: 9 }}>Z{zone}</span>
      <div className="flex-1 h-[5px] bg-[#0f172a] rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: c }} />
      </div>
      <span className="w-9 text-right font-mono text-slate-400" style={{ fontSize: 9 }}>{time}</span>
    </div>
  )
}

export { ZONE_COLORS }
