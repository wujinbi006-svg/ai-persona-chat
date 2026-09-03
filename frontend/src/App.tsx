import { useState, useEffect, useCallback, useRef } from 'react'
import type { Conversation, Character, Message, Speaker, ChatMode, ChatStreamChunk } from './types'
import { api } from './services/api'
import { useAuth } from './contexts/AuthContext'
import Sidebar from './components/Sidebar'
import CharacterSetup from './components/CharacterSetup'
import ChatArea from './components/ChatArea'
import ChatPanelV2 from './components/ChatPanelV2'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'

type View = 'setup' | 'chat'

// Chat Core 2.0: 默认使用 V2 聊天面板，V1 保留作为回滚保险
const DEFAULT_USE_V2 = true

// 乐观更新的临时 ID 生成器
let optimisticIdCounter = 0
function genOptimisticId(): number {
  optimisticIdCounter += 1
  return -Date.now() - optimisticIdCounter
}

export default function App() {
  const { user, loading, isSupabaseMode, logout } = useAuth()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [characters, setCharacters] = useState<Character[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [view, setView] = useState<View>('setup')
  const [speaker, setSpeaker] = useState<Speaker>('user')
  const [mode, setMode] = useState<ChatMode>('manual')
  const [isGenerating, setIsGenerating] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingCharacter, setStreamingCharacter] = useState<{ id: number; name: string } | null>(null)
  const [imageGeneratingCharacter, setImageGeneratingCharacter] = useState<{ id: number; name: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dark, setDark] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [hash, setHash] = useState(window.location.hash)
  const abortRef = useRef(false)
  const [useV2, setUseV2] = useState<boolean>(DEFAULT_USE_V2)

  // 戏剧模式状态
  const [isDramaActive, setIsDramaActive] = useState(false)
  const conversationCache = useRef(new Map<number, { conv: Conversation; chars: Character[]; msgs: Message[] }>())
  const loadSequence = useRef(0)
  const [dramaRound, setDramaRound] = useState(0)

  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  // ============================================================
  // 优化1: 聊天列表缓存 + 后台刷新
  // 先显示 localStorage 缓存，后台获取最新数据
  // ============================================================
  const loadConversations = useCallback(async () => {
    // 先从缓存显示（如果有）
    try {
      const cached = localStorage.getItem('cached_conversations')
      if (cached) {
        const parsed = JSON.parse(cached)
        if (Array.isArray(parsed) && parsed.length > 0) {
          setConversations(parsed)
        }
      }
    } catch { /* ignore cache errors */ }

    // 后台获取最新数据
    try {
      const list = await api.listConversations()
      setConversations(list)
      // 更新缓存
      try {
        localStorage.setItem('cached_conversations', JSON.stringify(list))
      } catch { /* ignore */ }
    } catch (e) {
      console.error('加载会话失败', e)
    }
  }, [])

  useEffect(() => { loadConversations() }, [loadConversations])

  // ============================================================
  // 优化2: 打开聊天立即显示，后台加载数据
  // 移除重复的 listCharacters 调用
  // ============================================================
  const loadConversationData = useCallback(async (id: number) => {
    const sequence = ++loadSequence.current
    const cached = conversationCache.current.get(id)
    if (cached) {
      setConversations((prev) => prev.map((c) => (c.id === id ? cached.conv : c)))
      setCharacters(cached.chars)
      setMessages(cached.msgs)
    }
    try {
      const [conv, chars, msgs] = await Promise.all([
        api.getConversation(id),
        api.listCharacters(id),
        api.getMessages(id),
      ])
      if (sequence !== loadSequence.current) return cached?.chars || []
      setConversations((prev) => prev.map((c) => (c.id === id ? conv : c)))
      setCharacters(chars)
      setMessages(msgs)
      conversationCache.current.set(id, { conv, chars, msgs })
      if (sequence === loadSequence.current) setView(chars.length > 0 ? 'chat' : 'setup')
      return chars
    } catch (e) {
      setError('加载数据失败')
      return []
    }
  }, [])

  const activeConversation = conversations.find((c) => c.id === activeId) || null

  // 认证守卫
  if (loading) {
    return <div className="h-full flex items-center justify-center text-gray-500">加载中…</div>
  }
  if (isSupabaseMode && !user) {
    if (hash === '#register') return <RegisterPage />
    return <LoginPage />
  }

  // ============================================================
  // 优化3: 打开聊天立即切换UI，后台异步加载
  // ============================================================
  const handleSelect = async (id: number) => {
    // 立即切换 UI（不等待数据加载）
    setActiveId(id)
    setError(null)
    setStreamingContent('')
    setImageGeneratingCharacter(null)
    setSpeaker('user')
    setMode('manual')
    setIsDramaActive(false)
    setDramaRound(0)
    setSidebarOpen(false)

    // 如果本地已有该对话的 characters，立即进入聊天视图
    const existingChars = conversationCache.current.get(id)?.chars || []
    if (existingChars.length > 0) {
      setView('chat')
    }

    // 后台加载数据
    // 先展示聊天壳层，数据到达后再补齐角色/消息，避免三路请求形成可感知阻塞。
    setView(existingChars.length > 0 ? 'chat' : 'setup')
    // 不阻塞点击事件：数据在后台刷新，视图切换应立即对用户可见。
    void loadConversationData(id)
  }

  const handleNew = () => {
    setActiveId(null)
    setCharacters([])
    setMessages([])
    setStreamingContent('')
    setImageGeneratingCharacter(null)
    setError(null)
    setSpeaker('user')
    setMode('manual')
    setIsDramaActive(false)
    setDramaRound(0)
    setView('setup')
    setSidebarOpen(false)
  }

  // ============================================================
  // 优化4: 新建会话乐观更新
  // ============================================================
  const handleCreateConversation = async () => {
    // 乐观创建临时会话
    const tempId = genOptimisticId()
    const tempConv: Conversation = {
      id: tempId,
      title: '新对话',
      persona: '',
      scene: '',
      scene_time: '',
      scene_context: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    setConversations((prev) => [tempConv, ...prev])
    setActiveId(tempId)
    setCharacters([])
    setMessages([])

    try {
      const conv = await api.createConversation('新对话')
      // 替换乐观对象
      setConversations((prev) => prev.map((c) => (c.id === tempId ? conv : c)))
      setActiveId(conv.id)
      return conv.id
    } catch (e) {
      // 失败回滚
      setConversations((prev) => prev.filter((c) => c.id !== tempId))
      setActiveId(null)
      setError('创建会话失败')
      return null
    }
  }

  // ============================================================
  // 优化5: 创建角色乐观更新（最高优先级）
  // 点击保存立即显示，API 返回后替换，失败 rollback
  // ============================================================
  const handleAddCharacter = async (name: string, persona: string) => {
    // 1. 立即乐观显示新角色
    const tempId = genOptimisticId()
    const tempChar: Character = {
      id: tempId,
      conversation_id: activeId || 0,
      name,
      persona,
      sort_order: characters.length,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as Character
    setCharacters((prev) => [...prev, tempChar])

    let convId = activeId
    try {
      // 2. 如果没有 activeId，先创建会话
      if (!convId) {
        const newId = await handleCreateConversation()
        if (!newId) {
          // 创建会话失败，回滚角色
          setCharacters((prev) => prev.filter((c) => c.id !== tempId))
          return
        }
        convId = newId
        // 更新临时角色的 conversation_id
        setCharacters((prev) => prev.map((c) => (c.id === tempId ? { ...c, conversation_id: newId } : c)))
      }

      // 3. API 创建角色
      const created = await api.createCharacter(convId, name, persona)

      // 4. 替换乐观对象为真实对象
      setCharacters((prev) => prev.map((c) => (c.id === tempId ? created : c)))

      // 5. 更新会话列表的 updated_at（不重新 GET 整个列表）
      setConversations((prev) => prev.map((c) =>
        c.id === convId ? { ...c, updated_at: new Date().toISOString() } : c
      ))
    } catch (e) {
      // 6. 失败回滚
      setCharacters((prev) => prev.filter((c) => c.id !== tempId))
      setError('创建角色失败，请重试')
    }
  }

  // ============================================================
  // 优化6: 编辑角色乐观更新
  // ============================================================
  const handleEditCharacter = async (id: number, name: string, persona: string) => {
    // 保存原始值用于回滚
    const original = characters.find((c) => c.id === id)
    // 立即乐观更新
    setCharacters((prev) => prev.map((c) => (c.id === id ? { ...c, name, persona } : c)))

    try {
      const updated = await api.updateCharacter(id, { name, persona })
      setCharacters((prev) => prev.map((c) => (c.id === id ? updated : c)))
    } catch (e) {
      // 失败回滚
      if (original) {
        setCharacters((prev) => prev.map((c) => (c.id === id ? original : c)))
      }
      setError('编辑角色失败')
    }
  }

  // ============================================================
  // 优化7: 删除角色乐观更新
  // ============================================================
  const handleDeleteCharacter = async (id: number) => {
    const original = characters.find((c) => c.id === id)
    // 立即移除
    setCharacters((prev) => prev.filter((c) => c.id !== id))
    if (speaker === id) setSpeaker('user')

    try {
      await api.deleteCharacter(id)
    } catch (e) {
      // 失败恢复
      if (original) {
        setCharacters((prev) => [...prev, original].sort((a, b) => a.sort_order - b.sort_order))
      }
      setError('删除角色失败')
    }
  }

  // ============================================================
  // 优化8: 排序乐观更新
  // ============================================================
  const handleMoveCharacter = async (id: number, direction: 'up' | 'down') => {
    const idx = characters.findIndex((c) => c.id === id)
    if (idx < 0) return
    const swapIdx = direction === 'up' ? idx - 1 : idx + 1
    if (swapIdx < 0 || swapIdx >= characters.length) return

    // 保存原始顺序用于回滚
    const original = [...characters]
    // 立即乐观交换
    const updated = [...characters]
    ;[updated[idx], updated[swapIdx]] = [updated[swapIdx], updated[idx]]
    // 更新 sort_order
    updated[idx] = { ...updated[idx], sort_order: idx }
    updated[swapIdx] = { ...updated[swapIdx], sort_order: swapIdx }
    setCharacters(updated)

    try {
      await api.moveCharacter(id, direction)
    } catch (e) {
      // 失败回滚
      setCharacters(original)
      console.error('移动角色失败', e)
    }
  }

  const handleUpdateScene = async (scene: string, sceneTime: string, sceneContext: string) => {
    if (!activeId) return
    try {
      const conv = await api.updateConversation(activeId, { scene, scene_time: sceneTime, scene_context: sceneContext })
      setConversations((prev) => prev.map((c) => (c.id === activeId ? conv : c)))
    } catch (e) {
      setError('保存场景失败')
    }
  }

  const handleEnterChat = () => {
    setView('chat')
  }

  // ============================================================
  // 优化9: 删除会话乐观更新
  // ============================================================
  const handleDeleteConversation = async (id: number) => {
    const original = conversations.find((c) => c.id === id)
    // 立即移除
    setConversations((prev) => prev.filter((c) => c.id !== id))
    if (activeId === id) {
      setActiveId(null)
      setCharacters([])
      setMessages([])
      setView('setup')
    }

    try {
      await api.deleteConversation(id)
      // 更新缓存
      try {
        const cached = localStorage.getItem('cached_conversations')
        if (cached) {
          const parsed = JSON.parse(cached)
          localStorage.setItem('cached_conversations', JSON.stringify(parsed.filter((c: Conversation) => c.id !== id)))
        }
      } catch { /* ignore */ }
    } catch (e) {
      // 失败恢复
      if (original) {
        setConversations((prev) => [...prev, original])
      }
      setError('删除会话失败')
    }
  }

  const handleClearMessages = async () => {
    if (!activeId) return
    await api.clearMessages(activeId)
    setMessages([])
  }

  // 通用：处理图片相关 SSE 事件
  const handleImageChunk = (chunk: ChatStreamChunk) => {
    if (chunk.type === 'image_start' && chunk.character_id && chunk.character_name) {
      setImageGeneratingCharacter({ id: chunk.character_id, name: chunk.character_name })
    } else if (chunk.type === 'image_done') {
      setImageGeneratingCharacter(null)
    } else if (chunk.type === 'image_error') {
      setImageGeneratingCharacter(null)
      setError(chunk.message || '图片生成失败')
    }
  }

  // ============================================================
  // V1 旧聊天路径（保留作为回滚保险，V2 是默认生产链路）
  // 优化10: SSE 后不重新 GET 全部 messages，直接用 SSE 内容更新
  // ============================================================
  const handleSendUser = async (msg: string) => {
    if (!activeId) return
    const tempMsg: Message = {
      id: -Date.now(), conversation_id: activeId, character_id: null,
      character_name: null, role: 'user', content: msg, image_url: null, created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempMsg])
    try {
      let currentCharId: number | null = null
      let currentCharName = ''
      let assistantContent = ''
      for await (const chunk of api.chatStream(activeId, msg, undefined, mode)) {
        handleImageChunk(chunk)
        if (chunk.type === 'character_start' && chunk.character_id && chunk.character_name) {
          currentCharId = chunk.character_id
          currentCharName = chunk.character_name
          assistantContent = ''
          setStreamingCharacter({ id: chunk.character_id, name: chunk.character_name })
          setStreamingContent('')
        } else if (chunk.type === 'content' && chunk.text) {
          assistantContent += chunk.text
          setStreamingContent((prev) => prev + chunk.text)
        } else if (chunk.type === 'character_done') {
          // 直接 append AI 消息，不重新 GET
          if (assistantContent.trim() && currentCharId) {
            const aiMsg: Message = {
              id: -Date.now() - 1,
              conversation_id: activeId,
              character_id: currentCharId,
              character_name: currentCharName,
              role: 'assistant',
              content: assistantContent,
              image_url: null,
              created_at: new Date().toISOString(),
            }
            setMessages((prev) => [...prev, aiMsg])
          }
          setStreamingContent('')
          setStreamingCharacter(null)
          assistantContent = ''
        } else if (chunk.type === 'error') {
          setError(chunk.message || '发送失败')
          break
        }
      }
      // 只更新会话 updated_at，不重新加载整个列表
      setConversations((prev) => prev.map((c) =>
        c.id === activeId ? { ...c, updated_at: new Date().toISOString() } : c
      ))
    } catch (e: any) {
      setError(e?.message || '发送失败')
      setMessages((prev) => prev.filter((m) => m.id !== tempMsg.id))
    } finally {
      setStreamingContent('')
      setStreamingCharacter(null)
      setImageGeneratingCharacter(null)
    }
  }

  const handleGenerateCharacter = async (charId: number) => {
    if (!activeId || isGenerating) return
    const char = characters.find((c) => c.id === charId)
    if (!char) return

    setIsGenerating(true)
    setError(null)
    setStreamingContent('')
    setStreamingCharacter({ id: char.id, name: char.name })
    abortRef.current = false

    try {
      let accumulated = ''
      for await (const chunk of api.chatStream(activeId, '（请基于当前对话继续发言）', charId)) {
        if (abortRef.current) break
        handleImageChunk(chunk)
        if (chunk.type === 'content' && chunk.text) {
          accumulated += chunk.text
          setStreamingContent(accumulated)
        } else if (chunk.type === 'error') {
          setError(chunk.message || '生成失败')
          break
        }
      }
      // 直接 append AI 消息
      if (accumulated.trim()) {
        const aiMsg: Message = {
          id: -Date.now() - 2,
          conversation_id: activeId,
          character_id: charId,
          character_name: char.name,
          role: 'assistant',
          content: accumulated,
          image_url: null,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, aiMsg])
      }
      setConversations((prev) => prev.map((c) =>
        c.id === activeId ? { ...c, updated_at: new Date().toISOString() } : c
      ))
    } catch (e: any) {
      setError(e?.message || '生成失败')
    } finally {
      setIsGenerating(false)
      setStreamingContent('')
      setStreamingCharacter(null)
      setImageGeneratingCharacter(null)
      abortRef.current = false
    }
  }

  const handleReplyAll = async () => {
    if (!activeId || isGenerating) return
    setIsGenerating(true)
    setError(null)
    setStreamingContent('')
    abortRef.current = false

    try {
      let currentCharId: number | null = null
      let currentCharName = ''
      let assistantContent = ''
      for await (const chunk of api.replyAll(activeId)) {
        if (abortRef.current) { await api.stopGeneration(); break }
        handleImageChunk(chunk)
        if (chunk.type === 'character_start' && chunk.character_id && chunk.character_name) {
          currentCharId = chunk.character_id
          currentCharName = chunk.character_name
          assistantContent = ''
          setStreamingCharacter({ id: chunk.character_id, name: chunk.character_name })
          setStreamingContent('')
        } else if (chunk.type === 'content' && chunk.text) {
          assistantContent += chunk.text
          setStreamingContent((prev) => prev + chunk.text)
        } else if (chunk.type === 'character_done') {
          if (assistantContent.trim() && currentCharId) {
            const aiMsg: Message = {
              id: -Date.now() - 3,
              conversation_id: activeId,
              character_id: currentCharId,
              character_name: currentCharName,
              role: 'assistant',
              content: assistantContent,
              image_url: null,
              created_at: new Date().toISOString(),
            }
            setMessages((prev) => [...prev, aiMsg])
          }
          setStreamingContent('')
          assistantContent = ''
        } else if (chunk.type === 'error') {
          setError(chunk.message || '全部回复失败')
          break
        }
      }
      setConversations((prev) => prev.map((c) =>
        c.id === activeId ? { ...c, updated_at: new Date().toISOString() } : c
      ))
    } catch (e: any) {
      setError(e?.message || '全部回复失败')
    } finally {
      setIsGenerating(false)
      setStreamingContent('')
      setStreamingCharacter(null)
      setImageGeneratingCharacter(null)
      abortRef.current = false
    }
  }

  const handleStartDiscussion = async (charIds: number[], rounds: number) => {
    if (!activeId || isGenerating) return
    setIsGenerating(true)
    setError(null)
    setStreamingContent('')
    abortRef.current = false

    try {
      let currentCharId: number | null = null
      let currentCharName = ''
      let assistantContent = ''
      for await (const chunk of api.discussion(activeId, charIds, rounds)) {
        if (abortRef.current) { await api.stopGeneration(); break }
        handleImageChunk(chunk)
        if (chunk.type === 'character_start' && chunk.character_id && chunk.character_name) {
          currentCharId = chunk.character_id
          currentCharName = chunk.character_name
          assistantContent = ''
          setStreamingCharacter({ id: chunk.character_id, name: chunk.character_name })
          setStreamingContent('')
        } else if (chunk.type === 'content' && chunk.text) {
          assistantContent += chunk.text
          setStreamingContent((prev) => prev + chunk.text)
        } else if (chunk.type === 'character_done') {
          if (assistantContent.trim() && currentCharId) {
            const aiMsg: Message = {
              id: -Date.now() - 4,
              conversation_id: activeId,
              character_id: currentCharId,
              character_name: currentCharName,
              role: 'assistant',
              content: assistantContent,
              image_url: null,
              created_at: new Date().toISOString(),
            }
            setMessages((prev) => [...prev, aiMsg])
          }
          setStreamingContent('')
          assistantContent = ''
        } else if (chunk.type === 'error') {
          setError(chunk.message || '讨论出错')
          break
        }
      }
      setConversations((prev) => prev.map((c) =>
        c.id === activeId ? { ...c, updated_at: new Date().toISOString() } : c
      ))
    } catch (e: any) {
      setError(e?.message || '讨论失败')
    } finally {
      setIsGenerating(false)
      setStreamingContent('')
      setStreamingCharacter(null)
      setImageGeneratingCharacter(null)
      abortRef.current = false
    }
  }

  // 戏剧模式
  const handleStartDrama = async (
    charIds: number[], rounds: number, interval: number,
    scene: string, sceneTime: string, sceneContext: string
  ) => {
    if (!activeId || isGenerating) return
    setIsGenerating(true)
    setIsDramaActive(true)
    setDramaRound(1)
    setError(null)
    setStreamingContent('')
    abortRef.current = false

    try {
      let currentCharId: number | null = null
      let currentCharName = ''
      let assistantContent = ''
      for await (const chunk of api.dramaStream(activeId, charIds, rounds, interval, scene, sceneTime, sceneContext)) {
        if (abortRef.current) { await api.dramaStop(); break }
        handleImageChunk(chunk)
        if (chunk.type === 'round_start' && chunk.round) {
          setDramaRound(chunk.round)
        } else if (chunk.type === 'character_start' && chunk.character_id && chunk.character_name) {
          currentCharId = chunk.character_id
          currentCharName = chunk.character_name
          assistantContent = ''
          setStreamingCharacter({ id: chunk.character_id, name: chunk.character_name })
          setStreamingContent('')
        } else if (chunk.type === 'content' && chunk.text) {
          assistantContent += chunk.text
          setStreamingContent((prev) => prev + chunk.text)
        } else if (chunk.type === 'character_done') {
          if (assistantContent.trim() && currentCharId) {
            const aiMsg: Message = {
              id: -Date.now() - 5,
              conversation_id: activeId,
              character_id: currentCharId,
              character_name: currentCharName,
              role: 'assistant',
              content: assistantContent,
              image_url: null,
              created_at: new Date().toISOString(),
            }
            setMessages((prev) => [...prev, aiMsg])
          }
          setStreamingContent('')
          assistantContent = ''
        } else if (chunk.type === 'drama_done' || chunk.type === 'done') {
          // 戏剧结束
        } else if (chunk.type === 'error') {
          setError(chunk.message || '戏剧出错')
          break
        }
      }
      setConversations((prev) => prev.map((c) =>
        c.id === activeId ? { ...c, updated_at: new Date().toISOString() } : c
      ))
    } catch (e: any) {
      setError(e?.message || '戏剧失败')
    } finally {
      setIsGenerating(false)
      setIsDramaActive(false)
      setDramaRound(0)
      setStreamingContent('')
      setStreamingCharacter(null)
      setImageGeneratingCharacter(null)
      abortRef.current = false
    }
  }

  const handleDramaPause = () => { api.dramaPause().catch(() => {}) }
  const handleDramaResume = () => { api.dramaResume().catch(() => {}) }
  const handleDramaStop = () => {
    abortRef.current = true
    api.dramaStop().catch(() => {})
  }

  const handleDramaInterject = async (message: string) => {
    if (!activeId) return
    const tempMsg: Message = {
      id: -Date.now(), conversation_id: activeId, character_id: null,
      character_name: null, role: 'user', content: message, image_url: null, created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempMsg])
    try {
      await api.dramaInterject(activeId, message)
    } catch (e) {
      setError('插话失败')
      setMessages((prev) => prev.filter((m) => m.id !== tempMsg.id))
    }
  }

  const handleStop = () => {
    abortRef.current = true
    api.stopGeneration().catch(() => {})
  }

  return (
    <div className="h-full flex bg-white dark:bg-gray-950 text-gray-800 dark:text-gray-100">
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/40 z-30 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}
      <div className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} fixed md:relative md:translate-x-0 z-40 h-full transition-transform duration-200 flex flex-col`}>
        <div className="flex-1 overflow-hidden">
          <Sidebar
            conversations={conversations}
            activeId={activeId}
            onSelect={handleSelect}
            onNew={handleNew}
            onDelete={handleDeleteConversation}
          />
        </div>
        {isSupabaseMode && user && (
          <div className="border-t border-gray-200 dark:border-gray-700 p-3 bg-gray-50 dark:bg-gray-900">
            <div className="text-xs text-gray-500 dark:text-gray-400 truncate mb-1.5">{user.email}</div>
            <button
              onClick={logout}
              className="w-full py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700"
            >
              退出登录
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 flex flex-col h-full min-w-0">
        <div className="md:hidden flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
          <button onClick={() => setSidebarOpen(true)} className="p-2 text-gray-600 dark:text-gray-300">☰</button>
          <button onClick={() => setDark(!dark)} className="p-2 text-gray-600 dark:text-gray-300 text-sm">{dark ? '☀️' : '🌙'}</button>
        </div>
        <div className="hidden md:flex fixed top-3 right-3 z-20">
          <button onClick={() => setDark(!dark)} className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 text-sm">
            {dark ? '☀️' : '🌙'}
          </button>
        </div>

        {view === 'setup' ? (
          <CharacterSetup
            conversationId={activeId || 0}
            characters={characters}
            onAddCharacter={handleAddCharacter}
            onEditCharacter={handleEditCharacter}
            onDeleteCharacter={handleDeleteCharacter}
            onMoveCharacter={handleMoveCharacter}
            onEnterChat={handleEnterChat}
          />
        ) : activeConversation ? (
          useV2 ? (
            <ChatPanelV2
              conversationId={activeConversation.id}
              characters={characters}
              initialMessages={messages}
              onBack={() => setView('setup')}
            />
          ) : (
            <ChatArea
              conversation={activeConversation}
              characters={characters}
              messages={messages}
              streamingContent={streamingContent}
              streamingCharacter={streamingCharacter}
              isGenerating={isGenerating}
              error={error}
              speaker={speaker}
              mode={mode}
              isDramaActive={isDramaActive}
              dramaRound={dramaRound}
              onSpeakerChange={setSpeaker}
              onModeChange={setMode}
              onSendUser={handleSendUser}
              onGenerateCharacter={handleGenerateCharacter}
              onReplyAll={handleReplyAll}
              onStartDiscussion={handleStartDiscussion}
              onStartDrama={handleStartDrama}
              onDramaPause={handleDramaPause}
              onDramaResume={handleDramaResume}
              onDramaStop={handleDramaStop}
              onDramaInterject={handleDramaInterject}
              onStop={handleStop}
              onAddCharacter={handleAddCharacter}
              onEditCharacter={handleEditCharacter}
              onDeleteCharacter={handleDeleteCharacter}
              onMoveCharacter={handleMoveCharacter}
              onUpdateScene={handleUpdateScene}
              onClearMessages={handleClearMessages}
              imageGeneratingCharacter={imageGeneratingCharacter}
            />
          )
        ) : (
          <CharacterSetup
            conversationId={activeId || 0}
            characters={characters}
            onAddCharacter={handleAddCharacter}
            onEditCharacter={handleEditCharacter}
            onDeleteCharacter={handleDeleteCharacter}
            onMoveCharacter={handleMoveCharacter}
            onEnterChat={handleEnterChat}
          />
        )}
      </div>
    </div>
  )
}
