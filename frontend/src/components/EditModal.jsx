import { useState } from 'react'

// V6.1: 编辑弹窗（从 KnowledgeSpace 抽出，供知识管理面板与全屏知识页共用）
export default function EditModal({ card, spaces, onSave, onClose }) {
  const [title, setTitle] = useState(card.title)
  const [spaceId, setSpaceId] = useState(card.space_id ? String(card.space_id) : '')
  const [tagsStr, setTagsStr] = useState((card.tags || []).join(', '))
  const [important, setImportant] = useState(card.importance === 'high')

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave({
      title,
      space_id: spaceId ? Number(spaceId) : null,
      tags: tagsStr.split(',').map((t) => t.trim()).filter(Boolean),
      importance: important ? 'high' : null,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl p-6 w-96 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-neutral-900 mb-4">编辑知识卡片</h3>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="text-xs text-neutral-600 mb-1 block">标题</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-300"
            />
          </div>
          <div>
            <label className="text-xs text-neutral-600 mb-1 block">知识空间</label>
            <select
              value={spaceId}
              onChange={(e) => setSpaceId(e.target.value)}
              className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-300 bg-white"
            >
              <option value="">未分类</option>
              {spaces.map((sp) => (
                <option key={sp.id} value={sp.id}>{sp.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-neutral-600 mb-1 block">标签（逗号分隔）</label>
            <input
              value={tagsStr}
              onChange={(e) => setTagsStr(e.target.value)}
              className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-300"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={important}
              onChange={(e) => setImportant(e.target.checked)}
              className="accent-neutral-900 w-4 h-4"
            />
            <span className="text-sm text-neutral-700">标记为重要</span>
          </label>
          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 text-sm border border-neutral-200 text-neutral-700 rounded-lg hover:bg-neutral-50"
            >
              取消
            </button>
            <button
              type="submit"
              className="flex-1 py-2 text-sm bg-neutral-900 text-white rounded-lg hover:bg-neutral-800"
            >
              保存
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
