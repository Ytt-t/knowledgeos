import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { getCard, listSpaces, updateCard, deleteCard, redistillCard } from '../api'
import CardContent from '../components/CardContent'
import EditModal from '../components/EditModal'

// V6.1: 全屏知识阅读页 /card/:cardId（捕获保存后直达，Notion 文章式居中排版）
export default function CardPage() {
  const { cardId } = useParams()
  const navigate = useNavigate()
  const [card, setCard] = useState(null)
  const [spaces, setSpaces] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [redistilling, setRedistilling] = useState(false)

  const handleRedistill = async () => {
    if (redistilling) return
    setRedistilling(true)
    try {
      const updated = await redistillCard(card.id)
      setCard(updated)
    } catch (e) {
      alert(e?.response?.data?.detail || '重新总结失败，请重试')
    } finally {
      setRedistilling(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    setCard(null)
    Promise.all([
      getCard(Number(cardId)).catch((e) => null),
      listSpaces().then((d) => d.spaces || []).catch(() => []),
    ]).then(([c, sps]) => {
      if (cancelled) return
      if (!c) {
        setError('卡片不存在或已删除')
      } else {
        setCard(c)
      }
      setSpaces(sps)
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [cardId])

  const handleSave = async (data) => {
    const updated = await updateCard(card.id, data)
    setCard(updated)
    setEditing(false)
  }

  const handleDelete = async () => {
    if (!confirm('确认删除这张知识卡片？')) return
    await deleteCard(card.id)
    navigate('/space')
  }

  if (loading) {
    return (
      <div className="max-w-[720px] mx-auto space-y-6">
        <div className="h-8 w-2/3 skeleton rounded-lg" />
        <div className="h-4 w-40 skeleton rounded" />
        <div className="h-40 skeleton rounded-xl" />
        <div className="h-24 skeleton rounded-xl" />
      </div>
    )
  }

  if (error || !card) {
    return (
      <div className="max-w-[720px] mx-auto text-center py-20">
        <p className="text-sm text-neutral-400 mb-4">{error || '卡片不存在'}</p>
        <button
          onClick={() => navigate('/space')}
          className="text-xs text-neutral-600 hover:text-neutral-900 underline underline-offset-2"
        >
          ← 返回知识管理
        </button>
      </div>
    )
  }

  return (
    <div>
      {/* 顶部操作栏 */}
      <div className="max-w-[720px] mx-auto flex items-center justify-between mb-8">
        <button
          onClick={() => navigate('/space')}
          className="text-sm text-neutral-400 hover:text-neutral-700 transition-colors"
        >
          ← 返回知识管理
        </button>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setEditing(true)}
            className="p-1.5 text-neutral-400 hover:text-neutral-700 rounded hover:bg-neutral-50 transition"
            title="编辑"
          >
            ✎
          </button>
          <button
            onClick={() => updateCard(card.id, { is_favorite: !card.is_favorite }).then((c) => setCard(c))}
            className={`p-1.5 rounded hover:bg-neutral-50 transition ${card.is_favorite ? 'text-neutral-900' : 'text-neutral-400 hover:text-neutral-900'}`}
            title="收藏"
          >
            ☆
          </button>
          {card.source_url && (
            <a
              href={card.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 text-neutral-400 hover:text-neutral-700 rounded hover:bg-neutral-50 transition"
              title="打开原始链接"
            >
              ↗
            </a>
          )}
          <button
            onClick={handleDelete}
            className="p-1.5 text-neutral-400 hover:text-red-500 rounded hover:bg-neutral-50 transition"
            title="删除"
          >
            🗑
          </button>
        </div>
      </div>

      {/* 正文（全屏居中阅读） */}
      <div className="max-w-[720px] mx-auto">
        <CardContent
          card={card}
          spaces={spaces}
          onCardChange={(next) => setCard(next)}
          onOpenCard={(id) => navigate(`/card/${id}`)}
          onRedistill={handleRedistill}
          redistilling={redistilling}
        />

        {/* V6.2: 学以致用 —— 单卡复习入口 */}
        <div className="mt-10 pt-6 border-t border-neutral-100 flex items-center justify-between">
          <span className="text-xs text-neutral-400">读完就练，记得更牢</span>
          <button
            onClick={() => navigate('/review', { state: { scopeType: 'cards', cardIds: [card.id] } })}
            className="px-4 py-2 bg-neutral-900 text-white rounded-lg text-xs font-medium hover:bg-neutral-800 transition-colors"
          >
            复习这张卡 →
          </button>
        </div>
      </div>

      {/* 编辑弹窗 */}
      {editing && (
        <EditModal
          card={card}
          spaces={spaces}
          onSave={handleSave}
          onClose={() => setEditing(false)}
        />
      )}
    </div>
  )
}
