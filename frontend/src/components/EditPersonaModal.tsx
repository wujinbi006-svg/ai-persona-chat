import { useState, useEffect } from 'react'

interface Props {
  open: boolean
  initialPersona: string
  onSave: (persona: string) => void
  onClose: () => void
}

export default function EditPersonaModal({ open, initialPersona, onSave, onClose }: Props) {
  const [persona, setPersona] = useState(initialPersona)

  useEffect(() => {
    if (open) setPersona(initialPersona)
  }, [open, initialPersona])

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-2xl shadow-2xl">
        <div className="p-5 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">编辑人格</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            保存后新消息将使用新人格，历史聊天记录不变。
          </p>
        </div>
        <div className="p-5">
          <textarea
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            className="w-full h-56 p-4 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
        <div className="p-5 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            取消
          </button>
          <button
            onClick={() => onSave(persona)}
            className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium transition-colors"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  )
}
