import type { Conversation, Character, Message, ChatStreamChunk } from '../types'
import { authService } from './auth'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://ai-persona-backend-znpi.onrender.com/api'

// 后端源地址（去掉 /api 后缀），用于拼接静态图片 URL
export const BACKEND_ORIGIN = API_BASE.replace(/\/api\/?$/, '')

// 将后端返回的相对图片 URL 转为完整可访问 URL
export function resolveImageUrl(imageUrl: string | null | undefined): string {
  if (!imageUrl) return ''
  if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://') || imageUrl.startsWith('data:')) {
    return imageUrl
  }
  return `${BACKEND_ORIGIN}${imageUrl.startsWith('/') ? '' : '/'}${imageUrl}`
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (authService.isSupabaseMode()) {
    const token = await authService.getSessionToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${API_BASE}${url}`, {
    headers,
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `请求失败 (${res.status})`)
  }
  return res.json()
}

async function* parseSSE(res: Response): AsyncGenerator<ChatStreamChunk, void, unknown> {
  if (!res.body) throw new Error('无响应体')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue
      const jsonStr = trimmed.slice(6)
      try {
        yield JSON.parse(jsonStr)
      } catch { /* skip */ }
    }
  }
}

export const api = {
  // 会话
  createConversation: (title?: string) =>
    request<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  listConversations: () => request<Conversation[]>('/conversations'),
  getConversation: (id: number) => request<Conversation>(`/conversations/${id}`),
  updateConversation: (id: number, title: string) =>
    request<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: number) =>
    request<{ ok: boolean }>(`/conversations/${id}`, { method: 'DELETE' }),

  // 角色
  listCharacters: (convId: number) =>
    request<Character[]>(`/conversations/${convId}/characters`),
  createCharacter: (convId: number, name: string, persona: string) =>
    request<Character>(`/conversations/${convId}/characters`, {
      method: 'POST',
      body: JSON.stringify({ name, persona }),
    }),
  updateCharacter: (charId: number, data: { name?: string; persona?: string }) =>
    request<Character>(`/characters/${charId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteCharacter: (charId: number) =>
    request<{ ok: boolean }>(`/characters/${charId}`, { method: 'DELETE' }),

  // 消息
  getMessages: (id: number) => request<Message[]>(`/conversations/${id}/messages`),
  clearMessages: (id: number) =>
    request<{ ok: boolean; deleted: number }>(`/conversations/${id}/messages`, { method: 'DELETE' }),

  // 聊天流式
  async *chatStream(conversationId: number, message: string, characterId?: number) {
    const headers = await getAuthHeaders()
    const res = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ conversation_id: conversationId, message, character_id: characterId }),
    })
    if (!res.ok) throw new Error(`请求失败 (${res.status})`)
    yield* parseSSE(res)
  },

  // 全部 AI 回复
  async *replyAll(conversationId: number, message?: string) {
    const headers = await getAuthHeaders()
    const res = await fetch(`${API_BASE}/chat/reply-all`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ conversation_id: conversationId, message }),
    })
    if (!res.ok) throw new Error(`请求失败 (${res.status})`)
    yield* parseSSE(res)
  },

  // 自由讨论
  async *discussion(conversationId: number, characterIds: number[], rounds: number, message?: string) {
    const headers = await getAuthHeaders()
    const res = await fetch(`${API_BASE}/chat/discussion`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ conversation_id: conversationId, character_ids: characterIds, rounds, message }),
    })
    if (!res.ok) throw new Error(`请求失败 (${res.status})`)
    yield* parseSSE(res)
  },

  // 停止
  stopGeneration: () =>
    request<{ ok: boolean }>('/chat/stop', { method: 'POST' }),
}
