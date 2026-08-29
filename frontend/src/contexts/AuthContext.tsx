import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authService, AuthUser } from '../services/auth'

interface AuthContextType {
  user: AuthUser | null
  loading: boolean
  isSupabaseMode: boolean
  login: (email: string, password: string) => Promise<string | null>
  register: (email: string, password: string) => Promise<string | null>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

// 本地模式默认用户
const LOCAL_USER: AuthUser = { id: 'local-user', email: 'local@dev.local', display_name: '本地用户' }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const isSupabaseMode = authService.isSupabaseMode()

  useEffect(() => {
    if (!isSupabaseMode) {
      setUser(LOCAL_USER)
      setLoading(false)
      return
    }

    let mounted = true
    authService.getCurrentUser().then((u) => {
      if (mounted) {
        setUser(u)
        setLoading(false)
      }
    })

    const unsubscribe = authService.onAuthStateChange((u) => {
      if (mounted) setUser(u)
    })

    return () => {
      mounted = false
      unsubscribe()
    }
  }, [isSupabaseMode])

  const login = async (email: string, password: string): Promise<string | null> => {
    const { user: u, error } = await authService.signIn(email, password)
    if (error) return error
    setUser(u)
    return null
  }

  const register = async (email: string, password: string): Promise<string | null> => {
    const { user: u, error } = await authService.signUp(email, password)
    if (error) return error
    if (u) setUser(u)
    return null
  }

  const logout = async () => {
    await authService.signOut()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, isSupabaseMode, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
