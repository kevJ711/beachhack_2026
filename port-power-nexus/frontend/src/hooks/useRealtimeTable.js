import { useEffect, useRef, useState } from 'react'
import supabase from '../lib/supabase'

/**
 * Subscribes to Supabase Realtime `postgres_changes` for `tableName`, plus an initial REST load.
 *
 * If the UI never updates until you refresh: enable Realtime for this table in the Supabase
 * project and ensure the `anon` role can SELECT rows (RLS). Optional polling: set
 * `pollIntervalMs` or `VITE_SUPABASE_POLL_MS` (>0).
 *
 * @param {string} tableName
 * @param {{
 *   filterColumn?: string
 *   filterValue?: string
 *   orderBy?: string
 *   orderAscending?: boolean
 *   limit?: number
 *   pollIntervalMs?: number
 * }} [options]
 * `pollIntervalMs`: full re-fetch every N ms (0 = off). Default off; env `VITE_SUPABASE_POLL_MS` to opt in.
 */
export default function useRealtimeTable(tableName, options = {}) {
  const filterColumn = options.filterColumn
  const filterValue = options.filterValue
  const orderBy = options.orderBy
  const orderAscending = options.orderAscending ?? false
  const limit = options.limit
  const envPoll = import.meta.env.VITE_SUPABASE_POLL_MS
  const pollIntervalMs =
    options.pollIntervalMs ??
    (envPoll != null && String(envPoll).trim() !== ''
      ? Math.max(0, parseInt(String(envPoll), 10) || 0)
      : 0)

  const channelNameRef = useRef(
    `realtime-${tableName}-${Date.now()}`
  )
  const channelRef = useRef(null)
  const [rows, setRows] = useState([])
  const [lastUpdated, setLastUpdated] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function fetchInitial() {
      let query = supabase.from(tableName).select('*')

      if (filterColumn != null && filterValue !== undefined) {
        query = query.eq(filterColumn, filterValue)
      }
      if (orderBy) {
        query = query.order(orderBy, { ascending: orderAscending })
      }
      if (typeof limit === 'number') {
        query = query.limit(limit)
      }

      const { data, error } = await query
      if (cancelled) return
      if (error) {
        console.error(
          `[useRealtimeTable:${tableName}] REST error:`,
          error.message ?? error,
          '| code:',
          error.code,
          '| details:',
          error.details,
          '| hint:',
          error.hint,
          '\n→ If 401/403: check anon key + RLS (SELECT allowed for anon on public.' +
            tableName +
            ').'
        )
        setRows([])
      } else {
        setRows(data ?? [])
      }
      setLastUpdated(Date.now())
    }

    fetchInitial()

    let pollTimer = null
    if (pollIntervalMs > 0) {
      pollTimer = setInterval(() => {
        if (!cancelled) fetchInitial()
      }, pollIntervalMs)
    }

    const ch = supabase
      .channel(channelNameRef.current)
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: tableName },
        (payload) => {
          if (payload.eventType === 'DELETE') {
            const oldRow = payload.old
            if (!oldRow || oldRow.id == null) return
            setRows((prev) => prev.filter((r) => r.id !== oldRow.id))
            setLastUpdated(Date.now())
            return
          }
          if (payload.eventType !== 'INSERT' && payload.eventType !== 'UPDATE') {
            return
          }
          const row = payload.new
          if (!row || row.id == null) return

          setRows((prev) => {
            const idx = prev.findIndex((r) => r.id === row.id)
            if (idx >= 0) {
              const next = [...prev]
              next[idx] = row
              return next
            }
            return [...prev, row]
          })
          setLastUpdated(Date.now())
        }
      )
      .subscribe((status, err) => {
        if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          console.warn(
            `[useRealtimeTable:${tableName}] Realtime ${status}:`,
            err?.message ?? err,
            '— enable this table for Realtime in Supabase, or set VITE_SUPABASE_POLL_MS for REST polling.'
          )
        }
      })

    channelRef.current = ch

    return () => {
      cancelled = true
      if (pollTimer) clearInterval(pollTimer)
      if (channelRef.current) {
        supabase.removeChannel(channelRef.current)
        channelRef.current = null
      }
    }
  }, [
    tableName,
    filterColumn,
    filterValue,
    orderBy,
    orderAscending,
    limit,
    pollIntervalMs,
  ])

  return { rows, lastUpdated }
}
