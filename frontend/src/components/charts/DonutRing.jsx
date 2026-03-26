export default function DonutRing({ value, max, color = '#f59e0b', size = 80, label }) {
  const pct = Math.min(value / max, 1)
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e293b" strokeWidth="5" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="5"
          strokeDasharray={`${circ * pct} ${circ * (1 - pct)}`} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-mono font-bold text-slate-50" style={{ fontSize: size > 60 ? 14 : 11 }}>{value}</span>
        {label && <span className="font-mono text-slate-500 uppercase" style={{ fontSize: 7, letterSpacing: 1 }}>{label}</span>}
      </div>
    </div>
  )
}
