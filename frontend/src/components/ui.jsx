export function G({ children, className = '', style }) {
  return (
    <div
      className={`rounded-[14px] p-4 ${className}`}
      style={{
        background: 'linear-gradient(135deg, rgba(15,23,42,0.8), rgba(15,23,42,0.5))',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        border: '1px solid rgba(148,163,184,0.08)',
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function Label({ children }) {
  return (
    <div className="mb-1.5 font-mono text-slate-400 uppercase" style={{ fontSize: 11, letterSpacing: 1.5 }}>
      {children}
    </div>
  )
}

export function MetricCard({ label, value, sub, color = '#f8fafc' }) {
  return (
    <G className="p-3 text-center">
      <Label>{label}</Label>
      <div className="font-mono font-bold" style={{ fontSize: 24, color }}>{value}</div>
      {sub && <div className="font-mono text-green-400" style={{ fontSize: 11 }}>{sub}</div>}
    </G>
  )
}
