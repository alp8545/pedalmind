export default function PMChart({ ctl, atl, tsb, width = 260, height = 80 }) {
  if (!ctl?.length) return null
  const mkLine = (data, color) => {
    const mx = Math.max(...data) + 10
    const mn = Math.min(...data) - 10
    const rg = mx - mn || 1
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - mn) / rg) * (height - 6) - 3}`).join(' ')
    return <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" opacity="0.85" />
  }
  return (
    <svg width={width} height={height} className="block w-full" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      {mkLine(ctl, '#f59e0b')}
      {mkLine(atl, '#ef4444')}
      {tsb && mkLine(tsb, '#22d3ee')}
    </svg>
  )
}
