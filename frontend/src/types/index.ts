export interface Conversation {
  id: number
  title: string
  persona: string
  created_at: string
  updated_at: string
}

export interface Character {
  id: number
  conversation_id: number
  name: string
  persona: string
  avatar: string | null
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  conversation_id: number
  character_id: number | null
  character_name: string | null
  role: 'system' | 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ChatStreamChunk {
  type: 'content' | 'character_start' | 'character_done' | 'done' | 'error'
  text?: string
  character_id?: number
  character_name?: string
  message?: string
  round?: number
}

export type Speaker = 'user' | number  // 'user' 或 character_id
