import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, Character } from '../types'

interface Props {
  messages: Message[]
  characters: Character[]
  streamingContent: string
  streamingCharacter: { id: number; name: string } | null
  isGenerating: boolean
  error: string | null
}

// 从名称生成颜色
function nameColor(name: string): string {
  const colors = [
    'bg-rose-500', 'bg-amber-500', 'bg-emerald-500', 'bg-sky-500',
    'bg-violet-500', 'bg-pink-500', 'bg-teal-500', 'bg-orange-500',
  ]
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return colors[Math.abs(hash) % colors.length]
}

export default function MessageList({
  messages,
  characters,
  streamingContent,
  streamingCharacter,
  isGenerating,
  error,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const displayMessages = messages.filter((m) => m.role !== 'system')

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-3xl mx-auto space-y-5">
        {displayMessages.length === 0 && !isGenerating && (
          <div className="text-center text-gray-400 dark:text-gray-500 py-20">
            选择发言者，开始聊天
          </div>
        )}

        {displayMessages.map((m) => {
          if (m.role === 'user') {
            return (
              <div key={m.id} className="flex justify-end">
                <div className="max-w-[80%]">
                  <div className="text-xs text-gray-400 dark:text-gray-500 mb-1 text-right">我</div>
                  <div className="bg-indigo-600 text-white rounded-2xl rounded-br-md px-4 py-3 text-sm leading-relaxed">
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                </div>
              </div>
            )
          }

          // AI 消息
          const charName = m.character_name || 'AI'
          return (
            <div key={m.id} className="flex justify-start">
              <div className="max-w-[80%]">
                <div className="flex items-center gap-2 mb-1">
                  <div className={`w-6 h-6 rounded-full ${nameColor(charName)} text-white flex items-center justify-center text-xs font-bold`}>
                    {charName.charAt(0)}
                  </div>
                  <span className="text-xs font-medium text-gray-600 dark:text-gray-400">{charName}</span>
                </div>
                <div className="bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100 rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed">
                  <div className="markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                </div>
              </div>
            </div>
          )
        })}

        {/* 流式输出中的 AI 消息 */}
        {isGenerating && streamingCharacter && (
          <div className="flex justify-start">
            <div className="max-w-[80%]">
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-6 h-6 rounded-full ${nameColor(streamingCharacter.name)} text-white flex items-center justify-center text-xs font-bold`}>
                  {streamingCharacter.name.charAt(0)}
                </div>
                <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                  {streamingCharacter.name} 正在输入…
                </span>
              </div>
              <div className="bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100 rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed">
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {streamingContent || '正在思考…'}
                  </ReactMarkdown>
                  {streamingContent && <span className="typing-cursor" />}
                </div>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex justify-center">
            <div className="max-w-[80%] rounded-lg px-4 py-3 text-sm bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800">
              {error}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}
