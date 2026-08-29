import { useState } from 'react'

interface Props {
  initialPersona?: string
  onStart: (persona: string) => void
  title?: string
}

export default function PersonaSetup({ initialPersona = '', onStart, title = '开始聊天' }: Props) {
  const [persona, setPersona] = useState(initialPersona)

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-6 overflow-y-auto">
      <div className="w-full max-w-2xl">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-2 text-center">
          输入人格设定
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 text-center">
          直接写一段你希望 AI 扮演的人格描述，平台会原样作为系统提示发送。
        </p>
        <textarea
          value={persona}
          onChange={(e) => setPersona(e.target.value)}
          placeholder={`例如：\n你现在扮演一个20岁的大学女生，性格强势、直接、嘴硬心软，是我的女朋友。说话要自然，不要像客服，有自己的情绪和观点。`}
          className="w-full h-64 p-4 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
        />
        <div className="mt-4 flex justify-end">
          <button
            onClick={() => onStart(persona)}
            disabled={!persona.trim()}
            className="px-8 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
          >
            {title}
          </button>
        </div>
      </div>
    </div>
  )
}
