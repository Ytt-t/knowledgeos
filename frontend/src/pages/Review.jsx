import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  listCards,
  listSpaces,
  generateReviewQuestions,
  evaluateReviewAnswers,
  getReviewWeakPoints,
  listWrongQuestions,
} from '../api'

const TYPE_LABEL = {
  concept: '概念',
  application: '应用',
  judgment: '判断',
  open: '简答',
}
const DIFFICULTY_LABEL = {
  easy: '简单',
  medium: '中等',
  hard: '困难',
}

// PRD V3.0 复习四模式
const REVIEW_MODES = [
  { key: 'understand', label: '理解模式', desc: '概念题为主，检验是否真正理解' },
  { key: 'apply', label: '应用模式', desc: '应用题为主，把知识用到具体场景' },
  { key: 'interview', label: '面试模式', desc: '高频考点 + 深度问答' },
  { key: 'quick', label: '快速检测', desc: '判断题为主，快速过一遍' },
]

const isOpenQuestion = (type) => type === 'application' || type === 'open'

// 将 0-1 或 0-100 的数值统一归一到 0-100
const normalize = (v) => {
  if (typeof v !== 'number' || isNaN(v)) return 0
  if (v <= 1) return v * 100
  return Math.max(0, Math.min(100, v))
}

export default function Review() {
  const navigate = useNavigate()
  const location = useLocation()
  const [cards, setCards] = useState([])
  const [spaces, setSpaces] = useState([])
  const [weakPoints, setWeakPoints] = useState([])
  const [wrongDueCount, setWrongDueCount] = useState(0)

  // 复习范围设置（V6: all | recent | space | cards | weak）
  // 支持从成长页/知识页跳转预选范围（薄弱知识 / 指定卡片）
  const [scopeType, setScopeType] = useState(
    () => location.state?.scopeType || 'all'
  )
  const [selectedSpaceId, setSelectedSpaceId] = useState('')
  const [selectedCardIds, setSelectedCardIds] = useState(
    () => location.state?.cardIds || []
  )
  // V6: 智能题量（默认）或自定义数量
  const [countMode, setCountMode] = useState('smart') // smart | custom
  const [customCount, setCustomCount] = useState(10)
  const [reviewMode, setReviewMode] = useState('understand') // PRD V3.0 四模式

  // 题目与答题状态
  const [questions, setQuestions] = useState([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [selectedAnswer, setSelectedAnswer] = useState(null)
  const [openAnswer, setOpenAnswer] = useState('')
  const [showResult, setShowResult] = useState(false)
  const [answers, setAnswers] = useState([])
  const [phase, setPhase] = useState('intro') // intro | quiz | result

  // 加载 / 评估状态
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [evaluation, setEvaluation] = useState(null)
  const [evaluating, setEvaluating] = useState(false)
  const [lastScope, setLastScope] = useState(null) // 评估落库用

  useEffect(() => {
    listCards({ limit: 200 }).then(setCards).catch(() => {})
    listSpaces().then((d) => setSpaces(d.spaces || [])).catch(() => {})
    getReviewWeakPoints().then((d) => setWeakPoints(d.weak_points || [])).catch(() => {})
    // V7: 错题本待攻克数（入口徽标）
    listWrongQuestions(true).then((d) => setWrongDueCount(d.due_count || 0)).catch(() => {})
  }, [])

  // 进入 result 阶段后触发 AI 评估
  useEffect(() => {
    if (phase !== 'result') return
    if (evaluation || evaluating) return
    if (answers.length === 0) return
    setEvaluating(true)
    evaluateReviewAnswers({
      mode: reviewMode,
      scope: lastScope,
      submissions: answers.map((a) => ({
        question: a.question,
        user_answer: a.user_answer,
        correct_answer: a.correct_answer,
        card_id: a.card_id,
        is_correct: a.isCorrect,  // V7: 错题本收集（开放题为 null 后端跳过）
      })),
    })
      .then((res) => setEvaluation(res))
      .catch(() => {})
      .finally(() => setEvaluating(false))
  }, [phase]) // eslint-disable-line react-hooks/exhaustive-deps

  // === 范围构建与校验（V6） ===
  // 字段名与后端 ReviewScope 对齐：
  //   scope_type: "all" | "space" | "card_ids" | "recent" | "weak"
  //   question_count: null = 智能题量（按所选卡片数自适应）
  const buildScope = () => {
    const base = {
      mode: reviewMode,
      question_count: countMode === 'custom' ? Math.max(1, Math.min(30, customCount || 5)) : null,
    }
    if (scopeType === 'space') {
      return { ...base, scope_type: 'space', space_id: Number(selectedSpaceId) }
    }
    if (scopeType === 'cards') {
      return { ...base, scope_type: 'card_ids', card_ids: selectedCardIds }
    }
    if (scopeType === 'recent') return { ...base, scope_type: 'recent' }
    if (scopeType === 'weak') return { ...base, scope_type: 'weak' }
    return { ...base, scope_type: 'all' }
  }

  const canGenerate = () => {
    if (loading) return false
    if (scopeType === 'space') return !!selectedSpaceId
    if (scopeType === 'cards') return selectedCardIds.length > 0
    if (scopeType === 'weak') return weakAvailable()
    return true
  }

  // 薄弱知识可用性：有历史薄弱点 或 有未掌握卡片
  const weakAvailable = () => {
    if (weakPoints.length > 0) return true
    return cards.some((c) => !c.learning_status || c.learning_status === 'new' || c.learning_status === 'learning')
  }

  const handleGenerate = async () => {
    if (!canGenerate()) return
    setLoading(true)
    setError('')
    try {
      const scope = buildScope()
      const data = await generateReviewQuestions(scope)
      const qs = data.questions || []
      if (qs.length === 0) {
        setError(data.message || '未能生成复习题，请稍后重试')
        return
      }
      // V8: 选项由 AI 直接生成（4 选项含高迷惑干扰项）；判断题兜底「对/错」
      const prepared = qs.map((q) => ({
        ...q,
        options: isOpenQuestion(q.type) ? null : (q.options?.length >= 2 ? q.options : ['对', '错']),
      }))
      setQuestions(prepared)
      setCurrentIdx(0)
      setSelectedAnswer(null)
      setOpenAnswer('')
      setShowResult(false)
      setAnswers([])
      setEvaluation(null)
      setLastScope(scope)
      setPhase('quiz')
    } catch (e) {
      setError('生成复习题失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  const startQuiz = () => {
    if (questions.length === 0) return
    setPhase('quiz')
    setCurrentIdx(0)
    setSelectedAnswer(null)
    setOpenAnswer('')
    setShowResult(false)
    setAnswers([])
    setEvaluation(null)
  }

  const handleSubmit = () => {
    const q = questions[currentIdx]
    const open = isOpenQuestion(q.type)
    let userAnswer
    let isCorrect = null

    if (open) {
      userAnswer = openAnswer.trim()
      if (!userAnswer) return
      // 简答题由 AI 评估，本地不做正误判定
    } else {
      userAnswer = selectedAnswer
      if (userAnswer === null) return
      isCorrect = userAnswer === q.answer
    }

    setShowResult(true)
    setAnswers((prev) => {
      const filtered = prev.filter((a) => a.idx !== currentIdx)
      return [
        ...filtered,
        {
          idx: currentIdx,
          question: q.question,
          user_answer: userAnswer,
          correct_answer: q.answer,
          card_id: q.card_id,
          card_title: q.card_title,
          type: q.type,
          isCorrect,
        },
      ]
    })
  }

  const handleNext = () => {
    if (currentIdx < questions.length - 1) {
      setCurrentIdx(currentIdx + 1)
      setSelectedAnswer(null)
      setOpenAnswer('')
      setShowResult(false)
    } else {
      setPhase('result')
    }
  }

  const toggleCard = (id) => {
    setSelectedCardIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  // ===================== Intro 界面 =====================
  if (phase === 'intro') {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="py-10">
          <div className="text-center mb-10">
            <div className="text-5xl text-neutral-200 mb-6">◈</div>
            <h1 className="text-2xl font-semibold text-neutral-900 mb-2">学习复习</h1>
            <p className="text-sm text-neutral-500">
              AI 根据你的知识卡片生成个性化复习题，检验掌握程度
            </p>
          </div>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-neutral-200 border-t-neutral-900 rounded-full animate-spin mb-4" />
              <p className="text-sm text-neutral-500">AI 正在生成复习题…</p>
            </div>
          ) : cards.length === 0 ? (
            <div className="border border-dashed border-neutral-200 rounded-xl py-12 px-6 text-center">
              <p className="text-sm text-neutral-400 mb-2">还没有知识卡片</p>
              <p className="text-xs text-neutral-300 mb-4">上传内容后即可生成复习题</p>
              <button
                onClick={() => navigate('/')}
                className="text-xs text-neutral-600 hover:text-neutral-900 underline underline-offset-2"
              >
                去上传内容 →
              </button>
            </div>
          ) : (
            <div className="space-y-8">
              {/* 复习模式（PRD V3.0 四模式） */}
              <div>
                <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">
                  复习模式
                </h2>
                <div className="grid grid-cols-2 gap-2">
                  {REVIEW_MODES.map((m) => (
                    <button
                      key={m.key}
                      onClick={() => setReviewMode(m.key)}
                      className={`text-left p-3 rounded-lg border transition-all ${
                        reviewMode === m.key
                          ? 'border-neutral-900 bg-neutral-50'
                          : 'border-neutral-200 hover:border-neutral-400'
                      }`}
                    >
                      <div className="text-sm font-medium text-neutral-900">{m.label}</div>
                      <div className="text-xs text-neutral-400 mt-0.5">{m.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* 复习范围（V6: 全部/最近/空间/卡片/薄弱） */}
              <div>
                <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">
                  复习范围
                </h2>
                <div className="space-y-2">
                  <ScopeOption
                    active={scopeType === 'all'}
                    onClick={() => setScopeType('all')}
                    label="全部知识"
                    desc="覆盖所有卡片"
                  />
                  <ScopeOption
                    active={scopeType === 'recent'}
                    onClick={() => setScopeType('recent')}
                    label="最近学习"
                    desc="近 7 天新增的知识"
                  />
                  <ScopeOption
                    active={scopeType === 'space'}
                    onClick={() => setScopeType('space')}
                    label="指定知识空间"
                    desc="选择一个空间出题"
                  >
                    {scopeType === 'space' && (
                      <select
                        value={selectedSpaceId}
                        onChange={(e) => setSelectedSpaceId(e.target.value)}
                        className="mt-3 w-full px-3 py-2 border border-neutral-200 rounded-lg text-sm text-neutral-800 outline-none focus:border-neutral-400 bg-white"
                      >
                        <option value="">请选择知识空间</option>
                        {spaces.map((sp) => (
                          <option key={sp.id} value={sp.id}>
                            {sp.name}（{sp.card_count} 张卡片）
                          </option>
                        ))}
                      </select>
                    )}
                  </ScopeOption>
                  <ScopeOption
                    active={scopeType === 'cards'}
                    onClick={() => setScopeType('cards')}
                    label="指定卡片"
                    desc="勾选要复习的卡片"
                  >
                    {scopeType === 'cards' && (
                      <div className="mt-3 max-h-56 overflow-y-auto border border-neutral-100 rounded-lg divide-y divide-neutral-100">
                        {cards.map((c) => (
                          <label
                            key={c.id}
                            className="flex items-center gap-3 px-3 py-2 hover:bg-neutral-50 cursor-pointer"
                          >
                            <input
                              type="checkbox"
                              checked={selectedCardIds.includes(c.id)}
                              onChange={() => toggleCard(c.id)}
                              className="accent-neutral-900 w-4 h-4"
                            />
                            <span className="text-sm text-neutral-700 flex-1 truncate">
                              {c.title}
                            </span>
                            <span className="text-xs text-neutral-400 shrink-0">{c.domain || '未分类'}</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </ScopeOption>
                  <ScopeOption
                    active={scopeType === 'weak'}
                    onClick={() => weakAvailable() && setScopeType('weak')}
                    label={weakAvailable() ? '薄弱知识' : '薄弱知识（暂无可复习内容）'}
                    desc={weakAvailable()
                      ? '历史答题薄弱点 + 未掌握卡片'
                      : '完成一次复习后，AI 会分析出你的薄弱点'}
                  />
                </div>
              </div>

              {/* 题目数量（V6: 智能题量） */}
              <div>
                <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">
                  题目数量
                </h2>
                <div className="space-y-2">
                  <label className="flex items-center gap-3 border border-neutral-200 rounded-xl p-3 cursor-pointer hover:border-neutral-400 transition-colors">
                    <input
                      type="radio"
                      checked={countMode === 'smart'}
                      onChange={() => setCountMode('smart')}
                      className="accent-neutral-900 w-4 h-4"
                    />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-neutral-900">智能题量</div>
                      <div className="text-xs text-neutral-400 mt-0.5">
                        按所选范围自动出题（每张卡片 1-2 题，3-20 题）
                      </div>
                    </div>
                  </label>
                  <label className="flex items-center gap-3 border border-neutral-200 rounded-xl p-3 cursor-pointer hover:border-neutral-400 transition-colors">
                    <input
                      type="radio"
                      checked={countMode === 'custom'}
                      onChange={() => setCountMode('custom')}
                      className="accent-neutral-900 w-4 h-4"
                    />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-neutral-900">自定义数量</div>
                    </div>
                    {countMode === 'custom' && (
                      <input
                        type="number"
                        min={1}
                        max={30}
                        value={customCount}
                        onChange={(e) => setCustomCount(Number(e.target.value))}
                        className="w-20 px-3 py-2 border border-neutral-200 rounded-lg text-sm text-neutral-800 outline-none focus:border-neutral-400"
                      />
                    )}
                  </label>
                </div>
              </div>

              {/* V7: 错题本入口 */}
              <button
                onClick={() => navigate('/wrong')}
                className="w-full flex items-center gap-4 border border-neutral-200 rounded-xl p-4 hover:border-neutral-400 transition-colors text-left"
              >
                <span className="text-2xl">📕</span>
                <div className="flex-1">
                  <div className="text-sm font-medium text-neutral-900">AI 错题本</div>
                  <div className="text-xs text-neutral-400 mt-0.5">
                    答错的题自动收集，按遗忘曲线安排重考
                  </div>
                </div>
                {wrongDueCount > 0 ? (
                  <span className="px-2.5 py-1 bg-neutral-900 text-white rounded-full text-xs font-medium">
                    {wrongDueCount} 题待攻克
                  </span>
                ) : (
                  <span className="text-xs text-neutral-300">暂无错题</span>
                )}
              </button>

              {error && (
                <p className="text-xs text-red-500 text-center">{error}</p>
              )}

              <button
                onClick={handleGenerate}
                disabled={!canGenerate()}
                className="w-full py-3 bg-neutral-900 text-white rounded-xl font-medium text-sm hover:bg-neutral-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                生成复习题
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ===================== Result 界面 =====================
  if (phase === 'result') {
    const total = answers.length
    const mcCorrect = answers.filter((a) => !isOpenQuestion(a.type) && a.isCorrect).length
    const displayCorrect = evaluation?.correct_count ?? mcCorrect
    const displayTotal = evaluation?.total ?? total
    const score = evaluation?.score
    const scoreNum = typeof score === 'number' ? Math.round(normalize(score)) : null

    return (
      <div className="max-w-2xl mx-auto">
        <div className="py-10">
          {evaluating ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-8 h-8 border-2 border-neutral-200 border-t-neutral-900 rounded-full animate-spin mb-4" />
              <p className="text-sm text-neutral-500">AI 正在评估你的答题…</p>
            </div>
          ) : evaluation ? (
            <>
              {/* 总分 */}
              <div className="text-center mb-8">
                <div className="text-5xl text-neutral-200 mb-4">◈</div>
                <h1 className="text-3xl font-semibold text-neutral-900 mb-2">
                  {scoreNum !== null ? `${scoreNum} 分` : `${displayCorrect} / ${displayTotal}`}
                </h1>
                <p className="text-sm text-neutral-500 mb-1">
                  答对 {displayCorrect} / {displayTotal} 题
                </p>
                {evaluation.feedback && (
                  <p className="text-xs text-neutral-400 mt-3 max-w-md mx-auto leading-relaxed">
                    {evaluation.feedback}
                  </p>
                )}
              </div>

              {/* 维度评分 */}
              <div className="space-y-4 mb-10">
                <ScoreBar label="准确性" value={evaluation.correctness} />
                <ScoreBar label="完整性" value={evaluation.completeness} />
                <ScoreBar label="理解度" value={evaluation.understanding} />
              </div>

              {/* 薄弱点 */}
              {evaluation.weak_points?.length > 0 && (
                <div className="mb-10">
                  <h2 className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-3">
                    薄弱点与建议
                  </h2>
                  <div className="space-y-2">
                    {evaluation.weak_points.map((wp, i) => {
                      const point =
                        typeof wp === 'string' ? wp : wp.point || wp.title || wp.topic || ''
                      const suggestion =
                        typeof wp === 'string'
                          ? ''
                          : wp.suggestion || wp.advice || wp.action || ''
                      return (
                        <div
                          key={i}
                          className="p-4 bg-neutral-50 rounded-lg border border-neutral-100"
                        >
                          {point && (
                            <p className="text-sm text-neutral-800 font-medium mb-1">{point}</p>
                          )}
                          {suggestion && (
                            <p className="text-xs text-neutral-500 leading-relaxed">
                              → {suggestion}
                            </p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* 操作按钮 */}
              <div className="flex gap-3 justify-center mb-10">
                <button
                  onClick={startQuiz}
                  className="px-6 py-2.5 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 transition-colors"
                >
                  再测一次
                </button>
                <button
                  onClick={() => setPhase('intro')}
                  className="px-6 py-2.5 border border-neutral-200 text-neutral-700 rounded-lg text-sm font-medium hover:bg-neutral-50 transition-colors"
                >
                  返回设置
                </button>
              </div>
            </>
          ) : (
            <div className="text-center py-20">
              <p className="text-sm text-neutral-500 mb-4">评估失败，请重试</p>
              <button
                onClick={startQuiz}
                className="px-6 py-2.5 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 transition-colors"
              >
                再测一次
              </button>
            </div>
          )}

          {/* 答题详情（V8: 逐题回顾 —— 无论 AI 评分是否成功都展示原题/你的答案/正确答案） */}
          <div className="border-t border-neutral-100 pt-6">
            <h2 className="text-sm font-semibold text-neutral-900 mb-1">
              逐题回顾
            </h2>
            <p className="text-xs text-neutral-400 mb-4">
              错题标红，附正确答案 —— 答错的题会自动收进错题本
            </p>
            <div className="space-y-3">
              {answers.map((a, i) => {
                const open = isOpenQuestion(a.type)
                const showCorrect = open || !a.isCorrect
                return (
                  <div
                    key={i}
                    className={`p-4 rounded-lg border ${
                      open
                        ? 'border-neutral-200 bg-white'
                        : a.isCorrect
                          ? 'border-neutral-200 bg-neutral-50'
                          : 'border-red-200 bg-red-50'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span
                        className={`text-sm shrink-0 ${
                          open
                            ? 'text-neutral-400'
                            : a.isCorrect
                              ? 'text-neutral-900'
                              : 'text-red-600'
                        }`}
                      >
                        {open ? '○' : a.isCorrect ? '✓' : '✗'}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-neutral-800 font-medium mb-1">{a.question}</p>
                        <div className="text-xs text-neutral-500 mt-1">
                          <span className="text-neutral-400">你的答案：</span>
                          <span className="whitespace-pre-wrap">{a.user_answer}</span>
                        </div>
                        {showCorrect && (
                          <div className="text-xs text-neutral-700 mt-1">
                            <span className="text-neutral-400">
                              {open ? '参考答案' : '正确答案'}：
                            </span>
                            <span className="whitespace-pre-wrap">{a.correct_answer}</span>
                          </div>
                        )}
                        {a.card_title && (
                          <div className="text-xs text-neutral-400 mt-1.5">来自：{a.card_title}</div>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ===================== Quiz 界面 =====================
  const q = questions[currentIdx]
  const open = isOpenQuestion(q.type)
  const progress = ((currentIdx + 1) / questions.length) * 100
  const canSubmit = open ? !!openAnswer.trim() : selectedAnswer !== null

  return (
    <div className="max-w-2xl mx-auto">
      {/* 进度条 */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-neutral-400">
            第 {currentIdx + 1} / {questions.length} 题
          </span>
          <div className="flex items-center gap-2">
            {q.type && (
              <span className="text-xs px-2 py-0.5 bg-neutral-100 text-neutral-600 rounded">
                {TYPE_LABEL[q.type] || q.type}
              </span>
            )}
            {q.difficulty && (
              <span className="text-xs text-neutral-400">
                {DIFFICULTY_LABEL[q.difficulty] || q.difficulty}
              </span>
            )}
          </div>
        </div>
        <div className="h-1 bg-neutral-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-neutral-900 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* 题目 */}
      <div className="bg-white border border-neutral-200 rounded-xl p-8">
        <p className="text-xs text-neutral-400 mb-3">来自：{q.card_title}</p>
        <h2 className="text-lg font-medium text-neutral-900 mb-6 leading-relaxed">{q.question}</h2>

        {open ? (
          /* 简答题：textarea */
          <div>
            <textarea
              value={openAnswer}
              onChange={(e) => !showResult && setOpenAnswer(e.target.value)}
              disabled={showResult}
              placeholder="请输入你的答案…"
              rows={5}
              className="w-full px-4 py-3 border border-neutral-200 rounded-lg text-sm text-neutral-800 outline-none focus:border-neutral-400 resize-none disabled:bg-neutral-50 disabled:cursor-not-allowed"
            />
            {showResult && (
              <div className="mt-4 p-4 bg-neutral-50 rounded-lg border border-neutral-100">
                <p className="text-xs font-semibold text-neutral-400 uppercase tracking-wider mb-2">
                  参考答案
                </p>
                <p className="text-sm text-neutral-800 leading-relaxed whitespace-pre-wrap">
                  {q.answer}
                </p>
              </div>
            )}
          </div>
        ) : (
          /* 选择题：选项 */
          <div className="space-y-2">
            {q.options.map((opt, i) => {
              const isSelected = selectedAnswer === opt
              const isCorrect = opt === q.answer
              let style =
                'border-neutral-200 text-neutral-700 hover:border-neutral-400 hover:bg-neutral-50'

              if (showResult) {
                if (isCorrect) {
                  style = 'border-neutral-900 bg-neutral-900 text-white'
                } else if (isSelected && !isCorrect) {
                  style = 'border-red-300 bg-red-50 text-red-700'
                } else {
                  style = 'border-neutral-200 text-neutral-400'
                }
              } else if (isSelected) {
                style = 'border-neutral-900 bg-neutral-50 text-neutral-900'
              }

              return (
                <button
                  key={i}
                  onClick={() => !showResult && setSelectedAnswer(opt)}
                  disabled={showResult}
                  className={`w-full text-left px-4 py-3 rounded-lg border text-sm transition-all ${style}`}
                >
                  <span className="text-xs mr-2 opacity-60">{String.fromCharCode(65 + i)}</span>
                  {opt}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* 操作按钮（V8: 显式「提交并打分」） */}
      <div className="flex justify-between mt-6">
        <button
          onClick={() => setPhase('result')}
          className="px-4 py-2 text-xs text-neutral-500 hover:text-neutral-900 border border-neutral-200 rounded-lg hover:border-neutral-400 transition"
        >
          提交并打分 →
        </button>
        {!showResult ? (
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="px-6 py-2.5 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            提交答案
          </button>
        ) : (
          <button
            onClick={handleNext}
            className="px-6 py-2.5 bg-neutral-900 text-white rounded-lg text-sm font-medium hover:bg-neutral-800 transition-colors"
          >
            {currentIdx < questions.length - 1 ? '下一题 →' : '查看结果 →'}
          </button>
        )}
      </div>
    </div>
  )
}

// === 范围选项卡片 ===
function ScopeOption({ active, onClick, label, desc, children }) {
  return (
    <div
      onClick={onClick}
      className={`border rounded-xl p-4 cursor-pointer transition-colors ${
        active
          ? 'border-neutral-900 bg-neutral-50'
          : 'border-neutral-200 hover:border-neutral-400'
      }`}
    >
      <div className="flex items-center gap-3">
        <span
          className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${
            active ? 'border-neutral-900' : 'border-neutral-300'
          }`}
        >
          {active && <span className="w-2 h-2 rounded-full bg-neutral-900" />}
        </span>
        <div className="flex-1">
          <div className="text-sm font-medium text-neutral-900">{label}</div>
          <div className="text-xs text-neutral-400">{desc}</div>
        </div>
      </div>
      {children && (
        <div onClick={(e) => e.stopPropagation()}>{children}</div>
      )}
    </div>
  )
}

// === 维度评分条 ===
function ScoreBar({ label, value }) {
  const v = normalize(value)
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-neutral-600">{label}</span>
        <span className="text-xs text-neutral-400">{Math.round(v)}</span>
      </div>
      <div className="h-2 bg-neutral-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-neutral-900 rounded-full transition-all"
          style={{ width: `${v}%` }}
        />
      </div>
    </div>
  )
}

// V8: buildOptions 已删除 —— 选项由 AI 出题时直接生成（高迷惑干扰项），
// 前端不再用"其他题目的答案"硬拼干扰项（那是题目没有含金量的元凶）。
