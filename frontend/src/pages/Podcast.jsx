import { useEffect, useRef, useState } from 'react'
import { listSpaces, listCards, createPodcast, getPodcast, listPodcasts, retryPodcast, deletePodcast } from '../api'

// V7 AI 学习播客（NotebookLM 式）：两位 AI 主持人对话讲解你的知识
export default function Podcast() {
  const [spaces, setSpaces] = useState([])
  const [cards, setCards] = useState([])
  const [scopeType, setScopeType] = useState('space') // space | cards | all
  const [selectedSpaceId, setSelectedSpaceId] = useState('')
  const [selectedCardIds, setSelectedCardIds] = useState([])
  const [generating, setGenerating] = useState(false)
  const [current, setCurrent] = useState(null)   // 当前生成/查看的播客详情
  const [history, setHistory] = useState([])
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const pollRef = useRef(null)

  // 播放队列：单 audio 元素顺序播放（无 ffmpeg 拼接）
  const [playingIdx, setPlayingIdx] = useState(-1)
  const audioRef = useRef(null)

  useEffect(() => {
    listSpaces().then((d) => setSpaces(d.spaces || [])).catch(() => {})
    listCards({ limit: 100 }).then(setCards).catch(() => {})
    listPodcasts().then(setHistory).catch(() => {})
    return () => clearInterval(pollRef.current)
  }, [])

  useEffect(() => {
    if (!generating) { setElapsed(0); return }
    const t = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(t)
  }, [generating])

  const startPolling = (id) => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const p = await getPodcast(id)
        setCurrent(p)
        if (p.status !== 'generating') {
          clearInterval(pollRef.current)
          setGenerating(false)
          listPodcasts().then(setHistory).catch(() => {})
        }
      } catch (e) {
        // ignore
      }
    }, 2500)
  }

  const handleGenerate = async () => {
    setError('')
    if (scopeType === 'space' && !selectedSpaceId) {
      setError('请选择一个知识空间')
      return
    }
    if (scopeType === 'cards' && selectedCardIds.length === 0) {
      setError('请至少勾选一张卡片')
      return
    }
    const scope = scopeType === 'space'
      ? { type: 'space', value: Number(selectedSpaceId) }
      : scopeType === 'cards'
        ? { type: 'card_ids', value: selectedCardIds }
        : { type: 'all' }
    setGenerating(true)
    setCurrent({ status: 'generating', segments: [] })
    try {
      const r = await createPodcast(scope)
      startPolling(r.id)
    } catch (e) {
      setError('生成失败，请重试')
      setGenerating(false)
    }
  }

  const toggleCard = (id) => {
    setSelectedCardIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const playFrom = (idx) => {
    const url = current?.audio_urls?.[idx]
    if (!url) return
    setPlayingIdx(idx)
    if (audioRef.current) {
      audioRef.current.src = url
      audioRef.current.play().catch(() => {})
    }
  }

  const handleEnded = () => {
    // 自动播下一段
    const next = playingIdx + 1
    const urls = current?.audio_urls || []
    if (next < urls.length && urls[next]) {
      setPlayingIdx(next)
      if (audioRef.current) {
        audioRef.current.src = urls[next]
        audioRef.current.play().catch(() => {})
      }
    } else {
      setPlayingIdx(-1)
    }
  }

  // V9: 失败播客重试 / 删除
  const handleRetryPodcast = async (id) => {
    setError('')
    try {
      await retryPodcast(id)
      setGenerating(true)
      setCurrent({ status: 'generating', segments: [] })
      startPolling(id)
      listPodcasts().then(setHistory).catch(() => {})
    } catch (e) {
      setError(e?.response?.data?.detail || '重试失败，请稍后再试')
    }
  }

  const handleDeletePodcast = async (id) => {
    if (!confirm('确认删除这条播客？音频文件也会一并删除。')) return
    try {
      await deletePodcast(id)
      setHistory((prev) => prev.filter((p) => p.id !== id))
      if (current?.id === id) setCurrent(null)
    } catch (e) {
      setError(e?.response?.data?.detail || '删除失败，请稍后再试')
    }
  }

  const openHistory = async (id) => {
    try {
      const p = await getPodcast(id)
      setCurrent(p)
      setPlayingIdx(-1)
    } catch (e) {
      // ignore
    }
  }

  const showResult = current && current.status !== 'generating'
  const showGenerator = !generating || current?.status === 'generating'

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      {/* 隐藏音频元素 */}
      <audio ref={audioRef} onEnded={handleEnded} className="hidden" />

      {/* 头部 */}
      <div>
        <h1 className="text-2xl font-semibold text-neutral-900 mb-2">AI 学习播客</h1>
        <p className="text-sm text-neutral-500">
          两位 AI 主持人用聊天的方式讲解你的知识——像听播客一样学习
        </p>
      </div>

      {/* 生成器 */}
      <div className="bg-white border border-neutral-100 rounded-2xl p-6 space-y-5">
        <div className="text-sm font-semibold text-neutral-900">选择要聊的知识</div>
        <div className="flex gap-2">
          {[
            { key: 'space', label: '整个知识空间' },
            { key: 'cards', label: '指定卡片' },
            { key: 'all', label: '全部知识' },
          ].map((m) => (
            <button
              key={m.key}
              onClick={() => setScopeType(m.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                scopeType === m.key
                  ? 'bg-neutral-900 text-white border-neutral-900'
                  : 'border-neutral-200 text-neutral-600 hover:border-neutral-400'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {scopeType === 'space' && (
          <select
            value={selectedSpaceId}
            onChange={(e) => setSelectedSpaceId(e.target.value)}
            className="w-full px-3 py-2.5 border border-neutral-200 rounded-lg text-sm text-neutral-800 outline-none focus:border-neutral-400 bg-white"
          >
            <option value="">请选择知识空间</option>
            {spaces.map((sp) => (
              <option key={sp.id} value={sp.id}>{sp.name}（{sp.card_count} 张卡片）</option>
            ))}
          </select>
        )}

        {scopeType === 'cards' && (
          <div className="max-h-48 overflow-y-auto border border-neutral-100 rounded-lg divide-y divide-neutral-100">
            {cards.map((c) => (
              <label key={c.id} className="flex items-center gap-3 px-3 py-2 hover:bg-neutral-50 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedCardIds.includes(c.id)}
                  onChange={() => toggleCard(c.id)}
                  className="accent-neutral-900 w-4 h-4"
                />
                <span className="text-sm text-neutral-700 flex-1 truncate">{c.title}</span>
                <span className="text-xs text-neutral-400 shrink-0">{c.domain || '未分类'}</span>
              </label>
            ))}
          </div>
        )}

        {error && <p className="text-xs text-red-500">{error}</p>}

        <button
          onClick={handleGenerate}
          disabled={generating}
          className="w-full py-3 bg-neutral-900 text-white rounded-xl font-medium text-sm hover:bg-neutral-800 disabled:opacity-40 transition"
        >
          {generating ? `AI 正在写脚本与合成语音…（已用 ${elapsed} 秒，预计 1-4 分钟）` : '🎙️ 生成播客'}
        </button>
      </div>

      {/* 结果 / 生成中 */}
      {current && (
        <div className="bg-white border border-neutral-100 rounded-2xl overflow-hidden">
          <div className="px-6 py-4 border-b border-neutral-100 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-neutral-900">
                {current.status === 'generating' ? '正在创作你的播客…' : (current.title || '我的知识播客')}
              </div>
              <div className="text-xs text-neutral-400 mt-0.5">
                {current.status === 'generating' && (
                  <>AI 正在构思对话脚本（深度思考中，最长约 3 分钟）…</>
                )}
                {current.status === 'failed' && (
                  <span className="text-red-500">{current.error_message || '生成失败'}</span>
                )}
                {current.status === 'ready' && (
                  <>{(current.segments || []).length} 轮对话{current.audio_urls?.some(u => u) ? ' · 支持语音播放' : ' · 文字版'}</>
                )}
              </div>
            </div>
            {current.status === 'failed' && (
              <button
                onClick={() => handleRetryPodcast(current.id)}
                className="px-4 py-2 bg-neutral-900 text-white rounded-lg text-xs font-medium hover:bg-neutral-800 transition"
              >
                重新生成
              </button>
            )}
            {current.status === 'ready' && current.audio_urls?.some((u) => u) && (
              <button
                onClick={() => (playingIdx === -1 ? playFrom(0) : (audioRef.current?.pause(), setPlayingIdx(-1)))}
                className="px-4 py-2 bg-neutral-900 text-white rounded-lg text-xs font-medium hover:bg-neutral-800 transition"
              >
                {playingIdx === -1 ? '▶ 播放全部' : '⏸ 暂停'}
              </button>
            )}
          </div>

          {/* 对话脚本 */}
          {(current.segments || []).length > 0 && (
            <div className="p-6 space-y-4">
              {current.segments.map((seg, i) => (
                <div key={i} className={`flex ${seg.speaker === 'A' ? 'justify-start' : 'justify-end'}`}>
                  <div
                    className={`max-w-[75%] px-4 py-3 rounded-2xl ${
                      seg.speaker === 'A'
                        ? 'bg-neutral-50 border border-neutral-100 rounded-bl-sm'
                        : 'bg-neutral-900 text-white rounded-br-sm'
                    }`}
                  >
                    <div className={`text-[10px] mb-1 ${seg.speaker === 'A' ? 'text-neutral-400' : 'text-neutral-400'}`}>
                      {seg.speaker === 'A' ? '🎀 好奇同学' : '🎓 讲解老师'}
                      {current.audio_urls?.[i] && (
                        <button
                          onClick={() => playFrom(i)}
                          className={`ml-2 ${playingIdx === i ? 'text-white' : 'hover:text-white'}`}
                          title="播放这一段"
                        >
                          {playingIdx === i ? '🔊' : '▶'}
                        </button>
                      )}
                    </div>
                    <p className={`text-sm leading-7 ${playingIdx === i && seg.speaker === 'B' ? 'text-white' : ''}`}>
                      {seg.text}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 历史 */}
      {history.length > 0 && (
        <div className="bg-white border border-neutral-100 rounded-2xl p-6">
          <div className="text-sm font-semibold text-neutral-900 mb-4">我的播客</div>
          <div className="space-y-1">
            {history.slice(0, 8).map((p) => (
              <div
                key={p.id}
                role="button"
                tabIndex={0}
                onClick={() => openHistory(p.id)}
                onKeyDown={(e) => { if (e.key === 'Enter') openHistory(p.id) }}
                className="w-full text-left flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-neutral-50 transition cursor-pointer group"
              >
                <span className="text-xs">🎙️</span>
                <span className="text-sm text-neutral-700 flex-1 truncate">{p.title}</span>
                {p.status === 'ready' && p.audio_count > 0 && (
                  <span className="text-[10px] text-neutral-400">🔊 {p.audio_count} 段音频</span>
                )}
                {p.status === 'generating' && (
                  <span className="text-[10px] text-neutral-400">生成中…</span>
                )}
                {p.status === 'failed' && (
                  <span className="text-[10px] text-red-500">生成失败</span>
                )}
                {p.status === 'failed' && (
                  <span className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleRetryPodcast(p.id) }}
                      className="px-2 py-0.5 bg-neutral-900 text-white rounded text-[10px] hover:bg-neutral-800"
                    >
                      重试
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeletePodcast(p.id) }}
                      className="px-2 py-0.5 border border-neutral-200 text-neutral-500 rounded text-[10px] hover:border-red-400 hover:text-red-500"
                    >
                      删除
                    </button>
                  </span>
                )}
                <span className="text-xs text-neutral-300">{(p.created_at || '').slice(0, 10)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
