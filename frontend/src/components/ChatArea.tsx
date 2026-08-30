import { useState } from 'react'
import type { Conversation, Character, Message, Speaker, ChatMode } from '../types'
import MessageList from './MessageList'
import MessageInput from './MessageInput'
import CharacterModal from './CharacterModal'
import DiscussionModal from './DiscussionModal'
import DramaModal from './DramaModal'
import MemoryPanel from './MemoryPanel'

interface Props {
  conversation: Conversation
  characters: Character[]
  messages: Message[]
  streamingContent: string
  streamingCharacter: { id: number; name: string } | null
  isGenerating: boolean
  error: string | null
  speaker: Speaker
  mode: ChatMode
  isDramaActive: boolean
  dramaRound: number
  onSpeakerChange: (s: Speaker) => void
  onModeChange: (m: ChatMode) => void
  onSendUser: (msg: string) => void
  onGenerateCharacter: (charId: number) => void
  onReplyAll: () => void
  onStartDiscussion: (charIds: number[], rounds: number) => void
  onStartDrama: (charIds: number[], rounds: number, interval: number, scene: string, sceneTime: string, sceneContext: string) => void
  onDramaPause: () => void
  onDramaResume: () => void
  onDramaStop: () => void
  onDramaInterject: (message: string) => void
  onStop: () => void
  onAddCharacter: (name: string, persona: string) => void
  onEditCharacter: (id: number, name: string, persona: string) => void
  onDeleteCharacter: (id: number) => void
  onMoveCharacter: (id: number, direction: 'up' | 'down') => void
  onUpdateScene: (scene: string, sceneTime: string, sceneContext: string) => void
  onClearMessages: () => void
  imageGeneratingCharacter: { id: number; name: string } | null
}

export default function ChatArea(props: Props) {
  const {
    conversation, characters, messages, streamingContent, streamingCharacter,
    isGenerating, error, speaker, mode, isDramaActive, dramaRound,
    onSpeakerChange, onModeChange, onSendUser, onGenerateCharacter,
    onReplyAll, onStartDiscussion, onStartDrama, onDramaPause, onDramaResume,
    onDramaStop, onDramaInterject, onStop, onAddCharacter, onEditCharacter,
    onDeleteCharacter, onMoveCharacter, onUpdateScene, onClearMessages,
    imageGeneratingCharacter,
  } = props

  const [charModalOpen, setCharModalOpen] = useState(false)
  const [editingChar, setEditingChar] = useState<Character | null>(null)
  const [discussionOpen, setDiscussionOpen] = useState(false)
  const [dramaOpen, setDramaOpen] = useState(false)
  const [clearConfirm, setClearConfirm] = useState(false)
  const [manageOpen, setManageOpen] = useState(false)
  const [memoryChar, setMemoryChar] = useState<Character | null>(null)
  const [sceneOpen, setSceneOpen] = useState(false)
  const [sceneInput, setSceneInput] = useState(conversation.scene || '')
  const [sceneTimeInput, setSceneTimeInput] = useState(conversation.scene_time || '')
  const [sceneContextInput, setSceneContextInput] = useState(conversation.scene_context || '')

  const handleSaveScene = () => {
    onUpdateScene(sceneInput, sceneTimeInput, sceneContextInput)
    setSceneOpen(false)
  }

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
            {(conversation.scene || conversation.scene_time) && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 dark:bg-purple-900/20 text-purple-600 dark:text-purple-400">
                📍 {conversation.scene}{conversation.scene_time ? ` · ${conversation.scene_time}` : ''}
              </span>
            )}
            {isDramaActive && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-purple-600 text-white animate-pulse">
                🎭 戏剧进行中 · 第{dramaRound}轮
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setSceneOpen(!sceneOpen)}
            className="px-3 py-1.5 rounded-lg text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700"
          >
            📍 场景
          </button>
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

      {/* 场景编辑面板 */}
      {sceneOpen && (
        <div className="border-b border-gray-200 dark:border-gray-700 bg-purple-50/50 dark:bg-purple-900/10 px-4 py-3">
          <div className="max-w-3xl mx-auto space-y-2">
            <div className="text-xs font-medium text-purple-600 dark:text-purple-400">场景设置（基础叙事）</div>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="text"
                value={sceneInput}
                onChange={(e) => setSceneInput(e.target.value)}
                placeholder="地点"
                className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <input
                type="text"
                value={sceneTimeInput}
                onChange={(e) => setSceneTimeInput(e.target.value)}
                placeholder="时间/天气"
                className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <input
              type="text"
              value={sceneContextInput}
              onChange={(e) => setSceneContextInput(e.target.value)}
              placeholder="背景/环境描述"
              className="w-full px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <div className="flex justify-end">
              <button onClick={handleSaveScene} className="px-3 py-1 rounded-lg bg-purple-600 text-white text-xs hover:bg-purple-700">保存场景</button>
            </div>
          </div>
        </div>
      )}

      {/* 角色管理展开面板 */}
      {manageOpen && (
        <div className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 px-4 py-3">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-500 dark:text-gray-400">角色列表（↑↓调整顺序）</span>
              <button
                onClick={() => { setEditingChar(null); setCharModalOpen(true) }}
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
              >
                + 添加角色
              </button>
            </div>
            <div className="space-y-1.5">
              {characters.map((c, idx) => (
                <div key={c.id} className="flex items-center gap-2 p-2 bg-white dark:bg-gray-800 rounded-lg">
                  <div className="flex flex-col gap-0.5 shrink-0">
                    <button
                      onClick={() => onMoveCharacter(c.id, 'up')}
                      disabled={idx === 0}
                      className="text-xs text-gray-400 hover:text-indigo-600 disabled:opacity-30 px-1"
                    >
                      ↑
                    </button>
                    <button
                      onClick={() => onMoveCharacter(c.id, 'down')}
                      disabled={idx === characters.length - 1}
                      className="text-xs text-gray-400 hover:text-indigo-600 disabled:opacity-30 px-1"
                    >
                      ↓
                    </button>
                  </div>
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-16 shrink-0">{c.name}</span>
                  <span className="text-xs text-gray-400 flex-1 truncate">{c.persona.slice(0, 50)}…</span>
                  <button
                    onClick={() => setMemoryChar(c)}
                    className="text-xs text-purple-500 hover:text-purple-700 px-2"
                  >
                    🧠 记忆
                  </button>
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

      {/* 戏剧模式控制条 */}
      {isDramaActive && (
        <div className="border-b border-purple-200 dark:border-purple-800 bg-purple-50 dark:bg-purple-900/20 px-4 py-2">
          <div className="max-w-3xl mx-auto flex items-center justify-between">
            <span className="text-xs text-purple-700 dark:text-purple-300">🎭 戏剧模式进行中 · 第{dramaRound}轮 · 可输入消息插话</span>
            <div className="flex gap-2">
              <button onClick={onDramaPause} className="px-2 py-1 text-xs bg-yellow-500 text-white rounded hover:bg-yellow-600">⏸ 暂停</button>
              <button onClick={onDramaResume} className="px-2 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600">▶ 继续</button>
              <button onClick={onDramaStop} className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700">⏹ 停止</button>
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
        imageGeneratingCharacter={imageGeneratingCharacter}
      />

      {/* 输入区 */}
      <MessageInput
        characters={characters}
        speaker={speaker}
        mode={mode}
        onSpeakerChange={onSpeakerChange}
        onModeChange={onModeChange}
        onSendUser={onSendUser}
        onGenerateCharacter={onGenerateCharacter}
        onReplyAll={onReplyAll}
        onOpenDiscussion={() => setDiscussionOpen(true)}
        onOpenDrama={() => setDramaOpen(true)}
        onStop={onStop}
        isGenerating={isGenerating}
        isDramaActive={isDramaActive}
        onDramaInterject={onDramaInterject}
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

      {/* 戏剧模式设置弹窗 */}
      <DramaModal
        open={dramaOpen}
        characters={characters}
        scene={conversation.scene || ''}
        sceneTime={conversation.scene_time || ''}
        sceneContext={conversation.scene_context || ''}
        onStart={onStartDrama}
        onClose={() => setDramaOpen(false)}
      />

      {/* 记忆面板 */}
      {memoryChar && (
        <MemoryPanel character={memoryChar} onClose={() => setMemoryChar(null)} />
      )}

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
