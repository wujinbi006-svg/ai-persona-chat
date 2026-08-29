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
  image_url: string | null  // 图片消息的图片URL，文字消息为null
  created_at: string
}

export interface ChatStreamChunk {
  type: 'content' | 'character_start' | 'character_done' | 'done' | 'error' | 'image_start' | 'image_done' | 'image_error'
  text?: string
  character_id?: number
  character_name?: string
  message?: string
  round?: number
  // 图片事件字段
  image_url?: string
  message_id?: number
}

export type Speaker = 'user' | number  // 'user' 或 character_id
