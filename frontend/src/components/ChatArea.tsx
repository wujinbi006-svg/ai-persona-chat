import { useState } from 'react'
import type { Conversation, Character, Message, Speaker } from '../types'
import MessageList from './MessageList'
import MessageInput from './MessageInput'
import CharacterModal from './CharacterModal'
import DiscussionModal from './DiscussionModal'

interface Props {
  conversation: Conversation
  characters: Character[]
  messages: Message[]
  streamingContent: string
  streamingCharacter: { id: number; name: string } | null
  isGenerating: boolean
  error: string | null
  speaker: Speaker
  onSpeakerChange: (s: Speaker) => void
  onSendUser: (msg: string) => void
  onGenerateCharacter: (charId: number) => void
  onReplyAll: () => void
  onStartDiscussion: (charIds: number[], rounds: number) => void
  onStop: () => void
  onAddCharacter: (name: string, persona: string) => void
  onEditCharacter: (id: number, name: string, persona: string) => void
  onDeleteCharacter: (id: number) => void
  onClearMessages: () => void
}

export default function ChatArea(props: Props) {
  const {
    conversation, characters, messages, streamingContent, streamingCharacter,
    isGenerating, error, speaker, onSpeakerChange, onSendUser, onGenerateCharacter,
    onReplyAll, onStartDiscussion, onStop, onAddCharacter, onEditCharacter,
    onDeleteCharacter, onClearMessages,
  } = props

  const [charModalOpen, setCharModalOpen] = useState(false)
  const [editingChar, setEditingChar] = useState<Character | null>(null)
  const [discussionOpen, setDiscussionOpen] = useState(false)
  const [clearConfirm, setClearConfirm] = useState(false)
  const [manageOpen, setManageOpen] = useState(false)

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-gray-950 min-w-0">
      {/* 顶部栏 */}
      <div className="border-b border-gray-200 dark:border-gray-700 px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
            {conversation.title}
          </div>
          <div className="flex items-center gap-1.5 mt-1 flex-wrap">
            {characters.map((c) => (
              <span key={c.id} className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                {c.name}
              </span>
            ))}
            {characters.length === 0 && (
              <span className="text-xs text-gray-400">暂无角色</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setManageOpen(!manageOpen)}
            className="px-3 py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700"
          >
            角色管理
          </button>
          <button
            onClick={() => setClearConfirm(true)}
            className="px-3 py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 border border-gray-200 dark:border-gray-700"
          >
            清空
          </button>
        </div>
      </div>

      {/* 角色管理展开面板 */}
      {manageOpen && (
        <div className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 px-4 py-3">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-500 dark:text-gray-400">角色列表</span>
              <button
                onClick={() => { setEditingChar(null); setCharModalOpen(true) }}
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                + 添加角色
              </button>
            </div>
            <div className="space-y-1.5">
              {characters.map((c) => (
                <div key={c.id} className="flex items-center gap-2 p-2 bg-white dark:bg-gray-800 rounded-lg">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-16 shrink-0">{c.name}</span>
                  <span className="text-xs text-gray-400 flex-1 truncate">{c.persona.slice(0, 50)}…</span>
                  <button
                    onClick={() => { setEditingChar(c); setCharModalOpen(true) }}
                    className="text-xs text-gray-500 hover:text-indigo-600 px-2"
                  >
                    编辑
                  </button>
                  <button
                    onClick={() => onDeleteCharacter(c.id)}
                    className="text-xs text-gray-500 hover:text-red-600 px-2"
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 消息列表 */}
      <MessageList
        messages={messages}
        characters={characters}
        streamingContent={streamingContent}
        streamingCharacter={streamingCharacter}
        isGenerating={isGenerating}
        error={error}
      />

      {/* 输入区 */}
      <MessageInput
        characters={characters}
        speaker={speaker}
        onSpeakerChange={onSpeakerChange}
        onSendUser={onSendUser}
        onGenerateCharacter={onGenerateCharacter}
        onReplyAll={onReplyAll}
        onOpenDiscussion={() => setDiscussionOpen(true)}
        onStop={onStop}
        isGenerating={isGenerating}
      />

      {/* 角色编辑弹窗 */}
      <CharacterModal
        open={charModalOpen}
        character={editingChar}
        onSave={(name, persona) => {
          if (editingChar) onEditCharacter(editingChar.id, name, persona)
          else onAddCharacter(name, persona)
          setCharModalOpen(false)
          setEditingChar(null)
        }}
        onClose={() => { setCharModalOpen(false); setEditingChar(null) }}
      />

      {/* 讨论设置弹窗 */}
      <DiscussionModal
        open={discussionOpen}
        characters={characters}
        onStart={(ids, rounds) => {
          onStartDiscussion(ids, rounds)
          setDiscussionOpen(false)
        }}
        onClose={() => setDiscussionOpen(false)}
      />

      {/* 清空确认 */}
      {clearConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setClearConfirm(false)}>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-5 max-w-sm" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-2">确认清空聊天？</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">将删除当前会话所有消息，角色和人格保留。</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setClearConfirm(false)} className="px-4 py-2 text-sm text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">取消</button>
              <button onClick={() => { onClearMessages(); setClearConfirm(false) }} className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700">确认清空</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
