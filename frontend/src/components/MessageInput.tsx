import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import type { Character, Speaker } from '../types'

interface Props {
  characters: Character[]
  speaker: Speaker
  onSpeakerChange: (s: Speaker) => void
  onSendUser: (message: string) => void
  onGenerateCharacter: (characterId: number) => void
  onReplyAll: () => void
  onOpenDiscussion: () => void
  onStop: () => void
  isGenerating: boolean
}

export default function MessageInput({
  characters,
  speaker,
  onSpeakerChange,
  onSendUser,
  onGenerateCharacter,
  onReplyAll,
  onOpenDiscussion,
  onStop,
  isGenerating,
}: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [dropdownOpen, setDropdownOpen] = useState(false)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 150) + 'px'
  }, [value])

  const handleSend = () => {
    const msg = value.trim()
    if (!msg || isGenerating) return
    if (speaker === 'user') {
      onSendUser(msg)
    } else {
      // 选择了 AI 角色：先发用户消息，再让该角色回复
      onSendUser(msg)
      setTimeout(() => onGenerateCharacter(speaker), 100)
    }
    setValue('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const currentSpeakerName = speaker === 'user' ? '我' : characters.find((c) => c.id === speaker)?.name || 'AI'

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 p-4">
      <div className="max-w-3xl mx-auto space-y-3">
        {/* 发言者选择 + 操作按钮 */}
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

          {/* 操作按钮 */}
          {!isGenerating ? (
            <>
              <button
                onClick={onReplyAll}
                disabled={characters.length === 0}
                className="px-3 py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                全部 AI 回复
              </button>
              <button
                onClick={onOpenDiscussion}
                disabled={characters.length === 0}
                className="px-3 py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                AI 自由讨论
              </button>
            </>
          ) : (
            <button
              onClick={onStop}
              className="px-3 py-1.5 rounded-lg text-xs text-white bg-red-600 hover:bg-red-700 font-medium"
            >
              ⏹ 停止生成
            </button>
          )}
        </div>

        {/* 输入框 */}
        <div className="flex items-end gap-3">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={speaker === 'user' ? '输入消息，Enter 发送…' : `输入消息后发送，${currentSpeakerName}会回复…`}
            rows={1}
            disabled={isGenerating}
            className="flex-1 resize-none rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 max-h-[150px] disabled:opacity-60"
          />
          <button
            onClick={handleSend}
            disabled={isGenerating || !value.trim()}
            className="px-5 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors shrink-0"
          >
            {speaker === 'user' ? '发送' : '发送并回复'}
          </button>
        </div>
      </div>
    </div>
  )
}
