import { useState, useEffect } from 'react'
import type { Character } from '../types'

interface Props {
  open: boolean
  character?: Character | null
  onSave: (name: string, persona: string) => void
  onClose: () => void
}

export default function CharacterModal({ open, character, onSave, onClose }: Props) {
  const [name, setName] = useState('')
  const [persona, setPersona] = useState('')

  useEffect(() => {
    if (open) {
      setName(character?.name || '')
      setPersona(character?.persona || '')
    }
  }, [open, character])

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-2xl shadow-2xl">
        <div className="p-5 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            {character ? '编辑角色' : '添加 AI 角色'}
          </h2>
        </div>
        <div className="p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">角色名称</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：小雅"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">人格设定</label>
            <textarea
              value={persona}
              onChange={(e) => setPersona(e.target.value)}
              placeholder="例如：你现在扮演一个20岁的大学女生，性格强势、嘴硬心软，是我的女朋友。说话自然，有自己的情绪和观点……"
              className="w-full h-48 p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>
        <div className="p-5 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">取消</button>
          <button
            onClick={() => name.trim() && onSave(name.trim(), persona)}
            disabled={!name.trim()}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-sm font-medium"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  )
}
