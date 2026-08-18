import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  listCards,
  getCard,
  updateCard,
  deleteCard,
  redistillCard,
  listSpaces,
  createSpace,
  updateSpace,
  deleteSpace,
} from '../api'
import { CONTENT_TYPE_LABEL } from '../utils/status'
import CardContent from '../components/CardContent'
import EditModal from '../components/EditModal'

export default function KnowledgeSpace() {
  const navigate = useNavigate()
  const [cards, setCards] = useState([])
  const [spaces, setSpaces] = useState([])
  const [unclassifiedCount, setUnclassifiedCount] = useState(0)
  // filterType: all | favorite | archived | unclassified | space
  const [filterType, setFilterType] = useState('all')
  const [filterSpaceId, setFilterSpaceId] = useState(null)
  const [selectedCard, setSelectedCard] = useState(null)
  const [editing, setEditing] = useState(null)
  const [viewMode, setViewMode] = useState('grid') // grid | list
  const [search, setSearch] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  // V6: 分类栏折叠 + 空间管理
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem('kos_space_sidebar') === '1'
  )
  const [newSpaceName, setNewSpaceName] = useState('')
  const [creatingSpace, setCreatingSpace] = useState(false)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')

  const load = () => {
    const params = {}
    if (filterType === 'favorite') params.favorite = true
    if (filterType === 'archived') params.archived = true
    if (filterType === 'unclassified') params.unclassified = true
    if (filterType === 'space' && filterSpaceId) params.space_id = filterSpaceId
    listCards(params).then((data) => {
      const filtered = search
        ? data.filter((c) =>
            c.title.toLowerCase().includes(search.toLowerCase()) ||
            (c.tags || []).some((t) => t.toLowerCase().includes(search.toLowerCase()))
          )
        : data
      setCards(filtered)
    }).catch(() => {})
    listSpaces().then((d) => {
      setSpaces(d.spaces || [])
      setUnclassifiedCount(d.unclassified_count || 0)
    }).catch(() => {})
  }

  useEffect(() => {
    load()
  }, [filterType, filterSpaceId, search, refreshKey])

  const handleUpdate = async (id, data) => {
    await updateCard(id, data)
    setEditing(null)
    load()
    if (selectedCard?.id === id) setSelectedCard(await getCard(id))
  }

  const handleDelete = async (id) => {
    if (!confirm('确认删除这张知识卡片？')) return
    await deleteCard(id)
    setSelectedCard(null)
    load()
  }

  const handleToggleSidebar = () => {
    const next = !sidebarCollapsed
    setSidebarCollapsed(next)
    localStorage.setItem('kos_space_sidebar', next ? '1' : '0')
  }

  // === 空间管理 ===
  const handleCreateSpace = async () => {
    const name = newSpaceName.trim()
    if (!name || creatingSpace) return
    setCreatingSpace(true)
    try {
      await createSpace(name)
      setNewSpaceName('')
      load()
    } catch (e) {
      alert(e?.response?.data?.detail || '创建失败')
    } finally {
      setCreatingSpace(false)
    }
  }

  const handleRenameSubmit = async (spaceId) => {
    const name = renameValue.trim()
    if (!name) { setRenamingId(null); return }
    try {
      await updateSpace(spaceId, { name })
      load()
    } catch (e) {
      alert(e?.response?.data?.detail || '重命名失败')
    }
    setRenamingId(null)
  }

  const handleDeleteSpace = async (sp) => {
    if (!confirm(`删除空间「${sp.name}」？该空间下 ${sp.card_count} 张卡片将变为未分类（不会删除卡片）。`)) return
    try {
      await deleteSpace(sp.id)
      if (filterType === 'space' && filterSpaceId === sp.id) {
        setFilterType('all'); setFilterSpaceId(null)
      }
      load()
    } catch (e) {
      alert(e?.response?.data?.detail || '删除失败')
    }
  }

  return (
    <div className="flex gap-8">
      {/* 左侧分类栏（V6: 可折叠 + 空间管理） */}
      {sidebarCollapsed ? (
        <button
          onClick={handleToggleSidebar}
          title="展开分类栏"
          className="w-8 shrink-0 self-start text-neutral-400 hover:text-neutral-900 text-sm mt-1"
        >
          ⇥
        </button>
      ) : (
        <aside className="w-48 shrink-0">
          <div className="flex items-center justify-between mb-3">
            <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider">
              知识空间
            </div>
            <button
              onClick={handleToggleSidebar}
              title="折叠分类栏"
              className="text-neutral-300 hover:text-neutral-600 text-xs"
            >
              ⇤
            </button>
          </div>
          <div className="space-y-0.5">
            <FilterItem
              active={filterType === 'all'}
              onClick={() => { setFilterType('all'); setFilterSpaceId(null) }}
              label="全部知识"
              count={cards.length}
            />
            <FilterItem
              active={filterType === 'favorite'}
              onClick={() => { setFilterType('favorite'); setFilterSpaceId(null) }}
              label="★ 已收藏"
            />
            <FilterItem
              active={filterType === 'unclassified'}
              onClick={() => { setFilterType('unclassified'); setFilterSpaceId(null) }}
              label="未分类"
              count={unclassifiedCount}
            />
          </div>

          <div className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mt-6 mb-3">
            我的空间
          </div>
          <div className="space-y-0.5">
            {spaces.map((sp) =>
              renamingId === sp.id ? (
                <div key={sp.id} className="px-2 py-1">
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameSubmit(sp.id)
                      if (e.key === 'Escape') setRenamingId(null)
                    }}
                    onBlur={() => handleRenameSubmit(sp.id)}
                    className="w-full px-2 py-1 text-xs border border-neutral-300 rounded outline-none focus:border-neutral-500"
                  />
                </div>
              ) : (
                <div key={sp.id} className="group relative">
                  <FilterItem
                    active={filterType === 'space' && filterSpaceId === sp.id}
                    onClick={() => { setFilterType('space'); setFilterSpaceId(sp.id) }}
                    label={sp.name}
                    count={sp.card_count}
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 hidden group-hover:flex items-center gap-0.5 bg-white px-1">
                    <button
                      onClick={(e) => { e.stopPropagation(); setRenamingId(sp.id); setRenameValue(sp.name) }}
                      className="text-neutral-400 hover:text-neutral-900 text-[10px] px-0.5"
                      title="重命名"
                    >
                      ✎
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteSpace(sp) }}
                      className="text-neutral-400 hover:text-red-500 text-[10px] px-0.5"
                      title="删除空间"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              )
            )}
            {spaces.length === 0 && (
              <div className="text-xs text-neutral-400 px-3 py-1">还没有空间，点击下方新建</div>
            )}
          </div>

          {/* 新建空间 */}
          <div className="mt-3">
            <input
              value={newSpaceName}
              onChange={(e) => setNewSpaceName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreateSpace() }}
              placeholder="＋ 新建空间…"
              className="w-full px-2.5 py-1.5 text-xs border border-dashed border-neutral-200 rounded-md outline-none focus:border-neutral-400"
            />
          </div>
        </aside>
      )}

      {/* 主内容区 */}
      <section className="flex-1 min-w-0">
        {/* 顶部工具栏 */}
        <div className="flex items-center justify-between mb-5">
          {/* 搜索 */}
          <div className="relative flex-1 max-w-xs">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400 text-xs">⌕</span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索知识、标签、来源…"
              className="w-full pl-8 pr-3 py-2 border border-neutral-100 rounded-lg text-xs outline-none focus:border-neutral-200 bg-neutral-50/50"
            />
          </div>

          <div className="flex items-center gap-2">
            {/* 视图切换 */}
            <div className="flex border border-neutral-100 rounded-lg overflow-hidden">
              <button
                onClick={() => setViewMode('grid')}
                className={`px-2.5 py-1.5 text-xs transition-colors ${
                  viewMode === 'grid' ? 'bg-neutral-900 text-white' : 'text-neutral-500 hover:bg-neutral-50'
                }`}
              >
                ▦
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`px-2.5 py-1.5 text-xs transition-colors ${
                  viewMode === 'list' ? 'bg-neutral-900 text-white' : 'text-neutral-500 hover:bg-neutral-50'
                }`}
              >
                ☰
              </button>
            </div>
          </div>
        </div>

        {/* 卡片数量 */}
        <div className="text-xs text-neutral-400 mb-4">{cards.length} 张卡片</div>

        {/* 空状态 */}
        {cards.length === 0 ? (
          <div className="border border-dashed border-neutral-200 rounded-xl py-20 text-center text-neutral-400 text-sm">
            {filterType === 'archived' ? '暂无已归档卡片'
              : filterType === 'favorite' ? '暂无已收藏卡片'
              : filterType === 'unclassified' ? '没有未分类卡片，都整理好了'
              : '还没有知识卡片，去首页上传资料吧'}
          </div>
        ) : viewMode === 'grid' ? (
          /* 卡片网格（V6.2: hover 快捷操作，网格全宽） */
          <div className="grid grid-cols-3 gap-4">
            {cards.map((c) => (
              <CardGridItem
                key={c.id}
                card={c}
                active={selectedCard?.id === c.id}
                onClick={() => setSelectedCard(c)}
                onEdit={() => setEditing(c)}
                onDelete={() => handleDelete(c.id)}
                onFavorite={() => updateCard(c.id, { is_favorite: !c.is_favorite }).then(() => setRefreshKey((k) => k + 1))}
              />
            ))}
          </div>
        ) : (
          /* 列表视图 */
          <div className="space-y-1">
            {cards.map((c) => (
              <CardListItem
                key={c.id}
                card={c}
                active={selectedCard?.id === c.id}
                onClick={() => setSelectedCard(c)}
                onEdit={() => setEditing(c)}
                onDelete={() => handleDelete(c.id)}
                onFavorite={() => updateCard(c.id, { is_favorite: !c.is_favorite }).then(() => setRefreshKey((k) => k + 1))}
              />
            ))}
          </div>
        )}
      </section>

      {/* V6.2: 详情改为右侧抽屉（遮罩关闭，不占布局） */}
      {selectedCard && (
        <>
          <div
            className="fixed inset-0 bg-black/10 z-30"
            onClick={() => setSelectedCard(null)}
          />
          <CardDetail
            card={selectedCard}
            spaces={spaces}
            onEdit={() => setEditing(selectedCard)}
            onDelete={() => handleDelete(selectedCard.id)}
            onClose={() => setSelectedCard(null)}
            onCardChange={(next) => {
              setSelectedCard(next)
              setRefreshKey((k) => k + 1)
            }}
          />
        </>
      )}

      {/* 编辑弹窗 */}
      {editing && (
        <EditModal
          card={editing}
          spaces={spaces}
          onSave={(data) => handleUpdate(editing.id, data)}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

function FilterItem({ active, onClick, label, count }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-1.5 rounded-md text-xs transition flex items-center justify-between ${
        active ? 'bg-neutral-100 text-neutral-900 font-medium' : 'text-neutral-600 hover:text-neutral-900 hover:bg-neutral-50'
      }`}
    >
      <span className="truncate">{label}</span>
      {count !== undefined && <span className="text-neutral-400 text-[10px] shrink-0">{count}</span>}
    </button>
  )
}

// === 卡片网格项（V6.2: hover 右上角快捷操作） ===
function CardGridItem({ card, active, onClick, onEdit, onDelete, onFavorite }) {
  const subtitle = card.one_liner || (card.ai_summary?.summary || '').slice(0, 60)
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } }}
      className={`text-left bg-white border rounded-xl overflow-hidden transition-all group relative cursor-pointer ${
        active ? 'border-neutral-300 ring-2 ring-neutral-200' : 'border-neutral-100 hover:border-neutral-200 hover:shadow-sm'
      }`}
    >
      <div className="p-3.5">
        {/* 收藏标记 + 学习状态 */}
        <div className="absolute top-2.5 right-2.5 flex items-center gap-1">
          {card.learning_status === 'mastered' && (
            <span className="text-[10px] px-1 py-0.5 bg-neutral-900 text-white rounded">已掌握</span>
          )}
          {card.learning_status === 'learning' && (
            <span className="text-[10px] px-1 py-0.5 bg-neutral-200 text-neutral-600 rounded">学习中</span>
          )}
          {card.is_favorite && (
            <span className="text-neutral-900 text-xs">★</span>
          )}
        </div>
        {/* V6.2: hover 快捷操作（编辑/收藏/删除） */}
        <div className="absolute top-2.5 right-2.5 hidden group-hover:flex items-center gap-0.5 bg-white/90 backdrop-blur border border-neutral-100 rounded-lg px-1 py-0.5 shadow-sm">
          <button
            onClick={(e) => { e.stopPropagation(); onEdit() }}
            className="p-1 text-neutral-400 hover:text-neutral-900 rounded text-xs"
            title="编辑"
          >
            ✎
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onFavorite() }}
            className="p-1 text-neutral-400 hover:text-neutral-900 rounded text-xs"
            title={card.is_favorite ? '取消收藏' : '收藏'}
          >
            {card.is_favorite ? '★' : '☆'}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete() }}
            className="p-1 text-neutral-400 hover:text-red-500 rounded text-xs"
            title="删除"
          >
            ✕
          </button>
        </div>
        {/* 标题 */}
        <h3 className="text-sm font-medium text-neutral-900 line-clamp-2 leading-snug min-h-[2.5em] pr-4">
          {card.title}
        </h3>
        {/* 一句话理解副标题 */}
        {subtitle && (
          <p className="text-xs text-neutral-400 mt-1 line-clamp-1 leading-relaxed">
            {subtitle}
          </p>
        )}
        {/* 标签 */}
        <div className="flex items-center gap-1.5 mt-2.5">
          <span className="text-[10px] px-1.5 py-0.5 bg-neutral-100 text-neutral-600 rounded">
            {CONTENT_TYPE_LABEL[card.content_type] || card.content_type}
          </span>
          {card.space_id ? (
            <span className="text-[10px] px-1.5 py-0.5 bg-neutral-50 text-neutral-500 rounded border border-neutral-100">
              {card.domain || `空间 #${card.space_id}`}
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 bg-neutral-50 text-neutral-400 rounded border border-dashed border-neutral-200">
              未分类
            </span>
          )}
        </div>
        {/* 日期与重要标记（仅用户手动标记才显示） */}
        <div className="text-[10px] text-neutral-400 mt-2 flex items-center justify-between">
          <span>{(card.created_at || '').slice(5, 10)}</span>
          {card.importance === 'high' && (
            <span className="text-neutral-900">★ 重要</span>
          )}
        </div>
      </div>
    </div>
  )
}

// === 列表项（V6.2: hover 快捷操作） ===
function CardListItem({ card, active, onClick, onEdit, onDelete, onFavorite }) {
  const subtitle = card.one_liner || (card.ai_summary?.summary || '').slice(0, 80)
  return (
    <div
      onClick={onClick}
      className={`w-full text-left flex items-center justify-between py-3 px-4 rounded-lg border transition group cursor-pointer ${
        active ? 'border-neutral-300 bg-neutral-50' : 'border-neutral-100 hover:border-neutral-200 hover:bg-neutral-50/50'
      }`}
    >
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <div className="w-10 h-10 bg-neutral-50 rounded-lg flex items-center justify-center text-neutral-300 text-sm shrink-0">
          {card.content_type === 'video' ? '▷' : card.content_type === 'image' ? '▣' : '▢'}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-neutral-800 truncate">
            {card.importance === 'high' && <span className="text-neutral-900 mr-1">★</span>}
            {card.title}
          </div>
          {subtitle && (
            <div className="text-xs text-neutral-400 truncate mt-0.5">{subtitle}</div>
          )}
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[10px] text-neutral-400">{CONTENT_TYPE_LABEL[card.content_type] || card.content_type}</span>
            <span className="text-[10px] text-neutral-400">·</span>
            <span className="text-[10px] text-neutral-400">
              {card.space_id ? (card.domain || `空间 #${card.space_id}`) : '未分类'}
            </span>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {/* V6.2: hover 快捷操作 */}
        <div className="hidden group-hover:flex items-center gap-0.5">
          <button
            onClick={(e) => { e.stopPropagation(); onEdit() }}
            className="p-1 text-neutral-400 hover:text-neutral-900 rounded text-xs"
            title="编辑"
          >
            ✎
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onFavorite() }}
            className="p-1 text-neutral-400 hover:text-neutral-900 rounded text-xs"
            title={card.is_favorite ? '取消收藏' : '收藏'}
          >
            {card.is_favorite ? '★' : '☆'}
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete() }}
            className="p-1 text-neutral-400 hover:text-red-500 rounded text-xs"
            title="删除"
          >
            ✕
          </button>
        </div>
        {card.is_favorite && <span className="text-neutral-900 text-sm group-hover:hidden">★</span>}
        <span className="text-xs text-neutral-400">{(card.created_at || '').slice(5, 10)}</span>
      </div>
    </div>
  )
}

// === 卡片详情抽屉（V6.2: fixed 右侧抽屉，不占布局；遮罩由父组件渲染） ===
function CardDetail({ card, spaces, onEdit, onDelete, onClose, onCardChange }) {
  const navigate = useNavigate()
  const [fullCard, setFullCard] = useState(card)
  const [redistilling, setRedistilling] = useState(false)

  // 列表卡片缺 raw_text/related_cards，打开抽屉时拉全量详情
  useEffect(() => {
    let cancelled = false
    getCard(card.id).then((c) => {
      if (!cancelled) setFullCard(c)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [card.id])

  const handleCardChange = (next) => {
    setFullCard(next)
    onCardChange(next)
  }

  const handleRedistill = async () => {
    if (redistilling) return
    setRedistilling(true)
    try {
      const updated = await redistillCard(card.id)
      handleCardChange(updated)
    } catch (e) {
      alert(e?.response?.data?.detail || '重新总结失败，请重试')
    } finally {
      setRedistilling(false)
    }
  }

  return (
    <aside className="fixed inset-y-0 right-0 w-[420px] z-40 bg-white shadow-2xl border-l border-neutral-100">
      <div className="h-full flex flex-col overflow-y-auto">
        {/* 头部 */}
        <div className="sticky top-0 bg-white border-b border-neutral-100 px-5 py-4 flex items-center justify-between z-10">
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-600 text-sm">
            ← 返回
          </button>
          <div className="flex items-center gap-1">
            <button
              onClick={() => navigate(`/card/${card.id}`)}
              className="p-1.5 text-neutral-400 hover:text-neutral-900 rounded hover:bg-neutral-50 transition"
              title="全屏阅读"
            >
              ⛶
            </button>
            <button onClick={onEdit} className="p-1.5 text-neutral-400 hover:text-neutral-600 rounded hover:bg-neutral-50">
              ✎
            </button>
            <button
              onClick={() => updateCard(card.id, { is_favorite: !fullCard.is_favorite }).then((c) => handleCardChange(c))}
              className={`p-1.5 rounded hover:bg-neutral-50 ${fullCard.is_favorite ? 'text-neutral-900' : 'text-neutral-400 hover:text-neutral-900'}`}
            >
              ☆
            </button>
          </div>
        </div>

        <div className="p-5">
          <CardContent
            card={fullCard}
            spaces={spaces}
            onCardChange={handleCardChange}
            onOpenCard={(id) => navigate(`/card/${id}`)}
            onRedistill={handleRedistill}
            redistilling={redistilling}
          />
        </div>

        {/* 底部操作 */}
        <div className="sticky bottom-0 bg-white border-t border-neutral-100 px-5 py-3 flex gap-2">
          <button
            onClick={onEdit}
            className="flex-1 py-2 text-sm border border-neutral-200 text-neutral-700 rounded-lg hover:bg-neutral-50"
          >
            编辑
          </button>
          <button
            onClick={onDelete}
            className="px-4 py-2 text-sm text-red-500 border border-red-100 rounded-lg hover:bg-red-50"
          >
            删除
          </button>
        </div>
      </div>
    </aside>
  )
}
