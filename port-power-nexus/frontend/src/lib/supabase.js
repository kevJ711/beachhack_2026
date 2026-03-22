import { createClient } from '@supabase/supabase-js'

/**
 * Injected by Vite from repo-root `.env` (see `vite.config.js`):
 * - `VITE_SUPABASE_URL` ← `SUPABASE_URL` or `VITE_SUPABASE_URL`
 * - `VITE_SUPABASE_ANON_KEY` ← `SUPABASE_ANON_KEY` or `VITE_SUPABASE_ANON_KEY`
 * Never use `SUPABASE_KEY` (service role / sb_secret) in the browser.
 */
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL ?? ''
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY ?? ''

const missing = !supabaseUrl.trim() || !supabaseAnonKey.trim()

if (import.meta.env.DEV && missing) {
  console.error(
    '[supabase] Add SUPABASE_ANON_KEY to repo-root `.env` (Supabase Dashboard → Settings → API → anon public). SUPABASE_URL alone is not enough. Restart `npm run dev` after saving.'
  )
}

// Avoid crashing the whole app on import when .env is incomplete (dev / misconfig)
const safeUrl = supabaseUrl.trim() || 'https://placeholder.supabase.co'
const safeKey =
  supabaseAnonKey.trim() ||
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid-placeholder-add-SUPABASE_ANON_KEY-to-root-env'

export default createClient(safeUrl, safeKey)
