import { useState, useEffect } from 'react'
import type { Character, Memory } from '../types'
import { api } from '../services/api'

interface Props {
  character: Character
  onClose: () => void
}

const TYPE_LABELS: Record<string, string> = {
  user: '用户信息',
  character: '角色信息',
  relationship: '关系',
  event: '事件',
  preference: '偏好',
  fact: '事实',
}

export default function MemoryPanel({ character, onClose }: Props) {
  const [memories, setMemories] = useState<Memory[]>([])
  const [loading, setLoading] = useState(true)
  const [newContent, setNewContent] = useState('')
  const [newType, setNewType] = useState('fact')
  const [newImportance, setNewImportance] = useState(3)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editContent, setEditContent] = useState('')

  const loadMemories = async () => {
    setLoading(true)
    try {
      const list = await api.listCharacterMemories(character.id)
      setMemories(list)
    } catch (e) {
      console.error('加载记忆失败', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadMemories()
  }, [character.id])

  const handleAdd = async () => {
    if (!newContent.trim()) return
    try {
      await api.createCharacterMemory(character.id, {
        content: newContent.trim(),
        memory_type: newType,
        importance: newImportance,
      })
      setNewContent('')
      await loadMemories()
    } catch (e) {
      console.error('添加记忆失败', e)
    }
  }

  const handleToggleActive = async (mem: Memory) => {
    try {
      await api.updateMemory(mem.id, { is_active: !mem.is_active })
      await loadMemories()
    } catch (e) {
      console.error('更新记忆失败', e)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await api.deleteMemory(id)
      await loadMemories()
    } catch (e) {
      console.error('删除记忆失败', e)
    }
  }

  const handleSaveEdit = async (id: number) => {
    if (!editContent.trim()) return
    try {
      await api.updateMemory(id, { content: editContent.trim() })
      setEditingId(null)
      await loadMemories()
    } catch (e) {
      console.error('保存记忆失败', e)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-gray-800 rounded-xl p-5 max-w-2xl w-full max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">🧠 {character.name} 的记忆</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 text-xl">×</button>
        </div>

        {/* 添加记忆 */}
        <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg space-y-2">
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="输入记忆内容…"
            rows={2}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
          />
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={newType}
              onChange={(e) => setNewType(e.target.value)}
              className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-xs text-gray-700 dark:text-gray-300"
            >
              {Object.entries(TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <select
              value={newImportance}
              onChange={(e) => setNewImportance(Number(e.target.value))}
              className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-xs text-gray-700 dark:text-gray-300"
            >
              {[1, 2, 3, 4, 5].map((i) => (
                <option key={i} value={i}>重要性 {i}</option>
              ))}
            </select>
            <button
              onClick={handleAdd}
              disabled={!newContent.trim()}
              className="px-3 py-1 rounded bg-indigo-600 text-white text-xs hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              + 添加
            </button>
          </div>
        </div>

        {/* 记忆列表 */}
        <div className="flex-1 overflow-y-auto space-y-2">
          {loading && <div className="text-center text-gray-400 text-sm py-8">加载中…</div>}
          {!loading && memories.length === 0 && (
            <div className="text-center text-gray-400 text-sm py-8">暂无记忆，系统会在对话中自动提取，也可以手动添加。</div>
          )}
          {memories.map((mem) => (
            <div
              key={mem.id}
              className={`p-3 rounded-lg border ${mem.is_active ? 'bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600' : 'bg-gray-50 dark:bg-gray-800 border-gray-100 dark:border-gray-700 opacity-60'}`}
            >
              {editingId === mem.id ? (
                <div className="space-y-2">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={2}
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                  />
                  <div className="flex gap-2">
                    <button onClick={() => handleSaveEdit(mem.id)} className="px-2 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700">保存</button>
                    <button onClick={() => setEditingId(null)} className="px-2 py-1 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-600 rounded">取消</button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-1">
                        <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400">
                          {TYPE_LABELS[mem.memory_type] || mem.memory_type}
                        </span>
                        <span className="text-xs text-gray-400">{'★'.repeat(mem.importance)}</span>
                      </div>
                      <p className="text-sm text-gray-700 dark:text-gray-300 break-words">{mem.content}</p>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button
                        onClick={() => { setEditingId(mem.id); setEditContent(mem.content) }}
                        className="text-xs text-gray-400 hover:text-indigo-600 px-1"
                      >
                        编辑
                      </button>
                      <button
                        onClick={() => handleToggleActive(mem)}
                        className="text-xs text-gray-400 hover:text-yellow-600 px-1"
                      >
                        {mem.is_active ? '停用' : '恢复'}
                      </button>
                      <button
                        onClick={() => handleDelete(mem.id)}
                        className="text-xs text-gray-400 hover:text-red-600 px-1"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
