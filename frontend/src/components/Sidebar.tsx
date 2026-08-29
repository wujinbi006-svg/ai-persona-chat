import { useState } from 'react'
import type { Conversation } from '../types'

interface Props {
  conversations: Conversation[]
  activeId: number | null
  onSelect: (id: number) => void
  onNew: () => void
  onDelete: (id: number) => void
}

export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete }: Props) {
  const [confirmId, setConfirmId] = useState<number | null>(null)

  return (
    <div className="w-64 h-full flex flex-col border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full py-2.5 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium transition-colors flex items-center justify-center gap-2"
        >
          <span className="text-lg leading-none">+</span> 新建聊天
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3 space-y-1">
        {conversations.length === 0 && (
          <div className="text-center text-gray-400 text-sm py-8">暂无聊天记录</div>
        )}
        {conversations.map((c) => (
          <div
            key={c.id}
            className={`group relative rounded-lg px-3 py-2.5 cursor-pointer text-sm transition-colors ${
              activeId === c.id
                ? 'bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300'
                : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
            }`}
            onClick={() => onSelect(c.id)}
          >
            <div className="truncate pr-6">{c.title || '新对话'}</div>
            <button
              onClick={(e) => {
                e.stopPropagation()
                setConfirmId(c.id)
              }}
              className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 transition-opacity text-xs"
              title="删除"
            >
              ✕
            </button>
            {confirmId === c.id && (
              <div
                className="absolute inset-0 bg-white dark:bg-gray-800 rounded-lg flex items-center justify-center gap-2 z-10 border border-gray-200 dark:border-gray-700"
                onClick={(e) => e.stopPropagation()}
              >
                <span className="text-xs text-gray-600 dark:text-gray-400">确认删除？</span>
                <button
                  onClick={() => { onDelete(c.id); setConfirmId(null) }}
                  className="text-xs text-red-600 hover:text-red-700 font-medium"
                >
                  删除
                </button>
                <button
                  onClick={() => setConfirmId(null)}
                  className="text-xs text-gray-500 hover:text-gray-700"
                >
                  取消
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
