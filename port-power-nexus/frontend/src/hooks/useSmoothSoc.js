import { useEffect, useRef, useState } from 'react'

/**
 * Smoothly approaches target SOC (0–100), similar to demo mock charging ramp.
 */
export default function useSmoothSoc(targetSoc) {
  const raw = Number(targetSoc)
  const target = Number.isFinite(raw) ? Math.max(0, Math.min(100, raw)) : 0

  const [display, setDisplay] = useState(target)
  const displayRef = useRef(target)
  const targetRef = useRef(target)
  targetRef.current = target

  useEffect(() => {
    let cancelled = false
    const alpha = 0.14

    function tick() {
      if (cancelled) return
      const t = targetRef.current
      const c = displayRef.current
      const next = c + (t - c) * alpha
      if (Math.abs(t - next) < 0.25) {
        if (displayRef.current !== t) {
          displayRef.current = t
          setDisplay(t)
        }
        return
      }
      displayRef.current = next
      setDisplay(next)
      requestAnimationFrame(tick)
    }

    const raf = requestAnimationFrame(tick)
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
    }
  }, [target])

  return display
}
