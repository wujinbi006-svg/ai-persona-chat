import { createClient, SupabaseClient } from '@supabase/supabase-js'

// 注意：VITE_SUPABASE_ANON_KEY 是公开的 anon key，不是 Secret
// 真正的 Secret（OPENAI_API_KEY、SUPABASE_SERVICE_ROLE_KEY、DATABASE_URL）只存在后端
const USE_SUPABASE = import.meta.env.VITE_USE_SUPABASE === 'true' || true
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || 'https://hduxrpsfgacdthgpdjxk.supabase.co'
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhkdXhycHNmZ2FjZHRoZ3BkanhrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU0Njc0NjUsImV4cCI6MjEwMTA0MzQ2NX0.T_pmgnU38jevz5mM1tvsJAGDkESm3jXdnzCKq2vyaac'

export interface AuthUser {
  id: string
  email: string
  display_name?: string
}

let supabase: SupabaseClient | null = null

if (USE_SUPABASE && SUPABASE_URL && SUPABASE_ANON_KEY) {
  supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
}

export const authService = {
  isSupabaseMode: () => USE_SUPABASE,

  getSupabase: () => supabase,

  async signUp(email: string, password: string): Promise<{ user: AuthUser | null; error: string | null }> {
    if (!supabase) return { user: null, error: '认证未配置' }
    const { data, error } = await supabase.auth.signUp({ email, password })
    if (error) return { user: null, error: error.message }
    if (!data.user) return { user: null, error: '注册失败' }
    return {
      user: { id: data.user.id, email: data.user.email || email, display_name: email.split('@')[0] },
      error: null,
    }
  },

  async signIn(email: string, password: string): Promise<{ user: AuthUser | null; error: string | null }> {
    if (!supabase) return { user: null, error: '认证未配置' }
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) return { user: null, error: error.message }
    if (!data.user) return { user: null, error: '登录失败' }
    return {
      user: { id: data.user.id, email: data.user.email || email, display_name: email.split('@')[0] },
      error: null,
    }
  },

  async signOut(): Promise<void> {
    if (supabase) {
      await supabase.auth.signOut()
    }
  },

  async getCurrentUser(): Promise<AuthUser | null> {
    if (!supabase) return null
    const { data } = await supabase.auth.getUser()
    if (!data.user) return null
    return { id: data.user.id, email: data.user.email || '', display_name: data.user.email?.split('@')[0] }
  },

  async getSessionToken(): Promise<string | null> {
    if (!supabase) return null
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token || null
  },

  onAuthStateChange(callback: (user: AuthUser | null) => void) {
    if (!supabase) return () => {}
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        callback({ id: session.user.id, email: session.user.email || '', display_name: session.user.email?.split('@')[0] })
      } else {
        callback(null)
      }
    })
    return () => data.subscription.unsubscribe()
  },
}
