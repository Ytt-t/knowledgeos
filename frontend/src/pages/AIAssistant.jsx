import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createChatSession,
  listChatSessions,
  updateChatSession,
  deleteChatSession,
  clearAllChatSessions,
  listMessages,
  streamChatMessage,
  getCitedCard,
  listSpaces,
} from '../api'
import MarkdownLite from '../components/MarkdownLite'

// V9：两种模式 —— 随便聊聊（通用 AI，秒回）/ 问我的知识（严格基于个人知识库，带引用）
const COPILOT_MODES = [
  {
    key: 'free',
    label: '随便聊聊',
    desc: '通用 AI 大脑 · 秒回',
    hint: '不查你的知识库，适合闲聊、灵感、通用问题',
    placeholder: '想聊什么就聊什么…',
  },
  {
    key: 'kb',
    label: '问我的知识',
    desc: '只基于你的知识库 · 带引用',
    hint: '只基于你存过的内容回答，关键结论带引用来源',
    placeholder: '问点和你学过的内容有关的…',
  },
]

const STARTERS = {
  free: [
    '帮我列一份今天 10 分钟能完成的学习计划',
    '用大白话解释一下大模型幻觉',
    '给我想一个有意思的 AI 产品 idea',
  ],
  kb: [
    '帮我总结一下最近学的知识点',
    '最近学的这些知识之间有什么联系？',
    '用我知识库里的内容讲讲 RAG',
    '给我出几道题考考自己',
  ],
}

// V9：每条回答后的快捷追问（纯前端、零延迟，引导多轮对话）
const FOLLOW_UPS = {
  free: ['换个更有趣的说法', '再举一个例子', '说说反面 / 风险是什么'],
  kb: ['再展开讲讲第一个点', '把重点浓缩成 3 条', '给我出一道相关的练习题'],
}

export default function AIAssistant() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [activeSession, setActiveSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(null) // { citations: [], text: '' }
  const [spaces, setSpaces] = useState([])
  const [scope, setScope] = useState({ type: 'all' })
  const [scopeLabel, setScopeLabel] = useState('全部知识')
  const [showScope, setShowScope] = useState(false)
  const [menuSessionId, setMenuSessionId] = useState(null)
  const [renaming, setRenaming] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [mode, setMode] = useState('free')
  const [copiedId, setCopiedId] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const scrollRef = useRef(null)
  const [sessionsCollapsed, setSessionsCollapsed] = useState(
    () => localStorage.getItem('kos_ai_sidebar') === '1'
  )

  useEffect(() => {
    listSpaces().then((d) => setSpaces(d.spaces || [])).catch(() => {})
    listChatSessions().then(async (list) => {
      setSessions(list)
      const lastId = localStorage.getItem('kos_active_session')
      if (lastId) {
        const last = list.find((s) => String(s.id) === String(lastId))
        if (last) {
          setActiveSession(last)
          const msgs = await listMessages(last.id).catch(() => [])
          setMessages(msgs)
          if (last.scope_filter) {
            setScope(last.scope_filter)
            setScopeLabel(scopeToLabel(last.scope_filter, []))
          }
        } else {
          localStorage.removeItem('kos_active_session')
        }
      }
    }).catch(() => {})
  }, [])

  // 发送计时（等待时间透明化）
  useEffect(() => {
    if (!sending) { setElapsed(0); return }
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(timer)
  }, [sending])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, streaming?.text, streaming?.citations])

  const toggleSessionsCollapsed = () => {
    const next = !sessionsCollapsed
    setSessionsCollapsed(next)
    localStorage.setItem('kos_ai_sidebar', next ? '1' : '0')
  }

  const handleNewSession = async () => {
    const s = await createChatSession(scope)
    setSessions([s, ...sessions])
    setActiveSession(s)
    setMessages([])
    localStorage.setItem('kos_active_session', String(s.id))
  }

  const handleSelectSession = async (s) => {
    setActiveSession(s)
    setMenuSessionId(null)
    const msgs = await listMessages(s.id)
    setMessages(msgs)
    if (s.scope_filter) {
      setScope(s.scope_filter)
      setScopeLabel(scopeToLabel(s.scope_filter, spaces))
    }
    localStorage.setItem('kos_active_session', String(s.id))
  }

  const refreshSessions = () => {
    listChatSessions().then((list) => {
      setSessions(list)
      const fresh = list.find((x) => x.id === activeSession?.id)
      if (fresh) setActiveSession(fresh)
    }).catch(() => {})
  }

  const handleSend = async (text) => {
    const content = (text || input).trim()
    if (!content || sending) return

    let sid = activeSession?.id
    if (!sid) {
      const s = await createChatSession(scope)
      sid = s.id
      setActiveSession(s)
      setSessions((prev) => [s, ...prev])
      localStorage.setItem('kos_active_session', String(sid))
    }

    setMessages((prev) => [...prev, { role: 'user', content }])
    setInput('')
    setSending(true)
    setStreaming({ citations: [], text: '' })

    let finalText = ''
    let citationCards = []
    let finished = false

    try {
      await streamChatMessage(sid, content, mode, (ev) => {
        if (ev.type === 'citations') {
          citationCards = ev.cards || []
          setStreaming((s) => ({ ...s, citations: citationCards }))
        } else if (ev.type === 'delta') {
          finalText += ev.text
          setStreaming((s) => ({ ...s, text: finalText }))
        } else if (ev.type === 'done') {
          const msg = ev.message
          finalText = msg.content
          setMessages((prev) => [...prev, msg])
          setStreaming(null)
          finished = true
        } else if (ev.type === 'error') {
          setMessages((prev) => [...prev, {
            role: 'assistant',
            content: ev.message || '出错了，请再试一次',
            error: true,
          }])
          setStreaming(null)
          finished = true
        }
      })
      if (!finished) {
        // 流意外结束但没有 done：把已生成的内容落成消息（内容已在后端保存）
        setMessages((prev) => [...prev, {
          role: 'assistant',
          content: finalText || '（回答中断了，再问一次试试）',
          cited_card_ids: citationCards.map((c) => c.id),
        }])
        setStreaming(null)
      }
      refreshSessions()
    } catch (e) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: `发送失败：${e.message}。网络或服务临时不可用，请稍后重试。`,
        error: true,
      }])
    } finally {
      setSending(false)
      setStreaming(null)
    }
  }

  const handleDeleteSession = async (id) => {
    if (!confirm('确认删除这个对话？所有消息将一并删除。')) return
    await deleteChatSession(id)
    const updated = sessions.filter((s) => s.id !== id)
    setSessions(updated)
    if (activeSession?.id === id) {
      setActiveSession(null)
      setMessages([])
    }
    setMenuSessionId(null)
  }

  const handleClearAll = async () => {
    if (!confirm('确认清空所有对话历史？此操作不可撤销。')) return
    await clearAllChatSessions()
    setSessions([])
    setActiveSession(null)
    setMessages([])
    setMenuSessionId(null)
  }

  const handleRename = (s) => {
    setRenaming(s)
    setRenameValue(s.title)
    setMenuSessionId(null)
  }

  const handleRenameSubmit = async (id) => {
    const title = renameValue.trim() || '新会话'
    await updateChatSession(id, { title })
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)))
    if (activeSession?.id === id) {
      setActiveSession({ ...activeSession, title })
    }
    setRenaming(null)
  }

  const handleToggleFavorite = async (s) => {
    const newValue = !s.is_favorite
    await updateChatSession(s.id, { is_favorite: newValue })
    setSessions((prev) => prev.map((x) => (x.id === s.id ? { ...x, is_favorite: newValue } : x)))
    setMenuSessionId(null)
  }

  const applyScope = (newScope, label) => {
    setScope(newScope)
    setScopeLabel(label)
    setShowScope(false)
  }

  const copyText = async (id, text) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 1500)
    } catch (e) {
      // 剪贴板不可用时静默
    }
  }

  const modeInfo = COPILOT_MODES.find((m) => m.key === mode) || COPILOT_MODES[0]

  return (
    <div className="flex gap-6 h-[calc(100vh-6rem)]">
      {/* 左侧：会话列表 */}
      {sessionsCollapsed ? (
        <div className="w-9 shrink-0 flex flex-col items-center gap-2">
          <button
            onClick={handleNewSession}
            title="新建对话"
            className="w-8 h-8 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 transition-colors"
          >
            +
          </button>
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => handleSelectSession(s)}
              title={s.title}
              className={`w-8 h-8 rounded-md text-xs transition ${
                activeSession?.id === s.id
                  ? 'bg-neutral-100 text-neutral-900 font-medium'
                  : 'text-neutral-400 hover:text-neutral-900 hover:bg-neutral-50'
              }`}
            >
              {s.is_favorite ? '★' : '✦'}
            </button>
          ))}
          <button
            onClick={toggleSessionsCollapsed}
            title="展开会话列表"
            className="text-neutral-300 hover:text-neutral-600 text-xs mt-2"
          >
            ⇥
          </button>
        </div>
      ) : (
        <aside className="w-56 shrink-0 flex flex-col">
          <div className="flex items-center gap-1 mb-2">
            <button
              onClick={handleNewSession}
              className="flex-1 px-3 py-2.5 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 transition-colors"
            >
              + 新建对话
            </button>
            <button
              onClick={toggleSessionsCollapsed}
              title="折叠会话列表"
              className="text-neutral-300 hover:text-neutral-600 text-xs px-1"
            >
              ⇤
            </button>
          </div>
          {sessions.length > 0 && (
            <button
              onClick={handleClearAll}
              className="w-full px-3 py-1.5 text-xs text-neutral-400 hover:text-red-500 transition-colors mb-3 text-right"
            >
              清空所有对话
            </button>
          )}
          <div className="flex-1 overflow-y-auto space-y-0.5">
            {sessions.map((s) => (
              <div key={s.id} className="relative">
                {renaming?.id === s.id ? (
                  <div className="px-3 py-2 bg-neutral-50 rounded-md">
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRenameSubmit(s.id)
                        if (e.key === 'Escape') setRenaming(null)
                      }}
                      onBlur={() => handleRenameSubmit(s.id)}
                      className="w-full px-2 py-1 text-sm border border-neutral-300 rounded outline-none focus:border-neutral-500"
                    />
                  </div>
                ) : (
                  <button
                    onClick={() => handleSelectSession(s)}
                    onContextMenu={(e) => {
                      e.preventDefault()
                      setMenuSessionId(menuSessionId === s.id ? null : s.id)
                    }}
                    className={`w-full text-left px-3 py-2 rounded-md text-sm transition group ${
                      activeSession?.id === s.id
                        ? 'bg-neutral-100 text-neutral-900 font-medium'
                        : 'text-neutral-500 hover:text-neutral-900 hover:bg-neutral-50'
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      {s.is_favorite && <span className="text-neutral-900 text-xs shrink-0">★</span>}
                      <span className="truncate flex-1">{s.title}</span>
                      <span
                        onClick={(e) => {
                          e.stopPropagation()
                          setMenuSessionId(menuSessionId === s.id ? null : s.id)
                        }}
                        className="text-neutral-300 hover:text-neutral-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 px-1"
                      >
                        ⋯
                      </span>
                    </div>
                    <div className="text-xs text-neutral-400 mt-0.5">
                      {(s.created_at || '').slice(0, 10)}
                    </div>
                  </button>
                )}
                {menuSessionId === s.id && renaming?.id !== s.id && (
                  <div className="absolute right-0 top-full mt-1 bg-white border border-neutral-200 rounded-lg shadow-lg z-20 w-36 py-1">
                    <button
                      onClick={() => handleRename(s)}
                      className="w-full text-left px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-50 transition-colors"
                    >
                      重命名
                    </button>
                    <button
                      onClick={() => handleToggleFavorite(s)}
                      className="w-full text-left px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-50 transition-colors"
                    >
                      {s.is_favorite ? '取消收藏' : '收藏对话'}
                    </button>
                    <div className="border-t border-neutral-100 my-1" />
                    <button
                      onClick={() => handleDeleteSession(s.id)}
                      className="w-full text-left px-3 py-1.5 text-xs text-red-500 hover:bg-red-50 transition-colors"
                    >
                      删除对话
                    </button>
                  </div>
                )}
              </div>
            ))}
            {sessions.length === 0 && (
              <div className="text-xs text-neutral-400 text-center py-4">
                暂无对话
              </div>
            )}
          </div>
        </aside>
      )}

      {/* 右侧：聊天区 */}
      <section className="flex-1 flex flex-col bg-white border border-neutral-200 rounded-xl overflow-hidden">
        {/* 顶部：模式 + 范围选择器 */}
        <div className="px-5 py-3 border-b border-neutral-100 flex items-center gap-3 relative flex-wrap">
          <div className="flex items-center gap-1 bg-neutral-50 rounded-md p-0.5">
            {COPILOT_MODES.map((m) => (
              <button
                key={m.key}
                onClick={() => setMode(m.key)}
                title={m.hint}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  mode === m.key
                    ? 'bg-neutral-900 text-white'
                    : 'text-neutral-500 hover:text-neutral-900'
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {mode === 'kb' && (
            <>
              <div className="w-px h-4 bg-neutral-200" />
              <span className="text-xs text-neutral-400">范围</span>
              <button
                onClick={() => setShowScope(!showScope)}
                className="px-3 py-1 bg-neutral-100 hover:bg-neutral-200 rounded-md text-xs text-neutral-700 flex items-center gap-1.5 transition-colors"
              >
                {scopeLabel}
                <span className="text-neutral-400">▾</span>
              </button>
            </>
          )}
          {showScope && (
            <div className="absolute top-full left-24 mt-1 bg-white border border-neutral-200 rounded-lg shadow-lg z-10 w-56 py-1 max-h-72 overflow-y-auto">
              <ScopeOption
                onClick={() => applyScope({ type: 'all' }, '全部知识')}
                active={scope.type === 'all'}
                label="全部知识"
              />
              <div className="px-3 py-1 text-xs text-neutral-400">按知识空间</div>
              {spaces.map((sp) => (
                <ScopeOption
                  key={sp.id}
                  onClick={() => applyScope({ type: 'space', value: sp.id }, `空间：${sp.name}`)}
                  active={scope.type === 'space' && scope.value === sp.id}
                  label={`${sp.name} (${sp.card_count})`}
                />
              ))}
              {spaces.length === 0 && (
                <div className="px-3 py-1 text-xs text-neutral-300">还没有知识空间</div>
              )}
            </div>
          )}
          <span className="text-xs text-neutral-400 ml-auto hidden md:block">{modeInfo.hint}</span>
        </div>

        {/* 消息区 */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {messages.length === 0 && !streaming ? (
            <EmptyState mode={mode} modeInfo={modeInfo} onSend={handleSend} />
          ) : (
            <>
              {messages.map((m, i) => (
                <MessageBubble
                  key={i}
                  msg={m}
                  copiedId={copiedId}
                  onCopy={copyText}
                  mode={mode}
                  onCiteClick={(id) => navigate(`/card/${id}`)}
                  onFollowUp={handleSend}
                />
              ))}
              {streaming && (
                <StreamingBubble
                  streaming={streaming}
                  onCiteClick={(id) => navigate(`/card/${id}`)}
                />
              )}
              {sending && !streaming && (
                <div className="flex justify-start">
                  <div className="px-4 py-3 bg-neutral-50 border border-neutral-100 rounded-2xl rounded-bl-sm flex items-center gap-2 text-sm text-neutral-500">
                    <span className="inline-block w-2 h-4 bg-neutral-900 animate-pulse rounded-sm" />
                    正在连接 AI…
                    {elapsed > 0 && <span className="text-xs text-neutral-400">{elapsed}s</span>}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* 输入区 */}
        <div className="px-5 py-4 border-t border-neutral-100">
          <div className="relative">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder={modeInfo.placeholder}
              className="w-full px-4 py-3 pr-20 bg-neutral-50 border border-neutral-200 rounded-xl text-sm outline-none focus:border-neutral-400 focus:bg-white transition-all"
              disabled={sending}
            />
            <button
              onClick={() => handleSend()}
              disabled={sending || !input.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-1.5 bg-neutral-900 text-white rounded-lg text-xs font-medium hover:bg-neutral-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {sending ? `思考中 ${elapsed}s` : '发送'}
            </button>
          </div>
          <div className="text-[11px] text-neutral-300 mt-2 text-center">
            AI 回答可能不完美，重要信息请以原文为准
          </div>
        </div>
      </section>
    </div>
  )
}

function EmptyState({ mode, modeInfo, onSend }) {
  const starters = STARTERS[mode] || STARTERS.free
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6">
      <div className="w-14 h-14 rounded-2xl bg-neutral-100 flex items-center justify-center text-2xl text-neutral-400 mb-5">
        ✦
      </div>
      <p className="text-base font-medium text-neutral-900 mb-1.5">
        {mode === 'kb' ? '想问你的知识库什么？' : '嗨，想聊点啥？'}
      </p>
      <p className="text-sm text-neutral-400 mb-7 max-w-sm leading-relaxed">
        {mode === 'kb'
          ? '我只基于你存过的知识回答，答完会标出来源卡片，点一下就能回原文。'
          : '我是不端着的 AI 搭子，什么都能聊。要聊知识库内容，切到「问我的知识」。'}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg w-full">
        {starters.map((q) => (
          <button
            key={q}
            onClick={() => onSend(q)}
            className="text-left px-4 py-3 border border-neutral-200 rounded-lg text-xs text-neutral-600 hover:border-neutral-400 hover:bg-neutral-50 transition-all"
          >
            {q}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-neutral-300 mt-6">{modeInfo.desc}</p>
    </div>
  )
}

function StreamingBubble({ streaming, onCiteClick }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] w-full">
        <div className="px-4 py-3 bg-neutral-50 border border-neutral-100 rounded-2xl rounded-bl-sm">
          {streaming.text ? (
            <div>
              <MarkdownLite text={streaming.text} />
              <span className="inline-block w-1.5 h-4 bg-neutral-900 animate-pulse align-middle ml-0.5 rounded-sm" />
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-neutral-500">
              <span className="inline-block w-2 h-4 bg-neutral-900 animate-pulse rounded-sm" />
              {streaming.citations.length > 0 ? '已经找到相关卡片，正在组织回答…' : '正在思考…'}
            </div>
          )}
        </div>
        {streaming.citations.length > 0 && (
          <div className="mt-2 px-4">
            <div className="text-xs text-neutral-400 mb-1.5">引用你的知识卡片（点击查看原文）</div>
            <div className="flex flex-wrap gap-1.5">
              {streaming.citations.map((c) => (
                <button
                  key={c.id}
                  onClick={() => onCiteClick(c.id)}
                  className="px-2 py-1 bg-white text-neutral-700 rounded text-xs border border-neutral-200 hover:border-neutral-900 hover:text-neutral-900 transition-colors"
                  title={c.one_liner || c.title}
                >
                  {c.title} ↗
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function MessageBubble({ msg, copiedId, onCopy, mode, onCiteClick, onFollowUp }) {
  const isUser = msg.role === 'user'
  const [citedCards, setCitedCards] = useState([])
  const structured = msg.structured_answer
  const isError = msg.error

  useEffect(() => {
    if (isUser || !msg.cited_card_ids?.length) return
    let cancelled = false
    Promise.all(msg.cited_card_ids.map((id) => getCitedCard(id).catch(() => null)))
      .then((cards) => {
        if (!cancelled) setCitedCards(cards.filter(Boolean))
      })
    return () => { cancelled = true }
  }, [msg.cited_card_ids, isUser])

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%] px-4 py-3 bg-neutral-900 text-white rounded-2xl rounded-br-sm text-sm leading-relaxed whitespace-pre-wrap">
          {msg.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] w-full">
        {msg.thinking_text && (
          <ThinkingBlock text={msg.thinking_text} />
        )}
        {/* V9: 模式徽标，知识库回答与自由闲聊一眼可辨 */}
        <div className="flex items-center gap-2 mb-1.5">
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${mode === 'kb' ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-500'}`}>
            {mode === 'kb' ? '知识库回答' : 'AI 搭子'}
          </span>
          {mode === 'kb' && citedCards.length > 0 && (
            <span className="text-[11px] text-neutral-400">基于 {citedCards.length} 张卡片</span>
          )}
        </div>

        {/* V9: 知识库回答把引用放在答案上方，先看到依据再读内容 */}
        {mode === 'kb' && !structured && citedCards.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {citedCards.map((c) => (
              <button
                key={c.id}
                onClick={() => onCiteClick(c.id)}
                className="px-2 py-1 bg-white text-neutral-700 rounded text-xs border border-neutral-200 hover:border-neutral-900 hover:text-neutral-900 transition-colors"
                title={c.one_liner || c.title}
              >
                {c.title} ↗
              </button>
            ))}
          </div>
        )}

        {structured ? (
          <StructuredAnswer data={structured} citedCards={citedCards} onCiteClick={onCiteClick} />
        ) : (
          <div
            className={`px-4 py-3 rounded-2xl rounded-bl-sm border text-sm leading-relaxed ${
              isError
                ? 'bg-red-50 border-red-100 text-red-700'
                : 'bg-neutral-50 border-neutral-100 text-neutral-800'
            }`}
          >
            <MarkdownLite text={msg.content} />
          </div>
        )}

        {!structured && mode !== 'kb' && citedCards.length > 0 && (
          <div className="mt-2 px-4">
            <div className="text-xs text-neutral-400 mb-1.5">引用知识卡片（点击查看原文）</div>
            <div className="flex flex-wrap gap-1.5">
              {citedCards.map((c) => (
                <button
                  key={c.id}
                  onClick={() => onCiteClick(c.id)}
                  className="px-2 py-1 bg-white text-neutral-700 rounded text-xs border border-neutral-200 hover:border-neutral-900 hover:text-neutral-900 transition-colors"
                  title={c.one_liner || c.title}
                >
                  {c.title} ↗
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 操作行：复制 + 快捷追问 */}
        {!isError && (
          <div className="mt-2 px-4 flex flex-wrap items-center gap-2">
            <button
              onClick={() => onCopy(msg.id || msg.content, msg.content)}
              className="text-[11px] text-neutral-400 hover:text-neutral-700 transition-colors"
            >
              {copiedId === (msg.id || msg.content) ? '✓ 已复制' : '复制'}
            </button>
            <div className="w-px h-3 bg-neutral-200" />
            {(FOLLOW_UPS[mode] || []).map((q) => (
              <button
                key={q}
                onClick={() => onFollowUp(q)}
                className="px-2.5 py-1 text-[11px] text-neutral-500 border border-dashed border-neutral-300 rounded-full hover:border-neutral-900 hover:text-neutral-900 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ThinkingBlock({ text }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="text-xs text-neutral-400 hover:text-neutral-600 transition"
      >
        💭 AI 思考过程 {open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="mt-2 p-3 bg-neutral-50 border border-neutral-100 rounded-xl max-h-72 overflow-y-auto">
          <p className="text-xs text-neutral-500 whitespace-pre-wrap leading-relaxed">
            {text}
          </p>
        </div>
      )}
    </div>
  )
}

function StructuredAnswer({ data, citedCards, onCiteClick }) {
  const keyPoints = data.key_points?.length
    ? data.key_points
    : (data.core_points || []).map((p) =>
        typeof p === 'string' ? { point: p, detail: '' } : p
      )
  const adviceList = Array.isArray(data.action_advice)
    ? data.action_advice
    : data.action_advice ? [data.action_advice] : []

  return (
    <div className="px-5 py-4 bg-neutral-50 border border-neutral-100 rounded-2xl rounded-bl-sm space-y-6">
      {data.conclusion && (
        <div>
          <SectionLabel>结论</SectionLabel>
          <div className="text-[15px] text-neutral-900 leading-7">
            <MarkdownLite text={data.conclusion} />
          </div>
        </div>
      )}

      {keyPoints.length > 0 && (
        <div>
          <SectionLabel>核心观点</SectionLabel>
          <div className="space-y-4">
            {keyPoints.map((p, i) => {
              const point = typeof p === 'string' ? p : p.point
              const detail = typeof p === 'object' && p.detail ? p.detail : ''
              return (
                <div key={i} className="flex gap-3">
                  <span className="w-5 h-5 rounded-full bg-neutral-900 text-white text-[11px] font-medium flex items-center justify-center shrink-0 mt-1">
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-neutral-900 leading-6">
                      <MarkdownLite text={point} />
                    </div>
                    {detail && (
                      <div className="text-sm text-neutral-500 leading-7 mt-0.5">
                        <MarkdownLite text={detail} />
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {data.extended_thinking && (
        <div>
          <SectionLabel>延伸思考</SectionLabel>
          <div className="text-sm text-neutral-600 leading-7">
            <MarkdownLite text={data.extended_thinking} />
          </div>
        </div>
      )}

      {adviceList.length > 0 && (
        <div className="pt-4 border-t border-neutral-100">
          <SectionLabel>行动建议</SectionLabel>
          <div className="space-y-2.5">
            {adviceList.map((a, i) => (
              <div key={i} className="flex gap-3">
                <span className="w-5 h-5 rounded-full border border-neutral-300 text-neutral-500 text-[11px] flex items-center justify-center shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <div className="flex-1 text-sm text-neutral-700 leading-7">
                  <MarkdownLite text={a} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {citedCards.length > 0 && (
        <div className="pt-3 border-t border-neutral-100">
          <div className="text-xs text-neutral-400 mb-1.5">引用知识卡片（点击查看原文）</div>
          <div className="flex flex-wrap gap-1.5">
            {citedCards.map((c) => (
              <button
                key={c.id}
                onClick={() => onCiteClick(c.id)}
                className="px-2 py-1 bg-white text-neutral-700 rounded text-xs border border-neutral-200 hover:border-neutral-900 hover:text-neutral-900 transition-colors"
                title={c.one_liner || c.title}
              >
                {c.title} ↗
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SectionLabel({ children }) {
  return (
    <div className="text-xs text-neutral-400 font-medium uppercase tracking-wider mb-2.5">
      {children}
    </div>
  )
}

function ScopeOption({ active, label, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-1.5 text-sm hover:bg-neutral-50 transition-colors ${
        active ? 'text-neutral-900 font-medium' : 'text-neutral-600'
      }`}
    >
      {label}
    </button>
  )
}

function scopeToLabel(scope, spaces) {
  if (!scope || scope.type === 'all') return '全部知识'
  if (scope.type === 'space') {
    const sp = (spaces || []).find((x) => x.id === scope.value)
    return sp ? `空间：${sp.name}` : '全部知识'
  }
  if (scope.type === 'domain') return `领域：${scope.value}`
  if (scope.type === 'tags') return `标签：${(scope.value || []).join(', ')}`
  return '全部知识'
}
