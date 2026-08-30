import { useState } from 'react'
import type { Character } from '../types'

interface Props {
  open: boolean
  characters: Character[]
  scene: string
  sceneTime: string
  sceneContext: string
  onStart: (charIds: number[], rounds: number, interval: number, scene: string, sceneTime: string, sceneContext: string) => void
  onClose: () => void
}

export default function DramaModal({ open, characters, scene, sceneTime, sceneContext, onStart, onClose }: Props) {
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [rounds, setRounds] = useState(3)
  const [interval, setInterval] = useState(1)
  const [localScene, setLocalScene] = useState(scene)
  const [localSceneTime, setLocalSceneTime] = useState(sceneTime)
  const [localSceneContext, setLocalSceneContext] = useState(sceneContext)

  if (!open) return null

  const toggleChar = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const handleStart = () => {
    if (selectedIds.length === 0) return
    onStart(selectedIds, rounds, interval, localScene, localSceneTime, localSceneContext)
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-xl p-5 max-w-lg w-full max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">🎭 戏剧模式</h3>

        {/* 场景设置 */}
        <div className="space-y-3 mb-4">
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400">场景设置</div>
          <input
            type="text"
            value={localScene}
            onChange={(e) => setLocalScene(e.target.value)}
            placeholder="地点（如：咖啡馆、公园、教室）"
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <input
            type="text"
            value={localSceneTime}
            onChange={(e) => setLocalSceneTime(e.target.value)}
            placeholder="时间（如：下午3点、夜晚、雨天）"
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <textarea
            value={localSceneContext}
            onChange={(e) => setLocalSceneContext(e.target.value)}
            placeholder="背景/天气/环境描述（可选）"
            rows={2}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
          />
        </div>

        {/* 参与角色 */}
        <div className="mb-4">
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">参与角色（按选择顺序发言）</div>
          <div className="flex flex-wrap gap-2">
            {characters.map((c) => (
              <button
                key={c.id}
                onClick={() => toggleChar(c.id)}
                className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                  selectedIds.includes(c.id)
                    ? 'bg-purple-600 text-white border-purple-600'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                {c.name}
              </button>
            ))}
          </div>
        </div>

        {/* 轮数和间隔 */}
        <div className="grid grid-cols-2 gap-4 mb-5">
          <div>
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400 block mb-1">轮数</label>
            <select
              value={rounds}
              onChange={(e) => setRounds(Number(e.target.value))}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              {[1, 3, 5, 10, 20].map((r) => (
                <option key={r} value={r}>{r} 轮</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400 block mb-1">发言间隔</label>
            <select
              value={interval}
              onChange={(e) => setInterval(Number(e.target.value))}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              {[0, 1, 3, 5, 10].map((s) => (
                <option key={s} value={s}>{s === 0 ? '无间隔' : `${s} 秒`}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">取消</button>
          <button
            onClick={handleStart}
            disabled={selectedIds.length === 0}
            className="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed font-medium"
          >
            开始戏剧
          </button>
        </div>
      </div>
    </div>
  )
}
