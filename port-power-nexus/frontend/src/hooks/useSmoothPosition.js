import { useEffect, useRef, useState } from 'react'

function easeInOutQuad(t) {
  return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2
}

/**
 * Animates (x,y) toward (tx,ty).
 * When `resetEpoch` increases, optionally starts from `(fromX, fromY)` (e.g. spawn off-screen left).
 */
export default function useSmoothPosition(
  tx,
  ty,
  durationMs = 1400,
  resetEpoch = 0,
  fromX = null,
  fromY = null
) {
  const [pos, setPos] = useState({ x: tx, y: ty })
  const posRef = useRef({ x: tx, y: ty })
  const rafRef = useRef(null)
  const lastResetEpoch = useRef(0)

  useEffect(() => {
    const to = { x: tx, y: ty }
    let from = posRef.current

    if (
      resetEpoch > 0 &&
      resetEpoch !== lastResetEpoch.current &&
      fromX != null &&
      fromY != null
    ) {
      lastResetEpoch.current = resetEpoch
      from = { x: fromX, y: fromY }
      posRef.current = from
      setPos(from)
    }

    const close =
      Math.abs(from.x - to.x) < 0.05 && Math.abs(from.y - to.y) < 0.05
    if (close) {
      posRef.current = to
      setPos(to)
      return
    }

    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }

    const start = performance.now()

    function tick(now) {
      const elapsed = now - start
      const u = Math.min(1, elapsed / durationMs)
      const e = easeInOutQuad(u)
      const x = from.x + (to.x - from.x) * e
      const y = from.y + (to.y - from.y) * e
      posRef.current = { x, y }
      setPos({ x, y })
      if (u < 1) {
        rafRef.current = requestAnimationFrame(tick)
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [tx, ty, durationMs, resetEpoch, fromX, fromY])

  return pos
}
