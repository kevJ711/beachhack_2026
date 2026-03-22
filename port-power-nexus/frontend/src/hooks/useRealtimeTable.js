import { useEffect, useRef, useState } from 'react'
import supabase from '../lib/supabase'

const EMPTY_REFETCH_ON = []

/**
 * Use with `refetchOnChanges` when another table must refresh because `events` updated.
 * Do not use `filter: type=eq.auction_end` — filtered Realtime INSERT is flaky; Activity
 * uses an unfiltered `events` subscription and updates while TopBar did not.
 */
export const REFETCH_ON_EVENTS_INSERT = [
  { table: 'events', event: 'INSERT' },
]

/**
 * Subscribes to Supabase Realtime `postgres_changes` for `tableName`, plus an initial REST load.
 * On each change, re-runs the same query (debounced) so limit/orderBy stay correct.
 *
 * No interval polling — updates rely on Realtime. If the UI is stale, enable Realtime for
 * this table (Supabase → Database → Replication) and ensure anon can SELECT (RLS).
 *
 * @param {string} tableName
 * @param {{
 *   filterColumn?: string
 *   filterValue?: string
 *   orderBy?: string
 *   orderAscending?: boolean
 *   limit?: number
 *   refetchOnChanges?: Array<{ table: string; event?: 'INSERT' | 'UPDATE' | 'DELETE' | '*'; filter?: string }>
 * }} [options]
 * `refetchOnChanges`: extra tables to listen to (e.g. `events` INSERT with filter) so this query
 * refetches when related rows change — useful when UPDATE replication is flaky.
 */
export default function useRealtimeTable(tableName, options = {}) {
  const filterColumn = options.filterColumn
  const filterValue = options.filterValue
  const orderBy = options.orderBy
  const orderAscending = options.orderAscending ?? false
  const limit = options.limit
  const refetchOnChanges = options.refetchOnChanges ?? EMPTY_REFETCH_ON

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

    let debounceRefetch = null
    const scheduleRefetch = () => {
      if (debounceRefetch) clearTimeout(debounceRefetch)
      debounceRefetch = setTimeout(() => {
        debounceRefetch = null
        if (!cancelled) fetchInitial()
      }, 120)
    }

    const onVisibility = () => {
      if (document.visibilityState === 'visible' && !cancelled) fetchInitial()
    }
    document.addEventListener('visibilitychange', onVisibility)

    const ch = supabase.channel(channelNameRef.current)

    ch.on(
      'postgres_changes',
      { event: '*', schema: 'public', table: tableName },
      () => {
        scheduleRefetch()
      }
    )

    for (const extra of refetchOnChanges) {
      const ev = extra.event ?? '*'
      const payload = {
        event: ev,
        schema: 'public',
        table: extra.table,
      }
      if (extra.filter) payload.filter = extra.filter
      ch.on('postgres_changes', payload, () => scheduleRefetch())
    }

    ch.subscribe((status, err) => {
        if (status === 'SUBSCRIBED') {
          if (import.meta.env.DEV) {
            console.info(`[useRealtimeTable:${tableName}] Realtime subscribed`)
          }
        }
        if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          console.warn(
            `[useRealtimeTable:${tableName}] Realtime ${status}:`,
            err?.message ?? err,
            '— enable this table for Realtime in Supabase (Replication).'
          )
        }
      })

    channelRef.current = ch

    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisibility)
      if (debounceRefetch) clearTimeout(debounceRefetch)
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
    refetchOnChanges,
  ])

  return { rows, lastUpdated }
}
