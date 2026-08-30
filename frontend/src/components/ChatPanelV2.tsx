/**
 * Phase 6: ChatPanelV2 - 统一聊天面板（UI 收敛）
 *
 * 核心概念：
 * - 聊天模式：普通 / 群聊 / 剧情
 * - 发言策略：指定角色 / @角色 / 智能选择
 *
 * 使用 v2 统一接口 + useChatV2 hook（乐观更新 + 统一 SSE 事件）。
 * 与旧的 ChatArea 并存，后续 Phase 逐步替换。
 */
import React, { useState, useCallback, useRef, useEffect } from 'react'
import type { Character, Message } from '../types'
import { useChatV2 } from '../hooks/useChatV2'
import { resolveImageUrl } from '../services/api'

type ChatMode = 'normal' | 'group' | 'drama'
type SpeakerStrategy = 'specific' | 'mention' | 'smart'

interface ChatPanelV2Props {
  conversationId: number
  characters: Character[]
  initialMessages?: Message[]
  onBack?: () => void
}

export const ChatPanelV2: React.FC<ChatPanelV2Props> = ({
  conversationId,
  characters,
  initialMessages = [],
  onBack,
}) => {
  // 聊天模式和发言策略
  const [chatMode, setChatMode] = useState<ChatMode>('normal')
  const [speakerStrategy, setSpeakerStrategy] = useState<SpeakerStrategy>('specific')
  const [selectedCharacterId, setSelectedCharacterId] = useState<number | null>(
    characters.length > 0 ? characters[0].id : null
  )

  // 输入框
  const [inputValue, setInputValue] = useState('')
  const [showMentionMenu, setShowMentionMenu] = useState(false)
  const [mentionSearch, setMentionSearch] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // 剧情模式设置
  const [dramaInterval, setDramaInterval] = useState(3)
  const [showDramaSettings, setShowDramaSettings] = useState(false)

  // 使用 v2 统一状态管理
  const {
    messages,
    generation,
    imageGeneratingCharacter,
    isGenerating,
    isPaused,
    sendMessage,
    stopGeneration,
    pauseGeneration,
    resumeGeneration,
  } = useChatV2({
    conversationId,
    characters,
    initialMessages,
  })

  // 角色变化时更新默认选中
  useEffect(() => {
    if (!selectedCharacterId && characters.length > 0) {
      setSelectedCharacterId(characters[0].id)
    }
  }, [characters, selectedCharacterId])

  // 发送消息
  const handleSend = useCallback(async () => {
    const message = inputValue.trim()
    if (!message || isGenerating) return

    setInputValue('')

    // 解析 @角色
    const mentionedIds: number[] = []
    let cleanedMessage = message
    for (const char of characters) {
      const pattern = new RegExp(`@${char.name}`, 'g')
      if (pattern.test(message)) {
        mentionedIds.push(char.id)
        cleanedMessage = cleanedMessage.replace(pattern, '').trim()
      }
    }

    // 根据模式和策略调用 v2 接口
    if (chatMode === 'normal') {
      if (speakerStrategy === 'mention' && mentionedIds.length > 0) {
        await sendMessage({
          message: cleanedMessage,
          mode: 'normal',
          strategy: 'mention',
          mentionedCharacterIds: mentionedIds,
        })
      } else if (speakerStrategy === 'smart') {
        await sendMessage({
          message,
          mode: 'normal',
          strategy: 'smart',
        })
      } else if (selectedCharacterId) {
        await sendMessage({
          message,
          mode: 'normal',
          strategy: 'specific',
          characterId: selectedCharacterId,
        })
      }
    } else if (chatMode === 'group') {
      // 群聊：所有角色依次回复
      await sendMessage({
        message,
        mode: 'group',
        strategy: 'specific',
      })
    }
    // 剧情模式有专门的开始按钮
  }, [inputValue, isGenerating, chatMode, speakerStrategy, selectedCharacterId, characters, sendMessage])

  // 键盘事件
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
    // @ 触发角色选择
    if (e.key === '@') {
      setShowMentionMenu(true)
      setMentionSearch('')
    }
  }, [handleSend])

  // 插入 @角色
  const insertMention = useCallback((character: Character) => {
    setInputValue(prev => prev + `@${character.name} `)
    setShowMentionMenu(false)
    setSpeakerStrategy('mention')
    inputRef.current?.focus()
  }, [])

  // 过滤角色列表
  const filteredCharacters = characters.filter(c =>
    c.name.toLowerCase().includes(mentionSearch.toLowerCase())
  )

  // 渲染消息
  const renderMessage = (msg: Message) => {
    const isUser = msg.role === 'user'
    const character = characters.find(c => c.id === msg.character_id)

    return (
      <div key={msg.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
        <div className={`max-w-[75%] ${isUser ? 'order-2' : 'order-1'}`}>
          {!isUser && character && (
            <div className="text-xs text-gray-500 mb-1 font-medium">{character.name}</div>
          )}
          <div
            className={`rounded-2xl px-4 py-3 ${
              isUser
                ? 'bg-purple-600 text-white rounded-br-md'
                : 'bg-gray-100 text-gray-900 rounded-bl-md'
            }`}
          >
            {msg.content && (
              <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{msg.content}</p>
            )}
            {msg.image_url && (
              <img
                src={resolveImageUrl(msg.image_url)}
                alt="生成的图片"
                className="mt-2 rounded-lg max-w-full cursor-pointer hover:opacity-90 transition-opacity"
                onClick={() => window.open(resolveImageUrl(msg.image_url), '_blank')}
              />
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-white">
      {/* 顶部：模式切换 */}
      <div className="border-b border-gray-200 px-4 py-3 bg-gray-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {onBack && (
              <button
                onClick={onBack}
                className="text-gray-500 hover:text-gray-700 text-sm"
              >
                ← 返回
              </button>
            )}
            <span className="text-sm font-medium text-gray-700">AI 人格聊天</span>
          </div>

          {/* 三模式切换 */}
          <div className="flex bg-gray-200 rounded-lg p-1">
            <button
              onClick={() => setChatMode('normal')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                chatMode === 'normal' ? 'bg-white text-purple-600 shadow-sm' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              💬 普通
            </button>
            <button
              onClick={() => setChatMode('group')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                chatMode === 'group' ? 'bg-white text-purple-600 shadow-sm' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              👥 群聊
            </button>
            <button
              onClick={() => setChatMode('drama')}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                chatMode === 'drama' ? 'bg-white text-purple-600 shadow-sm' : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              🎭 剧情
            </button>
          </div>
        </div>

        {/* 普通模式：发言策略选择 */}
        {chatMode === 'normal' && (
          <div className="flex items-center gap-3 mt-3">
            <span className="text-xs text-gray-500">发言策略：</span>
            <div className="flex gap-1">
              <button
                onClick={() => setSpeakerStrategy('specific')}
                className={`px-2 py-1 text-xs rounded ${
                  speakerStrategy === 'specific' ? 'bg-purple-100 text-purple-700' : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                指定角色
              </button>
              <button
                onClick={() => setSpeakerStrategy('mention')}
                className={`px-2 py-1 text-xs rounded ${
                  speakerStrategy === 'mention' ? 'bg-purple-100 text-purple-700' : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                @角色
              </button>
              <button
                onClick={() => setSpeakerStrategy('smart')}
                className={`px-2 py-1 text-xs rounded ${
                  speakerStrategy === 'smart' ? 'bg-purple-100 text-purple-700' : 'text-gray-500 hover:bg-gray-100'
                }`}
              >
                🧠 智能选择
              </button>
            </div>

            {/* 指定角色下拉 */}
            {speakerStrategy === 'specific' && (
              <select
                value={selectedCharacterId || ''}
                onChange={e => setSelectedCharacterId(Number(e.target.value))}
                className="text-xs border border-gray-300 rounded px-2 py-1 bg-white"
              >
                {characters.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            )}
          </div>
        )}

        {/* 剧情模式控制 */}
        {chatMode === 'drama' && (
          <div className="flex items-center gap-3 mt-3">
            <span className="text-xs text-gray-500">
              角色：{characters.map(c => c.name).join(' · ')}
            </span>
            <div className="flex items-center gap-2">
              <label className="text-xs text-gray-500">间隔：</label>
              <select
                value={dramaInterval}
                onChange={e => setDramaInterval(Number(e.target.value))}
                className="text-xs border border-gray-300 rounded px-2 py-1 bg-white"
                disabled={isGenerating}
              >
                <option value={0}>立即</option>
                <option value={1}>1秒</option>
                <option value={3}>3秒</option>
                <option value={5}>5秒</option>
                <option value={10}>10秒</option>
              </select>
            </div>
            {!isGenerating ? (
              <button
                onClick={() => {
                  // 剧情模式开始（使用 v2 接口）
                  sendMessage({
                    message: inputValue,
                    mode: 'drama',
                    strategy: 'specific',
                    dramaConfig: { interval: dramaInterval, character_ids: characters.map(c => c.id) },
                  })
                  setInputValue('')
                }}
                className="px-3 py-1 text-xs bg-purple-600 text-white rounded hover:bg-purple-700"
              >
                ▶ 开始剧情
              </button>
            ) : (
              <div className="flex gap-2">
                {isPaused ? (
                  <button
                    onClick={resumeGeneration}
                    className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700"
                  >
                    ▶ 继续
                  </button>
                ) : (
                  <button
                    onClick={pauseGeneration}
                    className="px-3 py-1 text-xs bg-yellow-600 text-white rounded hover:bg-yellow-700"
                  >
                    ⏸ 暂停
                  </button>
                )}
                <button
                  onClick={stopGeneration}
                  className="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700"
                >
                  ⏹ 停止
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="text-4xl mb-3">💬</div>
            <p className="text-sm">开始和 AI 角色聊天吧</p>
            <p className="text-xs mt-1">输入 @ 可以指定角色回复</p>
          </div>
        ) : (
          messages.map(renderMessage)
        )}

        {/* 流式输出中 */}
        {generation.streamingContent && (
          <div className="flex justify-start mb-4">
            <div className="max-w-[75%]">
              {generation.currentCharacterName && (
                <div className="text-xs text-gray-500 mb-1 font-medium">
                  {generation.currentCharacterName}
                </div>
              )}
              <div className="bg-gray-100 text-gray-900 rounded-2xl rounded-bl-md px-4 py-3">
                <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                  {generation.streamingContent}
                  <span className="inline-block w-2 h-4 bg-purple-500 ml-1 animate-pulse" />
                </p>
              </div>
            </div>
          </div>
        )}

        {/* 图片生成中 */}
        {imageGeneratingCharacter && (
          <div className="flex justify-start mb-4">
            <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                {imageGeneratingCharacter.name} 正在生成图片...
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 输入区域 */}
      <div className="border-t border-gray-200 px-4 py-3 bg-white relative">
        {/* @角色选择菜单 */}
        {showMentionMenu && (
          <div className="absolute bottom-full left-4 right-4 mb-2 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto z-10">
            <div className="p-2">
              <input
                type="text"
                placeholder="搜索角色..."
                value={mentionSearch}
                onChange={e => setMentionSearch(e.target.value)}
                className="w-full text-sm border border-gray-200 rounded px-2 py-1 mb-2"
                autoFocus
              />
              {filteredCharacters.map(char => (
                <button
                  key={char.id}
                  onClick={() => insertMention(char)}
                  className="w-full text-left px-2 py-1.5 text-sm hover:bg-purple-50 rounded"
                >
                  @{char.name}
                </button>
              ))}
              {filteredCharacters.length === 0 && (
                <p className="text-xs text-gray-400 px-2 py-1">没有找到角色</p>
              )}
            </div>
          </div>
        )}

        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              chatMode === 'normal'
                ? speakerStrategy === 'mention'
                  ? '输入 @ 选择角色，然后输入消息...'
                  : speakerStrategy === 'smart'
                    ? '输入消息，AI 自动决定谁回复...'
                    : '输入消息，按 Enter 发送...'
                : chatMode === 'group'
                  ? '输入消息，所有角色依次回复...'
                  : '输入剧情开场消息，然后点击开始剧情...'
            }
            rows={1}
            className="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            style={{ maxHeight: '120px' }}
          />
          {chatMode !== 'drama' && (
            <button
              onClick={handleSend}
              disabled={!inputValue.trim() || isGenerating}
              className="px-4 py-2 bg-purple-600 text-white text-sm rounded-xl hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {isGenerating ? '生成中...' : '发送'}
            </button>
          )}
          {isGenerating && chatMode !== 'drama' && (
            <button
              onClick={stopGeneration}
              className="px-4 py-2 bg-red-500 text-white text-sm rounded-xl hover:bg-red-600 transition-colors"
            >
              停止
            </button>
          )}
        </div>

        {/* 错误提示 */}
        {generation.errorMessage && (
          <div className="mt-2 text-xs text-red-500 bg-red-50 px-3 py-2 rounded-lg">
            {generation.errorMessage}
          </div>
        )}
      </div>
    </div>
  )
}

export default ChatPanelV2
