import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listWrongQuestions, submitWrongAnswer } from '../api'

// V7 AI 错题本：复习答错的题自动收集，按遗忘曲线安排重考
export default function WrongBook() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [reviewing, setReviewing] = useState(null) // 正在重考的错题 id
  const [revealed, setRevealed] = useState({})     // 已展开参考答案的 id 集合

  const load = () => {
    setLoading(true)
    listWrongQuestions(false)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const handleSubmit = async (id, isCorrect) => {
    setReviewing(id)
    try {
      await submitWrongAnswer(id, isCorrect)
      setRevealed((prev) => { const next = { ...prev }; delete next[id]; return next })
      load()
    } catch (e) {
      alert('提交失败，请重试')
    } finally {
      setReviewing(null)
    }
  }

  const items = data?.items || []
  const activeItems = items.filter((w) => !w.mastered)

  if (loading) return <div className="text-neutral-400">加载中…</div>

  return (
    <div className="max-w-2xl mx-auto">
      {/* 头部 */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-neutral-900 mb-2">AI 错题本</h1>
        <p className="text-sm text-neutral-500">
          复习时答错的题会自动收进来，按遗忘曲线安排重考，直到真正掌握
        </p>
      </div>

      {/* 统计 */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="border border-neutral-100 rounded-xl p-4 text-center">
          <div className="text-2xl font-semibold text-neutral-900">{data?.due_count || 0}</div>
          <div className="text-xs text-neutral-400 mt-1">待攻克</div>
        </div>
        <div className="border border-neutral-100 rounded-xl p-4 text-center">
          <div className="text-2xl font-semibold text-neutral-900">{data?.mastered_count || 0}</div>
          <div className="text-xs text-neutral-400 mt-1">已掌握</div>
        </div>
        <div className="border border-neutral-100 rounded-xl p-4 text-center">
          <div className="text-2xl font-semibold text-neutral-900">
            {items.filter((w) => w.wrong_count >= 2).length}
          </div>
          <div className="text-xs text-neutral-400 mt-1">顽固错题（错≥2次）</div>
        </div>
      </div>

      {/* 空状态 */}
      {activeItems.length === 0 && (
        <div className="border border-dashed border-neutral-200 rounded-xl py-16 text-center">
          <p className="text-sm text-neutral-400 mb-1">错题本是空的</p>
          <p className="text-xs text-neutral-300 mb-5">去学习复习做一轮题，答错的会自动收进来</p>
          <button
            onClick={() => navigate('/review')}
            className="text-xs text-neutral-600 hover:text-neutral-900 underline underline-offset-2"
          >
            去复习 →
          </button>
        </div>
      )}

      {/* 错题列表 */}
      <div className="space-y-4">
        {activeItems.map((w) => (
          <div key={w.id} className="bg-white border border-neutral-100 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                w.wrong_count >= 2 ? 'bg-neutral-900 text-white' : 'bg-neutral-100 text-neutral-500'
              }`}>
                错 {w.wrong_count} 次 · {w.interval_days} 天后重考
              </span>
              {w.card_title && (
                <button
                  onClick={() => w.card_id && navigate(`/card/${w.card_id}`)}
                  className="text-xs text-neutral-400 hover:text-neutral-700 transition truncate max-w-[60%]"
                  title={w.card_title}
                >
                  来自：{w.card_title}
                </button>
              )}
            </div>

            <div className="text-sm text-neutral-900 font-medium leading-7 mb-2">{w.question}</div>

            {w.user_answer && (
              <div className="text-xs text-neutral-400 leading-6 mb-2">
                上次你的答案：<span className="text-neutral-500">{w.user_answer}</span>
              </div>
            )}

            {revealed[w.id] ? (
              <div className="text-sm text-neutral-700 leading-7 bg-neutral-50 rounded-lg px-4 py-3 mb-4">
                <span className="text-xs text-neutral-400 mr-1">参考答案：</span>
                {w.correct_answer}
              </div>
            ) : (
              <button
                onClick={() => setRevealed((p) => ({ ...p, [w.id]: true }))}
                className="text-xs text-neutral-500 hover:text-neutral-700 mb-4"
              >
                先自己回忆一遍，再看答案 ▼
              </button>
            )}

            {revealed[w.id] && (
              <div className="flex gap-2">
                <button
                  onClick={() => handleSubmit(w.id, false)}
                  disabled={reviewing === w.id}
                  className="flex-1 py-2 text-sm border border-neutral-200 text-neutral-600 rounded-lg hover:bg-neutral-50 disabled:opacity-40 transition"
                >
                  还是没答对
                </button>
                <button
                  onClick={() => handleSubmit(w.id, true)}
                  disabled={reviewing === w.id}
                  className="flex-1 py-2 text-sm bg-neutral-900 text-white rounded-lg font-medium hover:bg-neutral-800 disabled:opacity-40 transition"
                >
                  我答对了 ✓
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
