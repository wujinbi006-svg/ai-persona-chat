import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, Character } from '../types'
import { resolveImageUrl } from '../services/api'

interface Props {
  messages: Message[]
  characters: Character[]
  streamingContent: string
  streamingCharacter: { id: number; name: string } | null
  isGenerating: boolean
  error: string | null
  // 图片生成中：哪个角色正在生成图片
  imageGeneratingCharacter: { id: number; name: string } | null
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

// 图片消息气泡
function ImageBubble({ imageUrl, onClick }: { imageUrl: string; onClick: () => void }) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const fullUrl = resolveImageUrl(imageUrl)

  if (error) {
    return (
      <div className="mt-2 rounded-lg px-3 py-2 text-xs text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-900/50">
        图片加载失败
      </div>
    )
  }

  return (
    <div className="mt-2 relative">
      {!loaded && (
        <div className="w-full h-48 rounded-lg bg-gray-100 dark:bg-gray-800 animate-pulse flex items-center justify-center">
          <span className="text-xs text-gray-400">图片加载中…</span>
        </div>
      )}
      <img
        src={fullUrl}
        alt="角色图片"
        onClick={onClick}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        className={`rounded-lg max-w-full cursor-pointer hover:opacity-90 transition-opacity ${loaded ? '' : 'hidden'}`}
        style={{ maxHeight: '360px', objectFit: 'contain' }}
      />
    </div>
  )
}

// 图片生成中加载占位
function ImageGeneratingBubble({ characterName }: { characterName: string }) {
  return (
    <div className="mt-2 rounded-lg bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 px-4 py-6 flex flex-col items-center gap-2">
      <div className="flex gap-1.5">
        <div className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '0ms' }} />
        <div className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '150ms' }} />
        <div className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
      <span className="text-xs text-gray-400 dark:text-gray-500">{characterName} 正在生成图片……</span>
    </div>
  )
}

export default function MessageList({
  messages,
  characters,
  streamingContent,
  streamingCharacter,
  isGenerating,
  error,
  imageGeneratingCharacter,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const [previewImage, setPreviewImage] = useState<string | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, imageGeneratingCharacter])

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
          const hasImage = !!m.image_url
          const hasText = !!m.content && m.content.trim().length > 0

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
                  {hasText && (
                    <div className="markdown-body">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </div>
                  )}
                  {hasImage && (
                    <ImageBubble
                      imageUrl={m.image_url!}
                      onClick={() => setPreviewImage(resolveImageUrl(m.image_url))}
                    />
                  )}
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
                {/* 图片生成中状态（在文字流式输出后、图片生成期间显示） */}
                {imageGeneratingCharacter && imageGeneratingCharacter.id === streamingCharacter.id && (
                  <ImageGeneratingBubble characterName={imageGeneratingCharacter.name} />
                )}
              </div>
            </div>
          </div>
        )}

        {/* 图片生成中（非流式输出场景，如 reply-all / discussion 中文字已完成但图片还在生成） */}
        {imageGeneratingCharacter && (!isGenerating || !streamingCharacter || imageGeneratingCharacter.id !== streamingCharacter?.id) && (
          <div className="flex justify-start">
            <div className="max-w-[80%]">
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-6 h-6 rounded-full ${nameColor(imageGeneratingCharacter.name)} text-white flex items-center justify-center text-xs font-bold`}>
                  {imageGeneratingCharacter.name.charAt(0)}
                </div>
                <span className="text-xs font-medium text-gray-600 dark:text-gray-400">{imageGeneratingCharacter.name}</span>
              </div>
              <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-bl-md px-4 py-3">
                <ImageGeneratingBubble characterName={imageGeneratingCharacter.name} />
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

      {/* 图片点击放大预览 Modal */}
      {previewImage && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
          onClick={() => setPreviewImage(null)}
        >
          <img
            src={previewImage}
            alt="图片预览"
            className="max-w-full max-h-full rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            className="absolute top-4 right-4 w-10 h-10 rounded-full bg-white/20 text-white text-xl flex items-center justify-center hover:bg-white/30 transition-colors"
            onClick={() => setPreviewImage(null)}
          >
            ✕
          </button>
        </div>
      )}
    </div>
  )
}
