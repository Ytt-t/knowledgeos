import { useEffect, useState } from 'react'
import { updateCard, submitFeedback, checkQuickTestAnswer } from '../api'
import { CONTENT_TYPE_LABEL } from '../utils/status'
import MarkdownLite from './MarkdownLite'

// V6.3.1: 卡片详情内容区（知识管理抽屉 + 全屏知识页共用）
// ChatGPT 式排版：大字号、大行距、粗体重点、数字圆点分点、次要区块折叠
// 职责：渲染卡片全部详情区块 + 内部交互；不含面板头部与底部操作栏（由宿主页面渲染）

const PLATFORM_LABEL = {
  bilibili_video: 'B站',
  douyin_video: '抖音',
  xiaohongshu_video: '小红书',
  pdf: 'PDF文档',
  docx: 'Word文档',
  txt: '笔记',
  image: '图片',
}

export default function CardContent({ card, spaces, onCardChange, onOpenCard, onRedistill, redistilling }) {
  const [showRawText, setShowRawText] = useState(false)
  const [showStructure, setShowStructure] = useState(false)
  const [showQuickTest, setShowQuickTest] = useState(false)
  const [feedback, setFeedback] = useState(card.user_feedback || null)
  const [testAnswers, setTestAnswers] = useState({})

  useEffect(() => {
    setShowRawText(false)
    setShowStructure(false)
    setShowQuickTest(false)
    setFeedback(card.user_feedback || null)
    setTestAnswers({})
  }, [card.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!card) return null

  const platformLabel = PLATFORM_LABEL[card.source_platform] || card.source_platform || card.content_type
  const summary = card.ai_summary?.summary || ''

  const handleFeedback = async (fb) => {
    try {
      await submitFeedback(card.id, fb)
      setFeedback(fb)
    } catch (e) {
      console.error('反馈失败', e)
    }
  }

  const handleRevealAnswer = async (index) => {
    if (testAnswers[index]) return
    try {
      const res = await checkQuickTestAnswer(card.id, index)
      setTestAnswers((prev) => ({ ...prev, [index]: res.answer }))
    } catch (e) {
      console.error('获取答案失败', e)
    }
  }

  const handleToggleImportance = async () => {
    const next = card.importance === 'high' ? null : 'high'
    await updateCard(card.id, { importance: next })
    onCardChange({ ...card, importance: next })
  }

  const handleMoveSpace = async (e) => {
    const v = e.target.value
    await updateCard(card.id, { space_id: v ? Number(v) : null })
    onCardChange({ ...card, space_id: v ? Number(v) : null })
  }

  return (
    <div className="space-y-10">
      {/* 标题 */}
      <div>
        <h1 className="text-2xl font-semibold text-neutral-900 leading-snug tracking-tight">
          {card.title}
        </h1>
        {/* 元信息（紧凑） */}
        <div className="text-xs text-neutral-400 flex flex-wrap gap-1.5 items-center mt-3">
          <span>{CONTENT_TYPE_LABEL[card.content_type] || card.content_type}</span>
          <span>·</span>
          <span>来自 {platformLabel}</span>
          {card.source_url && (
            <>
              <span>·</span>
              <a href={card.source_url} target="_blank" rel="noopener noreferrer"
                className="text-neutral-500 hover:text-neutral-700 underline underline-offset-2">
                原始链接 ↗
              </a>
            </>
          )}
          <span>·</span>
          <span>{(card.created_at || '').slice(0, 10)}</span>
        </div>
      </div>

      {/* 整理操作行（空间 / 重要 / 学习状态 / 标签 —— 紧凑一行） */}
      <div className="space-y-3 pt-4 border-t border-neutral-100">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-neutral-400 shrink-0">知识空间</span>
            <select
              value={card.space_id || ''}
              onChange={handleMoveSpace}
              className="text-xs px-2 py-1.5 border border-neutral-200 rounded-lg text-neutral-700 outline-none bg-white cursor-pointer"
            >
              <option value="">未分类</option>
              {spaces.map((sp) => (
                <option key={sp.id} value={sp.id}>{sp.name}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleToggleImportance}
            className={`px-3 py-1.5 rounded-lg text-xs border transition ${
              card.importance === 'high'
                ? 'bg-neutral-900 text-white border-neutral-900'
                : 'border-neutral-200 text-neutral-600 hover:border-neutral-400'
            }`}
          >
            {card.importance === 'high' ? '★ 重要' : '☆ 标记重要'}
          </button>
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-neutral-400">学习状态</span>
            {[
              { key: 'new', label: '未学习' },
              { key: 'learning', label: '学习中' },
              { key: 'mastered', label: '已掌握' },
            ].map((s) => (
              <button
                key={s.key}
                onClick={() => updateCard(card.id, { learning_status: s.key }).then(() => {
                  onCardChange({ ...card, learning_status: s.key })
                })}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  (card.learning_status || 'new') === s.key
                    ? s.key === 'mastered'
                      ? 'bg-neutral-900 text-white'
                      : s.key === 'learning'
                        ? 'bg-neutral-200 text-neutral-700'
                        : 'bg-neutral-50 text-neutral-500 border border-neutral-200'
                    : 'text-neutral-400 hover:text-neutral-600'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(card.tags || []).map((t, i) => (
            <span key={i} className="px-2 py-0.5 bg-neutral-50 text-neutral-600 rounded text-xs">
              {t}
            </span>
          ))}
        </div>
      </div>

      {/* V6.3.2: 旧卡片一键用新蒸馏重做（旧格式：无分段/无粗体/无 detail） */}
      {onRedistill && card.raw_text && (
        <button
          onClick={onRedistill}
          disabled={redistilling}
          className="inline-flex items-center gap-2 text-xs text-neutral-500 hover:text-neutral-900 border border-neutral-200 hover:border-neutral-400 rounded-lg px-3 py-1.5 transition disabled:opacity-40"
        >
          {redistilling ? '✦ AI 正在重新总结…（1-3 分钟）' : '✦ AI 重新总结（让内容更深更清晰）'}
        </button>
      )}

      {/* 一句话理解（突出显示 —— 这是知识的灵魂） */}
      {card.one_liner && (
        <section>
          <SectionTitle>一句话理解</SectionTitle>
          <div className="text-base text-neutral-900 font-medium leading-8 bg-neutral-50 border border-neutral-100 rounded-xl px-5 py-4">
            {card.one_liner}
          </div>
        </section>
      )}

      {/* AI 总结（V6.3.1 新增：完整段落 + 粗体重点，ChatGPT 式阅读） */}
      {summary && (
        <section>
          <SectionTitle>AI 总结</SectionTitle>
          <div className="text-base text-neutral-800">
            <MarkdownLite text={summary} className="[&_p]:leading-8 [&_p]:my-4 [&_p:first-child]:mt-0" />
          </div>
        </section>
      )}

      {/* 核心要点（数字圆点 + 加粗标题 + 详细解释，分隔线分条） */}
      {card.core_points?.length > 0 && (
        <section>
          <SectionTitle>核心要点</SectionTitle>
          <div className="divide-y divide-neutral-100">
            {card.core_points.map((p, i) => {
              const point = typeof p === 'string' ? p : p.point
              const detail = typeof p === 'object' && p.detail ? p.detail : ''
              return (
                <div key={i} className="flex gap-4 py-5 first:pt-0 last:pb-0">
                  <span className="w-6 h-6 rounded-full bg-neutral-900 text-white text-xs font-medium flex items-center justify-center shrink-0 mt-1">
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[15px] font-semibold text-neutral-900 leading-7">{point}</div>
                    {detail && (
                      <div className="text-sm text-neutral-600 leading-7 mt-1.5">
                        <MarkdownLite text={detail} />
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 下一步学习建议 */}
      {card.next_steps?.length > 0 && (
        <section>
          <SectionTitle>下一步学习建议</SectionTitle>
          <div className="space-y-3">
            {card.next_steps.map((s, i) => (
              <div key={i} className="flex gap-3">
                <span className="w-5 h-5 rounded-full border border-neutral-300 text-neutral-500 text-[11px] flex items-center justify-center shrink-0 mt-1">
                  {i + 1}
                </span>
                <div className="flex-1 text-sm text-neutral-700 leading-7">
                  {typeof s === 'string' ? s : s.step || s.suggestion || ''}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 常见误区（正解突出） */}
      {card.misconceptions?.length > 0 && (
        <section>
          <SectionTitle>常见误区</SectionTitle>
          <div className="space-y-4">
            {card.misconceptions.map((m, i) => (
              <div key={i} className="border-l-2 border-neutral-200 pl-4">
                <div className="text-sm text-neutral-500 leading-7">
                  <span className="text-xs font-medium text-neutral-400 mr-1">误区</span>
                  {m.misconception}
                </div>
                <div className="text-sm text-neutral-900 font-medium leading-7 mt-1.5">
                  <span className="text-xs font-medium text-neutral-400 mr-1">正解</span>
                  {m.correction}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 实践应用（折叠区） */}
      {card.key_cases?.length > 0 && (
        <section>
          <SectionTitle>实践应用</SectionTitle>
          <div className="space-y-4">
            {card.key_cases.map((c, i) => (
              <div key={i} className="border-l-2 border-neutral-200 pl-4">
                <div className="text-sm font-medium text-neutral-900 leading-6">{c.scenario}</div>
                <div className="text-sm text-neutral-600 leading-7 mt-1">{c.application}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 知识结构（默认折叠 —— 次要信息） */}
      {card.knowledge_structure && Object.keys(card.knowledge_structure).length > 0 && (
        <section>
          <FoldButton open={showStructure} onClick={() => setShowStructure(!showStructure)} label="知识结构树" />
          {showStructure && (
            <div className="mt-3 space-y-2 text-sm">
              {Object.entries(card.knowledge_structure).map(([root, subs]) => (
                <div key={root}>
                  <div className="font-medium text-neutral-800 text-xs">{root}</div>
                  {Array.isArray(subs) && subs.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1 ml-2">
                      {subs.map((s, i) => (
                        <span key={i} className="px-1.5 py-0.5 bg-neutral-50 text-neutral-600 rounded text-[11px] border border-neutral-100">
                          {typeof s === 'string' ? s : s.name || '...'}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 快速测试（默认折叠） */}
      {card.quick_test?.length > 0 && (
        <section>
          <FoldButton open={showQuickTest} onClick={() => setShowQuickTest(!showQuickTest)} label={`快速测试（${card.quick_test.length} 题）`} />
          {showQuickTest && (
            <div className="mt-3 space-y-2">
              {card.quick_test.map((t, i) => (
                <div key={i} className="bg-neutral-50 rounded-lg p-3 border border-neutral-100">
                  <div className="text-sm text-neutral-700">
                    <span className="text-xs font-medium text-neutral-400 mr-1">Q{i + 1}</span>
                    {t.question}
                  </div>
                  {testAnswers[i] ? (
                    <div className="mt-2 pt-2 border-t border-neutral-200 text-sm text-neutral-600">
                      <span className="text-xs text-neutral-400">参考答案：</span>
                      {testAnswers[i]}
                    </div>
                  ) : (
                    <button
                      onClick={() => handleRevealAnswer(i)}
                      className="mt-2 text-xs text-neutral-500 hover:text-neutral-700"
                    >
                      查看答案 ▼
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 相关知识 */}
      {card.related_cards?.length > 0 && (
        <section>
          <SectionTitle>相关知识</SectionTitle>
          <div className="flex flex-wrap gap-1.5">
            {card.related_cards.map((r) => (
              <button
                key={r.id}
                onClick={() => onOpenCard(r.id)}
                className="px-2.5 py-1.5 bg-neutral-50 text-neutral-600 rounded-lg text-xs border border-neutral-100 cursor-pointer hover:bg-neutral-100 hover:text-neutral-900 transition"
                title={r.title}
              >
                {r.title}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* 质量反馈 */}
      <section className="pt-4 border-t border-neutral-100">
        <SectionTitle>这张卡片对你有帮助吗？</SectionTitle>
        <div className="flex gap-2 max-w-sm">
          <button
            onClick={() => handleFeedback('helpful')}
            className={`flex-1 py-2 rounded-lg text-xs border transition ${
              feedback === 'helpful'
                ? 'bg-neutral-900 text-white border-neutral-900'
                : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50'
            }`}
          >
            有帮助
          </button>
          <button
            onClick={() => handleFeedback('inaccurate')}
            className={`flex-1 py-2 rounded-lg text-xs border transition ${
              feedback === 'inaccurate'
                ? 'bg-neutral-200 text-neutral-700 border-neutral-300'
                : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50'
            }`}
          >
            不准确
          </button>
        </div>
      </section>

      {/* 原始内容（默认折叠） */}
      {card.raw_text && (
        <section>
          <FoldButton open={showRawText} onClick={() => setShowRawText(!showRawText)} label="查看原始内容" />
          {showRawText && (
            <div className="mt-3 p-3 bg-neutral-50 rounded-lg border border-neutral-100 max-h-60 overflow-y-auto">
              <p className="text-xs text-neutral-500 whitespace-pre-wrap leading-relaxed">
                {card.raw_text}
              </p>
            </div>
          )}
        </section>
      )}

    </div>
  )
}

function SectionTitle({ children }) {
  return (
    <h2 className="text-sm font-semibold text-neutral-900 mb-4">{children}</h2>
  )
}

function FoldButton({ open, onClick, label }) {
  return (
    <button
      onClick={onClick}
      className="text-sm font-semibold text-neutral-900 hover:text-neutral-600 transition"
    >
      {label} {open ? '▲' : '▼'}
    </button>
  )
}
