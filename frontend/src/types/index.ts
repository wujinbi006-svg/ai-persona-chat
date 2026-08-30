export interface Conversation {
  id: number
  title: string
  persona: string
  scene: string
  scene_time: string
  scene_context: string
  created_at: string
  updated_at: string
}

export interface Character {
  id: number
  conversation_id: number
  name: string
  persona: string
  avatar: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Memory {
  id: number
  conversation_id: number | null
  character_id: number | null
  content: string
  memory_type: 'user' | 'character' | 'relationship' | 'event' | 'preference' | 'fact'
  importance: number
  is_active: boolean
  created_at: string
  updated_at: string
  last_used_at: string
}

export interface Message {
  id: number
  conversation_id: number
  character_id: number | null
  character_name: string | null
  role: 'system' | 'user' | 'assistant'
  content: string
  image_url: string | null
  created_at: string
}

export interface ChatStreamChunk {
  type: 'content' | 'character_start' | 'character_done' | 'done' | 'error'
    | 'image_start' | 'image_done' | 'image_error'
    | 'drama_start' | 'drama_paused' | 'drama_done'
    | 'round_start' | 'round_done'
  text?: string
  character_id?: number
  character_name?: string
  message?: string
  round?: number
  rounds?: number
  interval?: number
  image_url?: string
  message_id?: number
}

export type Speaker = 'user' | number
export type ChatMode = 'manual' | 'smart'
