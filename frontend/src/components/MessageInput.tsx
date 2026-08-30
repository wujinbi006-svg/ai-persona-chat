import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import type { Character, Speaker, ChatMode } from '../types'

interface Props {
  characters: Character[]
  speaker: Speaker
  mode: ChatMode
  onSpeakerChange: (s: Speaker) => void
  onModeChange: (m: ChatMode) => void
  onSendUser: (message: string) => void
  onGenerateCharacter: (characterId: number) => void
  onReplyAll: () => void
  onOpenDiscussion: () => void
  onOpenDrama: () => void
  onStop: () => void
  isGenerating: boolean
  isDramaActive: boolean
  onDramaInterject: (message: string) => void
}

export default function MessageInput({
  characters,
  speaker,
  mode,
  onSpeakerChange,
  onModeChange,
  onSendUser,
  onGenerateCharacter,
  onReplyAll,
  onOpenDiscussion,
  onOpenDrama,
  onStop,
  isGenerating,
  isDramaActive,
  onDramaInterject,
}: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [mentionOpen, setMentionOpen] = useState(false)
  const [mentionSearch, setMentionSearch] = useState('')
  const [mentionStart, setMentionStart] = useState(-1)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 150) + 'px'
  }, [value])

  // 检测 @ 触发提及菜单
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    setValue(val)
    const cursorPos = e.target.selectionStart
    // 查找光标前最近的 @
    const beforeCursor = val.substring(0, cursorPos)
    const atMatch = beforeCursor.match(/@([^\s@]*)$/)
    if (atMatch) {
      setMentionOpen(true)
      setMentionSearch(atMatch[1])
      setMentionStart(cursorPos - atMatch[0].length)
    } else {
      setMentionOpen(false)
    }
  }

  const filteredCharacters = characters.filter((c) =>
    c.name.toLowerCase().includes(mentionSearch.toLowerCase())
  )

  const insertMention = (char: Character) => {
    const before = value.substring(0, mentionStart)
    const after = value.substring(mentionStart + mentionSearch.length + 1)
    const newValue = `${before}@${char.name} ${after}`
    setValue(newValue)
    setMentionOpen(false)
    setMentionSearch('')
    // 聚焦到插入后位置
    setTimeout(() => {
      if (textareaRef.current) {
        const pos = before.length + char.name.length + 2
        textareaRef.current.focus()
        textareaRef.current.setSelectionRange(pos, pos)
      }
    }, 0)
  }

  const handleSend = () => {
    const msg = value.trim()
    if (!msg || isGenerating) return
    if (isDramaActive) {
      // 戏剧模式中：用户插话
      onDramaInterject(msg)
      setValue('')
      return
    }
    if (speaker === 'user') {
      onSendUser(msg)
    } else {
      onSendUser(msg)
      setTimeout(() => onGenerateCharacter(speaker), 100)
    }
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (mentionOpen && filteredCharacters.length > 0) {
        e.preventDefault()
        insertMention(filteredCharacters[0])
        return
      }
      e.preventDefault()
      handleSend()
    }
    if (e.key === 'Escape' && mentionOpen) {
      setMentionOpen(false)
    }
  }

  const currentSpeakerName = speaker === 'user' ? '我' : characters.find((c) => c.id === speaker)?.name || 'AI'

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 p-4">
      <div className="max-w-3xl mx-auto space-y-3">
        {/* 发言者选择 + 模式 + 操作按钮 */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* 发言者下拉 */}
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700"
            >
              <span>{speaker === 'user' ? '👤' : '🤖'}</span>
              <span>{currentSpeakerName}</span>
              <span className="text-xs">▼</span>
            </button>
            {dropdownOpen && (
              <div className="absolute bottom-full left-0 mb-1 w-40 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-20 overflow-hidden">
                <button
                  onClick={() => { onSpeakerChange('user'); setDropdownOpen(false) }}
                  className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 ${speaker === 'user' ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400' : 'text-gray-700 dark:text-gray-300'}`}
                >
                  👤 我
                </button>
                {characters.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => { onSpeakerChange(c.id); setDropdownOpen(false) }}
                    className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 ${speaker === c.id ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400' : 'text-gray-700 dark:text-gray-300'}`}
                  >
                    🤖 {c.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 发言模式选择 */}
          <div className="flex items-center rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <button
              onClick={() => onModeChange('manual')}
              className={`px-2.5 py-1.5 text-xs ${mode === 'manual' ? 'bg-indigo-600 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}`}
            >
              手动
            </button>
            <button
              onClick={() => onModeChange('smart')}
              className={`px-2.5 py-1.5 text-xs ${mode === 'smart' ? 'bg-indigo-600 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'}`}
            >
              🧠 智能
            </button>
          </div>

          {/* 操作按钮 */}
          {!isGenerating ? (
            <>
              <button
                onClick={onReplyAll}
                disabled={characters.length === 0}
                className="px-3 py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                全部 AI
              </button>
              <button
                onClick={onOpenDiscussion}
                disabled={characters.length === 0}
                className="px-3 py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                💬 讨论
              </button>
              <button
                onClick={onOpenDrama}
                disabled={characters.length === 0}
                className="px-3 py-1.5 rounded-lg text-xs text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/20 hover:bg-purple-100 dark:hover:bg-purple-900/30 border border-purple-200 dark:border-purple-800 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                🎭 戏剧
              </button>
            </>
          ) : (
            <button
              onClick={onStop}
              className="px-3 py-1.5 rounded-lg text-xs text-white bg-red-600 hover:bg-red-700 font-medium"
            >
              ⏹ 停止
            </button>
          )}
        </div>

        {/* 输入框 + @提及菜单 */}
        <div className="relative flex items-end gap-3">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={isDramaActive ? '戏剧进行中，输入消息插话…' : speaker === 'user' ? '输入消息，@角色可指定回复，Enter 发送…' : `输入消息后发送，${currentSpeakerName}会回复…`}
            rows={1}
            disabled={isGenerating && !isDramaActive}
            className="flex-1 resize-none rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 max-h-[150px] disabled:opacity-60"
          />
          {/* @提及菜单 */}
          {mentionOpen && filteredCharacters.length > 0 && (
            <div className="absolute bottom-full left-0 mb-1 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-30 overflow-hidden max-h-48 overflow-y-auto">
              <div className="px-3 py-1.5 text-xs text-gray-400 border-b border-gray-100 dark:border-gray-700">选择角色</div>
              {filteredCharacters.map((c) => (
                <button
                  key={c.id}
                  onClick={() => insertMention(c)}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-indigo-50 dark:hover:bg-indigo-900/30 text-gray-700 dark:text-gray-300 flex items-center gap-2"
                >
                  <span className="w-6 h-6 rounded-full bg-indigo-500 text-white flex items-center justify-center text-xs">{c.name.charAt(0)}</span>
                  <span>{c.name}</span>
                </button>
              ))}
            </div>
          )}
          <button
            onClick={handleSend}
            disabled={isGenerating && !isDramaActive || !value.trim()}
            className="px-5 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors shrink-0"
          >
            {isDramaActive ? '插话' : speaker === 'user' ? '发送' : '发送并回复'}
          </button>
        </div>
      </div>
    </div>
  )
}
