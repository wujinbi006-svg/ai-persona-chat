import { useState } from 'react'
import type { Character } from '../types'
import CharacterModal from './CharacterModal'

interface Props {
  conversationId: number
  characters: Character[]
  onAddCharacter: (name: string, persona: string) => void
  onEditCharacter: (id: number, name: string, persona: string) => void
  onDeleteCharacter: (id: number) => void
  onEnterChat: () => void
}

export default function CharacterSetup({
  conversationId,
  characters,
  onAddCharacter,
  onEditCharacter,
  onDeleteCharacter,
  onEnterChat,
}: Props) {
  const [modalOpen, setModalOpen] = useState(false)
  const [editingChar, setEditingChar] = useState<Character | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null)

  const handleSave = (name: string, persona: string) => {
    if (editingChar) {
      onEditCharacter(editingChar.id, name, persona)
    } else {
      onAddCharacter(name, persona)
    }
    setModalOpen(false)
    setEditingChar(null)
  }

  return (
    <div className="flex-1 flex flex-col items-center p-6 overflow-y-auto">
      <div className="w-full max-w-2xl">
        <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 mb-2 text-center">角色设置</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 text-center">
          添加一个或多个 AI 角色，每个角色有独立人格，共享同一个聊天室。
        </p>

        {/* 角色列表 */}
        <div className="space-y-3 mb-6">
          {characters.length === 0 && (
            <div className="text-center py-12 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
              <p className="text-gray-400 dark:text-gray-500 text-sm">暂无角色，点击下方按钮添加</p>
            </div>
          )}
          {characters.map((c) => (
            <div key={c.id} className="flex items-center gap-3 p-4 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
              <div className="w-10 h-10 rounded-full bg-indigo-500 text-white flex items-center justify-center font-bold text-sm shrink-0">
                {c.name.charAt(0)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-gray-800 dark:text-gray-100 text-sm">{c.name}</div>
                <div className="text-xs text-gray-400 dark:text-gray-500 truncate">{c.persona.slice(0, 60)}…</div>
              </div>
              <div className="flex gap-1 shrink-0">
                <button
                  onClick={() => { setEditingChar(c); setModalOpen(true) }}
                  className="px-2.5 py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                >
                  编辑
                </button>
                <button
                  onClick={() => setDeleteConfirm(c.id)}
                  className="px-2.5 py-1.5 rounded-lg text-xs text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                >
                  删除
                </button>
              </div>
              {deleteConfirm === c.id && (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setDeleteConfirm(null)}>
                  <div className="bg-white dark:bg-gray-800 rounded-xl p-5 max-w-sm" onClick={(e) => e.stopPropagation()}>
                    <p className="text-sm text-gray-800 dark:text-gray-100 mb-4">删除角色"{c.name}"？历史消息会保留。</p>
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setDeleteConfirm(null)} className="px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">取消</button>
                      <button onClick={() => { onDeleteCharacter(c.id); setDeleteConfirm(null) }} className="px-3 py-1.5 text-xs bg-red-600 text-white rounded-lg hover:bg-red-700">删除</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-3">
          <button
            onClick={() => { setEditingChar(null); setModalOpen(true) }}
            className="flex-1 py-2.5 rounded-lg border border-indigo-300 dark:border-indigo-700 text-indigo-600 dark:text-indigo-400 text-sm font-medium hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
          >
            + 添加 AI 角色
          </button>
          <button
            onClick={onEnterChat}
            disabled={characters.length === 0}
            className="flex-1 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
          >
            进入聊天
          </button>
        </div>
      </div>

      <CharacterModal
        open={modalOpen}
        character={editingChar}
        onSave={handleSave}
        onClose={() => { setModalOpen(false); setEditingChar(null) }}
      />
    </div>
  )
}
