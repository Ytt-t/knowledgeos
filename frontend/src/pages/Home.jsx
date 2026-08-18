import { useEffect, useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  submitVideoUrl, uploadFile, getSource, continueSource, getGrowthOverview, listCards,
  getCard, listSpaces, createSpace, updateCard, listActiveSources, retrySource,
} from '../api'
import { STATUS_TEXT, STATUS_COLOR, PROCESSING_STATUSES, CONTENT_TYPE_LABEL } from '../utils/status'
import MarkdownLite from '../components/MarkdownLite'

const CAPTURE_MODES = [
  { key: 'video', label: '视频', icon: '▷' },
  { key: 'document', label: '文档', icon: '▢' },
  { key: 'image', label: '图片', icon: '▣' },
  { key: 'note', label: '笔记', icon: '✎' },
]

const PLACEHOLDER_MAP = {
  video: '粘贴 B站 / 小红书 / 抖音视频链接，或上传文件、图片…',
  document: '点击或拖拽 PDF / Word 文档到此处…',
  image: '点击或拖拽截图 / 笔记图片到此处…',
  note: '写一句笔记或心得…',
}

export default function Home() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [recentCards, setRecentCards] = useState([])
  const [activeSource, setActiveSource] = useState(null)
  const [error, setError] = useState('')
  const [input, setInput] = useState('')
  const [mode, setMode] = useState('video')
  const [submitting, setSubmitting] = useState(false)
  const fileRef = useRef(null)
  const imageRef = useRef(null)
  const noteRef = useRef(null)
  const pollRef = useRef(null)
  const [dragActive, setDragActive] = useState(false)
  const dragCounter = useRef(0)

  // V6: 确认保存面板状态
  const [confirmCard, setConfirmCard] = useState(null)
  const [spaces, setSpaces] = useState([])
  const [pickSpaceId, setPickSpaceId] = useState(null)   // null = 未分类
  const [newSpaceName, setNewSpaceName] = useState('')
  const [confirmTags, setConfirmTags] = useState('')
  const [markImportant, setMarkImportant] = useState(false)
  const [savingCard, setSavingCard] = useState(false)
  const [showThinking, setShowThinking] = useState(false)
  const [showNextSteps, setShowNextSteps] = useState(false)
  const [showSummaryDetail, setShowSummaryDetail] = useState(false)
  // V7: 重复内容弹窗
  const [dupSource, setDupSource] = useState(null)

  const load = () => {
    getGrowthOverview().then(setStats).catch(() => {})
    listCards({ limit: 5 }).then(setRecentCards).catch(() => {})
    listSpaces().then((d) => setSpaces(d.spaces || [])).catch(() => {})
  }

  useEffect(() => {
    load()
    // V8: 切走再切回时恢复处理进度/重复弹窗（后端一直在跑，前端 state 会丢）
    listActiveSources().then((items) => {
      const active = items || []
      const dup = active.find((s) => s.status === 'duplicate')
      if (dup) {
        setDupSource(dup)
        return
      }
      const processing = active.find((s) => PROCESSING_STATUSES.includes(s.status))
      if (processing) {
        setActiveSource(processing)
        startPolling(processing.id)
        return
      }
      // V9: 失败来源也要让用户看见，可一键重试
      const failed = active.find((s) => s.status === 'failed')
      if (failed) {
        setActiveSource(failed)
      }
    }).catch(() => {})
    return () => clearInterval(pollRef.current)
  }, [])

  const startPolling = (sourceId) => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await getSource(sourceId)
        setActiveSource(s)
        if (!PROCESSING_STATUSES.includes(s.status)) {
          clearInterval(pollRef.current)
          load()
          // V7: 重复内容 → 弹决策窗（不做确认保存）
          if (s.status === 'duplicate') {
            setDupSource(s)
            return
          }
          // V6: 处理完成后拉取卡片，弹「确认保存」面板（PRD: 用户确认保存）
          if (s.status === 'done' && s.card_id) {
            const card = await getCard(s.card_id).catch(() => null)
            if (card) {
              const sd = await listSpaces().catch(() => ({ spaces: [] }))
              const freshSpaces = sd.spaces || []
              setSpaces(freshSpaces)
              // 默认选中 AI 建议的空间
              const suggested = freshSpaces.find((sp) => sp.name === card.suggested_space)
              setPickSpaceId(suggested ? suggested.id : null)
              setConfirmTags((card.tags || []).join(', '))
              setMarkImportant(false)
              setConfirmCard(card)
            }
          }
        }
      } catch (e) {
        // ignore
      }
    }, 2500)
  }

  // V9: 失败来源重试
  const retryFailed = async () => {
    if (!activeSource || activeSource.status !== 'failed') return
    setError('')
    setActiveSource({ ...activeSource, status: 'pending', error_message: null })
    try {
      await retrySource(activeSource.id)
      startPolling(activeSource.id)
    } catch (e) {
      setError(e?.response?.data?.detail || '重试失败，请稍后再试')
      const s = await getSource(activeSource.id).catch(() => null)
      if (s) setActiveSource(s)
    }
  }

  // V6.1: 处理计时（等待时间透明化）
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!activeSource || !PROCESSING_STATUSES.includes(activeSource.status)) {
      setElapsed(0)
      return
    }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(t)
  }, [activeSource?.id, activeSource?.status])

  const formatElapsed = (sec) => {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m}:${String(s).padStart(2, '0')}`
  }

  // === 提交 ===
  const handleSubmit = async () => {
    setError('')
    if (mode === 'video') {
      if (!input.trim()) {
        setError('请输入视频链接')
        return
      }
      setSubmitting(true)
      try {
        const s = await submitVideoUrl(input.trim())
        setActiveSource(s)
        startPolling(s.id)
        setInput('')
      } catch (err) {
        setError(err?.response?.data?.detail || err.message)
      } finally {
        setSubmitting(false)
      }
    } else if (mode === 'note') {
      if (!input.trim()) {
        setError('请输入笔记内容')
        return
      }
      const blob = new Blob([input.trim()], { type: 'text/plain' })
      const file = new File([blob], `笔记_${new Date().toLocaleDateString()}.txt`, { type: 'text/plain' })
      setSubmitting(true)
      try {
        const s = await uploadFile(file)
        setActiveSource(s)
        startPolling(s.id)
        setInput('')
      } catch (err) {
        setError(err?.response?.data?.detail || err.message)
      } finally {
        setSubmitting(false)
      }
    }
  }

  const handleFileUpload = async (file) => {
    if (!file) return
    setError('')
    setSubmitting(true)
    try {
      const s = await uploadFile(file)
      setActiveSource(s)
      startPolling(s.id)
    } catch (err) {
      setError(err?.response?.data?.detail || err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const switchMode = (m) => {
    setMode(m)
    setError('')
    if (m === 'document') {
      fileRef.current?.click()
    } else if (m === 'image') {
      imageRef.current?.click()
    } else if (m === 'note') {
      setTimeout(() => noteRef.current?.focus(), 50)
    }
  }

  // === 拖拽 ===
  const onDragEnter = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = 'copy'
    dragCounter.current++
    setDragActive(true)
  }, [])

  const onDragOver = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    e.dataTransfer.dropEffect = 'copy'
  }, [])

  const onDragLeave = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current--
    if (dragCounter.current <= 0) {
      dragCounter.current = 0
      setDragActive(false)
    }
  }, [])

  const onDrop = useCallback(async (e) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current = 0
    setDragActive(false)
    if (submitting) return
    const file = e.dataTransfer.files?.[0]
    if (file) {
      if (file.type.startsWith('image/')) setMode('image')
      else setMode('document')
      handleFileUpload(file)
    }
  }, [submitting])

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleSubmit()
    }
  }

  // === V6 确认保存（V6.1: 保存后直达全屏知识页面） ===
  const handleConfirmSave = async () => {
    if (!confirmCard) return
    setSavingCard(true)
    try {
      let spaceId = pickSpaceId
      const newName = newSpaceName.trim()
      if (newName) {
        const sp = await createSpace(newName)
        spaceId = sp.id
      }
      await updateCard(confirmCard.id, {
        space_id: spaceId ?? null,
        tags: confirmTags.split(',').map((t) => t.trim()).filter(Boolean),
        importance: markImportant ? 'high' : null,
      })
      const cardId = confirmCard.id
      setConfirmCard(null)
      setActiveSource(null)
      navigate(`/card/${cardId}`)
    } catch (err) {
      setError(err?.response?.data?.detail || '保存失败，请重试')
    } finally {
      setSavingCard(false)
    }
  }

  const handleConfirmSkip = () => {
    // 不保存，卡片留在「未分类」，之后可在知识管理页随时整理
    setConfirmCard(null)
    setActiveSource(null)
    navigate('/space')
  }

  return (
    <div
      className="max-w-3xl mx-auto space-y-10"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {/* 拖拽全局提示 */}
      {dragActive && (
        <div className="fixed inset-0 bg-black/5 flex items-center justify-center z-50 pointer-events-none">
          <div className="bg-white rounded-2xl shadow-2xl border border-neutral-200 px-12 py-8 text-center">
            <div className="text-2xl text-neutral-400 mb-2 tracking-widest">↑</div>
            <div className="text-neutral-900 font-medium">松开鼠标即可上传</div>
            <div className="text-xs text-neutral-400 mt-1">支持 PDF、Word、图片等多种格式</div>
          </div>
        </div>
      )}

      {/* 首页 Hero（V10: GitHub/Stripe 式纯排版，无胶囊无装饰） */}
      <section className="pt-8 pb-12">
        <h1 className="text-[44px] leading-[1.08] font-semibold text-neutral-900 tracking-tight">
          Think less.
          <br />
          Answer more.
        </h1>
        <p className="text-base text-neutral-500 mt-4 max-w-lg leading-relaxed">
          Capture what you learn. Ask your own knowledge.
          <br />
          Get answers that actually stick.
        </p>
        <div className="flex items-center gap-6 mt-7">
          <button
            onClick={() => navigate('/assistant')}
            className="px-5 py-2.5 bg-neutral-900 text-white rounded-md text-sm font-medium hover:bg-neutral-700 transition-colors"
          >
            去问 AI
          </button>
          <button
            onClick={() => navigate('/space')}
            className="text-sm text-neutral-500 font-medium hover:text-neutral-900 transition-colors underline underline-offset-4 decoration-neutral-200 hover:decoration-neutral-900"
          >
            浏览知识库
          </button>
        </div>
      </section>

      {/* 捕获知识输入区 */}
      <section>
        <div className="relative">
          <input
            ref={noteRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={PLACEHOLDER_MAP[mode]}
            className="w-full px-4 py-3.5 pr-28 border border-neutral-200 rounded-2xl text-sm outline-none focus:border-neutral-400 focus:ring-4 focus:ring-neutral-100 transition-all shadow-sm"
            disabled={submitting}
          />
          <button
            onClick={handleSubmit}
            disabled={submitting || !input.trim()}
            className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-2 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            捕获知识
          </button>
        </div>

        {/* 模式切换 + 能力提示 */}
        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-1">
            {CAPTURE_MODES.map((m) => {
              const active = mode === m.key
              return (
                <button
                  key={m.key}
                  onClick={() => switchMode(m.key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    active
                      ? 'bg-neutral-900 text-white shadow-sm'
                      : 'text-neutral-500 hover:text-neutral-800 hover:bg-neutral-100'
                  }`}
                >
                  <span>{m.icon}</span>
                  <span>{m.label}</span>
                </button>
              )
            })}
          </div>
          <span className="text-[11px] text-neutral-400 hidden sm:block">
            支持 B站 / 小红书 / 抖音链接 · PDF / Word / 图片 · 直接写笔记
          </span>
        </div>

        {error && <p className="text-red-500 text-xs mt-2">{error}</p>}

        {/* 处理状态 */}
        {activeSource && (
          <div className="mt-4 p-4 bg-neutral-50 rounded-xl border border-neutral-100">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-neutral-700">
                {activeSource.source_type?.includes('video') ? '视频'
                  : activeSource.source_type === 'image' ? '图片'
                  : '文档'}处理
              </span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLOR[activeSource.status] || ''}`}>
                {STATUS_TEXT[activeSource.status] || activeSource.status}
              </span>
            </div>
            {PROCESSING_STATUSES.includes(activeSource.status) && (
              <div className="mt-4 space-y-3">
                {/* V6.3: 4 步阶段进度条（解析 → 思考 → 标签 → 完成） */}
                <div className="flex items-center gap-1.5">
                  {[
                    { step: 1, label: '解析内容' },
                    { step: 2, label: 'AI 深度思考' },
                    { step: 3, label: '标签建议' },
                    { step: 4, label: '完成' },
                  ].map((s) => {
                    const cur = activeSource.status === 'pending' ? 0
                      : activeSource.status === 'parsing' ? 1
                      : activeSource.status === 'summarizing' ? 2
                      : activeSource.status === 'classifying' ? 3 : 4
                    const state = s.step < cur ? 'done' : s.step === cur ? 'active' : 'todo'
                    return (
                      <div key={s.step} className="flex items-center gap-1.5 flex-1">
                        <div className={`flex items-center justify-center w-5 h-5 rounded-full text-[10px] shrink-0 ${
                          state === 'done'
                            ? 'bg-neutral-900 text-white'
                            : state === 'active'
                              ? 'bg-neutral-900 text-white animate-pulse'
                              : 'bg-neutral-100 text-neutral-400'
                        }`}>
                          {state === 'done' ? '✓' : s.step}
                        </div>
                        <span className={`text-[11px] ${
                          state === 'active' ? 'text-neutral-900 font-medium' : state === 'done' ? 'text-neutral-500' : 'text-neutral-300'
                        }`}>
                          {s.label}
                        </span>
                        {s.step < 4 && <span className={`flex-1 h-px ${s.step < cur ? 'bg-neutral-900' : 'bg-neutral-100'}`} />}
                      </div>
                    )
                  })}
                </div>

                {/* 当前状态描述 + 预计时长 */}
                <div className="flex items-center gap-2 text-xs text-neutral-500">
                  {activeSource.status === 'summarizing' && (
                    <>
                      <span className="inline-block w-3 h-3 border-2 border-neutral-400 border-t-transparent rounded-full animate-spin" />
                      AI 正在深度思考与蒸馏知识…
                      <span className="text-neutral-300">|</span>
                      <span className="text-neutral-400">预计 1-3 分钟 · 已用 {formatElapsed(elapsed)}</span>
                    </>
                  )}
                  {activeSource.status === 'parsing' && (
                    <>正在解析内容… <span className="text-neutral-400">通常几秒</span></>
                  )}
                  {activeSource.status === 'classifying' && (
                    <>
                      正在生成标签与空间建议…
                      <span className="text-neutral-300">|</span>
                      <span className="text-neutral-400">预计 10-30 秒</span>
                    </>
                  )}
                  {activeSource.status === 'pending' && <>排队等待处理…</>}
                </div>

                {/* V6.3: 思维链默认收起（不再实时铺开） */}
                {activeSource.status === 'summarizing' && activeSource.thinking_text && (
                  <div>
                    <button
                      onClick={() => setShowThinking(!showThinking)}
                      className="text-[11px] text-neutral-400 hover:text-neutral-600 transition"
                    >
                      💭 查看 AI 正在想什么 {showThinking ? '▲' : '▼'}
                    </button>
                    {showThinking && (
                      <div className="mt-2 p-3 bg-neutral-50 border border-neutral-100 rounded-lg max-h-36 overflow-y-auto">
                        <p className="text-[11px] text-neutral-500 whitespace-pre-wrap leading-relaxed">
                          {activeSource.thinking_text.slice(-600)}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            {activeSource.status === 'done' && (
              <button
                onClick={() => navigate('/space')}
                className="mt-3 w-full px-4 py-2.5 bg-neutral-900 text-white rounded-lg font-medium text-sm hover:bg-neutral-800 transition-colors"
              >
                处理完成，查看知识卡片 →
              </button>
            )}
            {activeSource.status === 'failed' && (
              <div className="mt-3 space-y-2.5">
                <div className="text-xs text-neutral-600 bg-neutral-100 px-3 py-2.5 rounded-lg leading-relaxed">
                  <div className="font-medium text-neutral-800 mb-1">这条内容处理失败了</div>
                  {activeSource.error_message || '未知错误，可能是网络或平台风控，点重试试试'}
                </div>
                <button
                  onClick={retryFailed}
                  className="w-full px-4 py-2 bg-white border border-neutral-300 text-neutral-800 rounded-lg text-sm hover:border-neutral-900 hover:text-neutral-900 transition-colors"
                >
                  重新处理
                </button>
              </div>
            )}
          </div>
        )}

        {/* 隐藏文件输入 */}
        <input ref={fileRef} type="file" accept=".pdf,.docx,.doc" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); e.target.value = '' }} />
        <input ref={imageRef} type="file" accept=".png,.jpg,.jpeg,.webp" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); e.target.value = '' }} />
      </section>

      {/* 最近学习 + 知识概览 */}
      <div className="grid grid-cols-3 gap-6">
        {/* 最近学习 */}
        <section className="col-span-2">
          <h2 className="text-sm font-semibold text-neutral-900 mb-3">最近学习</h2>
          {recentCards.length === 0 ? (
            <div className="text-neutral-400 text-sm py-6">还没有知识卡片</div>
          ) : (
            <div className="space-y-0.5">
              {recentCards.map((c) => (
                <button
                  key={c.id}
                  onClick={() => navigate(`/card/${c.id}`)}
                  className="w-full text-left flex items-center gap-3 py-2.5 px-3 -mx-2 rounded-lg border border-transparent hover:border-neutral-100 hover:bg-neutral-50 transition-all group"
                >
                  <span className="w-7 h-7 rounded-md bg-neutral-100 text-neutral-500 flex items-center justify-center text-xs group-hover:bg-neutral-900 group-hover:text-white transition-colors">
                    {c.content_type === 'video' ? '▷' : c.content_type === 'image' ? '▣' : '▢'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-neutral-700 truncate group-hover:text-neutral-900 block">
                      {c.title}
                    </span>
                    {c.one_liner && (
                      <span className="text-xs text-neutral-400 truncate block mt-0.5">
                        {c.one_liner}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-neutral-400 shrink-0 group-hover:text-neutral-600">
                    {(c.created_at || '').slice(5, 10)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* 知识概览 */}
        <section>
          <h2 className="text-sm font-semibold text-neutral-900 mb-3">知识概览</h2>
          <div className="border border-neutral-100 rounded-xl overflow-hidden shadow-sm">
            <div className="p-4 bg-neutral-50/60">
              <div className="flex items-baseline justify-between">
                <div className="text-xs text-neutral-400">总知识数</div>
                <span className="text-[10px] text-neutral-300">全部卡片</span>
              </div>
              <div className="text-3xl font-semibold text-neutral-900 mt-1 tracking-tight">
                {stats?.total_cards || 0}
              </div>
            </div>
            <div className="grid grid-cols-3 divide-x divide-neutral-100 border-t border-neutral-100">
              <div className="p-3.5 text-center hover:bg-neutral-50 transition-colors">
                <div className="text-base font-semibold text-neutral-900">{stats?.today_count || 0}</div>
                <div className="text-[10px] text-neutral-400 mt-0.5">今日新增</div>
              </div>
              <div className="p-3.5 text-center hover:bg-neutral-50 transition-colors">
                <div className="text-base font-semibold text-neutral-900">{stats?.streak_days || 0}</div>
                <div className="text-[10px] text-neutral-400 mt-0.5">连续学习</div>
              </div>
              <div className="p-3.5 text-center hover:bg-neutral-50 transition-colors">
                <div className="text-base font-semibold text-neutral-900">
                  {Object.keys(stats?.space_distribution || {}).length}
                </div>
                <div className="text-[10px] text-neutral-400 mt-0.5">知识空间</div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* V7: 重复内容决策弹窗 */}
      {dupSource && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-neutral-100 w-full max-w-md p-7 text-center">
            <div className="text-3xl mb-4">🙈</div>
            <h3 className="text-base font-semibold text-neutral-900 leading-snug">
              这个知识你已经存过了
            </h3>
            {dupSource.duplicate_card_title && (
              <p className="text-sm text-neutral-500 mt-2">
                已有卡片：<span className="text-neutral-900 font-medium">{dupSource.duplicate_card_title}</span>
              </p>
            )}
            <p className="text-xs text-neutral-400 mt-2 leading-relaxed">
              AI 发现这份内容和知识库里已有的卡片非常相似，不用重复学习
            </p>
            <div className="mt-6 space-y-2">
              <button
                onClick={() => {
                  const id = dupSource.duplicate_card_id
                  setDupSource(null)
                  setActiveSource(null)
                  if (id) navigate(`/card/${id}`)
                }}
                className="w-full py-2.5 text-sm bg-neutral-900 text-white rounded-lg font-medium hover:bg-neutral-800 transition"
              >
                查看已有卡片
              </button>
              <button
                onClick={async () => {
                  const id = dupSource.id
                  setDupSource(null)
                  try {
                    await continueSource(id, 'create_new')
                    startPolling(id)
                  } catch (e) {
                    setError('操作失败，请重试')
                  }
                }}
                className="w-full py-2.5 text-sm border border-neutral-200 text-neutral-700 rounded-lg hover:bg-neutral-50 transition"
              >
                仍然新建（内容确实不同）
              </button>
              <button
                onClick={async () => {
                  const id = dupSource.id
                  setDupSource(null)
                  setActiveSource(null)
                  try {
                    await continueSource(id, 'discard')
                  } catch (e) {
                    // ignore
                  }
                }}
                className="w-full py-2.5 text-sm text-neutral-400 hover:text-neutral-600 transition"
              >
                放弃这次上传
              </button>
            </div>
          </div>
        </div>
      )}

      {/* V6.2: 确认保存面板 —— 知识总结预览重做（产品核心：保存前审阅 AI 蒸馏成果） */}
      {confirmCard && (
        <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50 p-4" onClick={handleConfirmSkip}>
          <div
            className="bg-white rounded-2xl shadow-2xl border border-neutral-100 w-full max-w-2xl max-h-[88vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 头部 */}
            <div className="px-7 pt-6 pb-5 border-b border-neutral-100">
              <div className="text-sm text-neutral-600 mb-2">
                AI 已读完全部内容，先把它归个类吧：
              </div>
              <h3 className="text-xl font-semibold text-neutral-900 leading-snug tracking-tight">
                {confirmCard.title}
              </h3>
              {confirmCard.one_liner && (
                <p className="text-sm text-neutral-500 mt-2.5 leading-relaxed bg-neutral-50 px-3.5 py-2.5 rounded-lg">
                  {confirmCard.one_liner}
                </p>
              )}
            </div>

            {/* V6.4: 整理区优先（弹出面板的主体 —— 先分类，总结想看了再展开） */}
            <div className="px-7 py-6 space-y-5">
              <div>
                <div className="text-xs font-semibold text-neutral-900 mb-2">
                  归入知识空间
                  {confirmCard.suggested_space && (
                    <span className="ml-2 font-normal text-neutral-400">
                      AI 建议「{confirmCard.suggested_space}」
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <button
                    onClick={() => setPickSpaceId(null)}
                    className={`px-3 py-1.5 rounded-lg text-xs border transition ${
                      pickSpaceId === null && !newSpaceName.trim()
                        ? 'bg-neutral-900 text-white border-neutral-900'
                        : 'border-neutral-200 text-neutral-600 hover:border-neutral-400'
                    }`}
                  >
                    未分类
                  </button>
                  {spaces.map((sp) => (
                    <button
                      key={sp.id}
                      onClick={() => { setPickSpaceId(sp.id); setNewSpaceName('') }}
                      className={`px-3 py-1.5 rounded-lg text-xs border transition ${
                        pickSpaceId === sp.id && !newSpaceName.trim()
                          ? 'bg-neutral-900 text-white border-neutral-900'
                          : 'border-neutral-200 text-neutral-600 hover:border-neutral-400'
                      }`}
                    >
                      {sp.name}
                    </button>
                  ))}
                </div>
                <input
                  value={newSpaceName}
                  onChange={(e) => setNewSpaceName(e.target.value)}
                  placeholder="＋ 新建一个空间…"
                  className="mt-2 w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-400"
                />
              </div>

              <div>
                <div className="text-xs font-semibold text-neutral-900 mb-2">
                  标签 <span className="font-normal text-neutral-400">（逗号分隔，AI 建议可修改）</span>
                </div>
                <input
                  value={confirmTags}
                  onChange={(e) => setConfirmTags(e.target.value)}
                  className="w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm outline-none focus:border-neutral-400"
                />
              </div>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={markImportant}
                  onChange={(e) => setMarkImportant(e.target.checked)}
                  className="accent-neutral-900 w-4 h-4"
                />
                <span className="text-sm text-neutral-700">标记为重要</span>
                <span className="text-xs text-neutral-400">（是否重要由你决定）</span>
              </label>
            </div>

            {/* V6.4: 总结详情默认收起 —— 想仔细看时再展开（保存后知识页里也能看） */}
            <div className="px-7 pb-5">
              <button
                onClick={() => setShowSummaryDetail(!showSummaryDetail)}
                className="w-full flex items-center justify-between px-4 py-3 border border-dashed border-neutral-200 rounded-xl text-sm text-neutral-600 hover:border-neutral-400 hover:text-neutral-900 transition"
              >
                <span>{showSummaryDetail ? '收起 AI 总结详情' : '先看看 AI 总结得怎么样？'}</span>
                <span className="text-xs text-neutral-400">{showSummaryDetail ? '▲' : '▼'}</span>
              </button>
              {showSummaryDetail && (
                <div className="mt-5 space-y-8">
                  {confirmCard.ai_summary?.summary && (
                    <div>
                      <h4 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">AI 总结</h4>
                      <div className="text-base text-neutral-800">
                        <MarkdownLite text={confirmCard.ai_summary.summary} className="[&_p]:leading-8 [&_p]:my-4 [&_p:first-child]:mt-0" />
                      </div>
                    </div>
                  )}

                  {confirmCard.core_points?.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">核心要点</h4>
                      <div className="divide-y divide-neutral-100">
                        {confirmCard.core_points.map((p, i) => {
                          const point = typeof p === 'string' ? p : p.point
                          const detail = typeof p === 'object' && p.detail ? p.detail : ''
                          return (
                            <div key={i} className="flex gap-3.5 py-4 first:pt-0 last:pb-0">
                              <span className="w-6 h-6 rounded-full bg-neutral-900 text-white text-xs font-medium flex items-center justify-center shrink-0 mt-0.5">
                                {i + 1}
                              </span>
                              <div className="flex-1 min-w-0">
                                <div className="text-[15px] font-semibold text-neutral-900 leading-7">{point}</div>
                                {detail && (
                                  <div className="text-sm text-neutral-500 leading-7 mt-1">{detail}</div>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {confirmCard.next_steps?.length > 0 && (
                    <div>
                      <button
                        onClick={() => setShowNextSteps(!showNextSteps)}
                        className="text-xs text-neutral-500 hover:text-neutral-700 transition"
                      >
                        📚 下一步学习建议（{confirmCard.next_steps.length} 条） {showNextSteps ? '▲' : '▼'}
                      </button>
                      {showNextSteps && (
                        <div className="mt-3 space-y-2">
                          {confirmCard.next_steps.map((s, i) => (
                            <div key={i} className="text-sm text-neutral-700 flex gap-2 items-start leading-relaxed">
                              <span className="text-neutral-400 shrink-0 mt-0.5 text-xs">{i + 1}.</span>
                              <span className="flex-1">{typeof s === 'string' ? s : s.step || s.suggestion || ''}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {activeSource?.thinking_text && (
                    <div>
                      <button
                        onClick={() => setShowThinking(!showThinking)}
                        className="text-xs text-neutral-500 hover:text-neutral-700 transition"
                      >
                        💭 查看 AI 思考过程 {showThinking ? '▲' : '▼'}
                      </button>
                      {showThinking && (
                        <div className="mt-2 p-3 bg-neutral-50 border border-neutral-100 rounded-lg max-h-48 overflow-y-auto">
                          <p className="text-[11px] text-neutral-500 whitespace-pre-wrap leading-relaxed">
                            {activeSource.thinking_text}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* 底部按钮 */}
            <div className="px-7 pb-6 flex gap-2 border-t border-neutral-100 pt-4">
              <button
                onClick={handleConfirmSkip}
                className="flex-1 py-2.5 text-sm border border-neutral-200 text-neutral-600 rounded-lg hover:bg-neutral-50 transition"
              >
                跳过（留在未分类）
              </button>
              <button
                onClick={handleConfirmSave}
                disabled={savingCard}
                className="flex-1 py-2.5 text-sm bg-neutral-900 text-white rounded-lg font-medium hover:bg-neutral-800 disabled:opacity-40 transition"
              >
                {savingCard ? '保存中…' : '确认保存，查看知识页'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
