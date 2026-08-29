import { useState, useEffect, useCallback, useRef } from 'react'
import type { Conversation, Character, Message, Speaker, ChatStreamChunk } from './types'
import { api } from './services/api'
import { useAuth } from './contexts/AuthContext'
import Sidebar from './components/Sidebar'
import CharacterSetup from './components/CharacterSetup'
import ChatArea from './components/ChatArea'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'

type View = 'setup' | 'chat'

export default function App() {
  const { user, loading, isSupabaseMode, logout } = useAuth()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [characters, setCharacters] = useState<Character[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [view, setView] = useState<View>('setup')
  const [speaker, setSpeaker] = useState<Speaker>('user')
  const [isGenerating, setIsGenerating] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingCharacter, setStreamingCharacter] = useState<{ id: number; name: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dark, setDark] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [hash, setHash] = useState(window.location.hash)
  const abortRef = useRef(false)

  // 所有 Hooks 必须在条件返回之前调用
  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  const loadConversations = useCallback(async () => {
    try {
      const list = await api.listConversations()
      setConversations(list)
    } catch (e) {
      console.error('加载会话失败', e)
    }
  }, [])

  useEffect(() => { loadConversations() }, [loadConversations])

  const loadConversationData = useCallback(async (id: number) => {
    try {
      const [chars, msgs] = await Promise.all([
        api.listCharacters(id),
        api.getMessages(id),
      ])
      setCharacters(chars)
      setMessages(msgs)
    } catch (e) {
      setError('加载数据失败')
    }
  }, [])

  const activeConversation = conversations.find((c) => c.id === activeId) || null

  // 认证守卫：Supabase 模式下未登录显示登录页
  if (loading) {
    return <div className="h-full flex items-center justify-center text-gray-500">加载中…</div>
  }
  if (isSupabaseMode && !user) {
    if (hash === '#register') return <RegisterPage />
    return <LoginPage />
  }

  const handleSelect = async (id: number) => {
    setActiveId(id)
    setError(null)
    setStreamingContent('')
    setSpeaker('user')
    await loadConversationData(id)
    const chars = await api.listCharacters(id)
    if (chars.length === 0) {
      setView('setup')
    } else {
      setView('chat')
    }
    setSidebarOpen(false)
  }

  const handleNew = () => {
    setActiveId(null)
    setCharacters([])
    setMessages([])
    setStreamingContent('')
    setError(null)
    setSpeaker('user')
    setView('setup')
    setSidebarOpen(false)
  }

  const handleCreateConversation = async () => {
    try {
      const conv = await api.createConversation('新对话')
      setActiveId(conv.id)
      setCharacters([])
      setMessages([])
      await loadConversations()
      return conv.id
    } catch (e) {
      setError('创建会话失败')
      return null
    }
  }

  const handleAddCharacter = async (name: string, persona: string) => {
    if (!activeId) {
      const newId = await handleCreateConversation()
      if (!newId) return
      await api.createCharacter(newId, name, persona)
      const chars = await api.listCharacters(newId)
      setCharacters(chars)
      await loadConversations()
    } else {
      await api.createCharacter(activeId, name, persona)
      const chars = await api.listCharacters(activeId)
      setCharacters(chars)
    }
  }

  const handleEditCharacter = async (id: number, name: string, persona: string) => {
    await api.updateCharacter(id, { name, persona })
    if (activeId) {
      const chars = await api.listCharacters(activeId)
      setCharacters(chars)
    }
  }

  const handleDeleteCharacter = async (id: number) => {
    await api.deleteCharacter(id)
    if (activeId) {
      const chars = await api.listCharacters(activeId)
      setCharacters(chars)
      if (speaker === id) setSpeaker('user')
    }
  }

  const handleEnterChat = () => {
    setView('chat')
  }

  const handleDeleteConversation = async (id: number) => {
    await api.deleteConversation(id)
    if (activeId === id) {
      setActiveId(null)
      setCharacters([])
      setMessages([])
      setView('setup')
    }
    await loadConversations()
  }

  const handleClearMessages = async () => {
    if (!activeId) return
    await api.clearMessages(activeId)
    setMessages([])
  }

  const handleSendUser = async (msg: string) => {
    if (!activeId) return
    const tempMsg: Message = {
      id: -Date.now(), conversation_id: activeId, character_id: null,
      character_name: null, role: 'user', content: msg, created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempMsg])
    try {
      for await (const _ of api.chatStream(activeId, msg)) { /* just done */ }
      const fresh = await api.getMessages(activeId)
      setMessages(fresh)
      await loadConversations()
    } catch (e: any) {
      setError(e?.message || '发送失败')
      setMessages((prev) => prev.filter((m) => m.id !== tempMsg.id))
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
        if (chunk.type === 'content' && chunk.text) {
          accumulated += chunk.text
          setStreamingContent(accumulated)
        } else if (chunk.type === 'error') {
          setError(chunk.message || '生成失败')
          break
        }
      }
      const fresh = await api.getMessages(activeId)
      setMessages(fresh)
      await loadConversations()
    } catch (e: any) {
      setError(e?.message || '生成失败')
    } finally {
      setIsGenerating(false)
      setStreamingContent('')
      setStreamingCharacter(null)
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
      for await (const chunk of api.replyAll(activeId)) {
        if (abortRef.current) { await api.stopGeneration(); break }
        if (chunk.type === 'character_start' && chunk.character_id && chunk.character_name) {
          setStreamingCharacter({ id: chunk.character_id, name: chunk.character_name })
          setStreamingContent('')
        } else if (chunk.type === 'content' && chunk.text) {
          setStreamingContent((prev) => prev + chunk.text)
        } else if (chunk.type === 'character_done') {
          const fresh = await api.getMessages(activeId)
          setMessages(fresh)
        } else if (chunk.type === 'error') {
          setError(chunk.message || '生成失败')
          break
        }
      }
      const fresh = await api.getMessages(activeId)
      setMessages(fresh)
      await loadConversations()
    } catch (e: any) {
      setError(e?.message || '全部回复失败')
    } finally {
      setIsGenerating(false)
      setStreamingContent('')
      setStreamingCharacter(null)
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
      for await (const chunk of api.discussion(activeId, charIds, rounds)) {
        if (abortRef.current) { await api.stopGeneration(); break }
        if (chunk.type === 'character_start' && chunk.character_id && chunk.character_name) {
          setStreamingCharacter({ id: chunk.character_id, name: chunk.character_name })
          setStreamingContent('')
        } else if (chunk.type === 'content' && chunk.text) {
          setStreamingContent((prev) => prev + chunk.text)
        } else if (chunk.type === 'character_done') {
          const fresh = await api.getMessages(activeId)
          setMessages(fresh)
        } else if (chunk.type === 'error') {
          setError(chunk.message || '讨论出错')
          break
        }
      }
      const fresh = await api.getMessages(activeId)
      setMessages(fresh)
      await loadConversations()
    } catch (e: any) {
      setError(e?.message || '讨论失败')
    } finally {
      setIsGenerating(false)
      setStreamingContent('')
      setStreamingCharacter(null)
      abortRef.current = false
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
            onEnterChat={handleEnterChat}
          />
        ) : activeConversation ? (
          <ChatArea
            conversation={activeConversation}
            characters={characters}
            messages={messages}
            streamingContent={streamingContent}
            streamingCharacter={streamingCharacter}
            isGenerating={isGenerating}
            error={error}
            speaker={speaker}
            onSpeakerChange={setSpeaker}
            onSendUser={handleSendUser}
            onGenerateCharacter={handleGenerateCharacter}
            onReplyAll={handleReplyAll}
            onStartDiscussion={handleStartDiscussion}
            onStop={handleStop}
            onAddCharacter={handleAddCharacter}
            onEditCharacter={handleEditCharacter}
            onDeleteCharacter={handleDeleteCharacter}
            onClearMessages={handleClearMessages}
          />
        ) : (
          <CharacterSetup
            conversationId={activeId || 0}
            characters={characters}
            onAddCharacter={handleAddCharacter}
            onEditCharacter={handleEditCharacter}
            onDeleteCharacter={handleDeleteCharacter}
            onEnterChat={handleEnterChat}
          />
        )}
      </div>
    </div>
  )
}
