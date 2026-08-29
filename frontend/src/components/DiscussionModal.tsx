import { useState } from 'react'
import type { Character } from '../types'

interface Props {
  open: boolean
  characters: Character[]
  onStart: (characterIds: number[], rounds: number) => void
  onClose: () => void
}

const ROUND_OPTIONS = [1, 3, 5, 10, 20]

export default function DiscussionModal({ open, characters, onStart, onClose }: Props) {
  const [selected, setSelected] = useState<number[]>([])
  const [rounds, setRounds] = useState(5)

  if (!open) return null

  const toggle = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md shadow-2xl">
        <div className="p-5 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">AI 自由讨论</h2>
        </div>
        <div className="p-5 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">参与角色</label>
            <div className="space-y-2">
              {characters.map((c) => (
                <label key={c.id} className="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
                  <input
                    type="checkbox"
                    checked={selected.includes(c.id)}
                    onChange={() => toggle(c.id)}
                    className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-sm text-gray-800 dark:text-gray-100">{c.name}</span>
                </label>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">讨论轮数</label>
            <div className="flex gap-2">
              {ROUND_OPTIONS.map((r) => (
                <button
                  key={r}
                  onClick={() => setRounds(r)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    rounds === r
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="p-5 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700">取消</button>
          <button
            onClick={() => selected.length > 0 && onStart(selected, rounds)}
            disabled={selected.length === 0}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-sm font-medium"
          >
            开始讨论
          </button>
        </div>
      </div>
    </div>
  )
}
