import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  // V6.1: R1 深度思考最长约 5 分钟，120s 超时会误杀长问答
  timeout: 360000,
})

// ===== Sources (V4: /url + /file 双端点) =====
export const submitVideoUrl = (url) =>
  api.post('/sources/url', { url }).then((r) => r.data)
export const uploadFile = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api
    .post('/sources/file', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data)
}
export const getSource = (id) => api.get(`/sources/${id}`).then((r) => r.data)
// V7: duplicate 状态下的用户决策
export const continueSource = (id, action) =>
  api.post(`/sources/${id}/continue`, { action }).then((r) => r.data)
// V8: 处理中/待决策的 source（切回首页恢复进度）
export const listActiveSources = () => api.get('/sources/active').then((r) => r.data)
export const listSources = () => api.get('/sources').then((r) => r.data)

// ===== Cards =====
export const listCards = (params = {}) =>
  api.get('/cards', { params }).then((r) => r.data)
export const getCard = (id) => api.get(`/cards/${id}`).then((r) => r.data)
export const updateCard = (id, data) =>
  api.patch(`/cards/${id}`, data).then((r) => r.data)
export const deleteCard = (id) =>
  api.delete(`/cards/${id}`).then((r) => r.data)
export const redistillCard = (id) =>
  api.post(`/cards/${id}/redistill`).then((r) => r.data)
export const getRelatedCards = (id) =>
  api.get(`/cards/${id}/related`).then((r) => r.data)
export const listDomains = () => api.get('/domains').then((r) => r.data)
export const getKnowledgeGraph = () =>
  api.get('/knowledge-graph').then((r) => r.data)

// ===== V6 知识空间（PRD V3.0：用户自定义分类） =====
export const listSpaces = () => api.get('/spaces').then((r) => r.data)
export const createSpace = (name) =>
  api.post('/spaces', { name }).then((r) => r.data)
export const updateSpace = (id, data) =>
  api.patch(`/spaces/${id}`, data).then((r) => r.data)
export const deleteSpace = (id) =>
  api.delete(`/spaces/${id}`).then((r) => r.data)

// ===== V4.1 Card 2.0: Quality Feedback + Quick Test =====
export const submitFeedback = (cardId, feedback) =>
  api.post(`/cards/${cardId}/feedback`, { feedback }).then((r) => r.data)
export const getQuickTest = (cardId) =>
  api.get(`/cards/${cardId}/quick-test`).then((r) => r.data)
export const checkQuickTestAnswer = (cardId, index) =>
  api.post(`/cards/${cardId}/quick-test/check`, { index }).then((r) => r.data)

// ===== Chat (V5: 对话管理) =====
export const createChatSession = (scope) =>
  api
    .post('/chat/sessions', { title: '新会话', scope: scope || { type: 'all' } })
    .then((r) => r.data)
export const listChatSessions = () => api.get('/chat/sessions').then((r) => r.data)
export const updateChatSession = (id, data) =>
  api.patch(`/chat/sessions/${id}`, data).then((r) => r.data)
export const deleteChatSession = (id) =>
  api.delete(`/chat/sessions/${id}`).then((r) => r.data)
export const clearAllChatSessions = () =>
  api.delete('/chat/sessions').then((r) => r.data)
export const listMessages = (sid) =>
  api.get(`/chat/sessions/${sid}/messages`).then((r) => r.data)
export const sendMessage = (sid, content, mode = 'qa') =>
  api.post(`/chat/sessions/${sid}/messages`, { content, mode }).then((r) => r.data)
export const streamChatMessage = (sid, content, mode, onEvent) => {
  // V9: SSE 流式问答（fetch 手写解析，支持逐字渲染）
  return fetch(`/api/chat/sessions/${sid}/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, mode }),
  }).then(async (resp) => {
    if (!resp.ok || !resp.body) {
      throw new Error(`请求失败（${resp.status}）`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue
        try {
          onEvent(JSON.parse(raw))
        } catch (e) {
          // 忽略解析失败的分片
        }
      }
    }
    if (buffer.trim()) {
      const raw = buffer.trim().slice(6)
      if (raw) {
        try { onEvent(JSON.parse(raw)) } catch (e) { /* ignore */ }
      }
    }
  })
}
export const retrySource = (id) =>
  api.post(`/sources/${id}/retry`).then((r) => r.data)
export const getCitedCard = (cardId) =>
  api.get(`/chat/cited-cards/${cardId}`).then((r) => r.data)

// ===== Review (V6: 按空间/最近/薄弱点出题 + 智能题量 + 评分) =====
export const generateReviewQuestions = (scope) =>
  api.post('/review/questions', scope).then((r) => r.data)
export const evaluateReviewAnswers = (payload) =>
  api.post('/review/evaluate', payload).then((r) => r.data)
export const getReviewDomains = () =>
  api.get('/review/domains').then((r) => r.data)
export const getReviewWeakPoints = () =>
  api.get('/review/weak-points').then((r) => r.data)
export const getReviewToday = () =>
  api.get('/review/today').then((r) => r.data)
// V7 错题本
export const listWrongQuestions = (dueOnly = false) =>
  api.get('/review/wrong-questions', { params: { due_only: dueOnly } }).then((r) => r.data)
export const submitWrongAnswer = (id, isCorrect) =>
  api.post(`/review/wrong-questions/${id}/submit`, { is_correct: isCorrect }).then((r) => r.data)

// ===== V7 AI 学习播客 =====
export const createPodcast = (scope) =>
  api.post('/podcasts', { scope }).then((r) => r.data)
export const listPodcasts = () => api.get('/podcasts').then((r) => r.data)
export const getPodcast = (id) => api.get(`/podcasts/${id}`).then((r) => r.data)
export const retryPodcast = (id) =>
  api.post(`/podcasts/${id}/retry`).then((r) => r.data)
export const deletePodcast = (id) =>
  api.delete(`/podcasts/${id}`).then((r) => r.data)

// ===== V8 账号系统 =====
export const getMe = () => api.get('/users/me').then((r) => r.data)
export const updateMe = (data) => api.put('/users/me', data).then((r) => r.data)
export const updatePassword = (data) =>
  api.post('/users/me/password', data).then((r) => r.data)
export const uploadAvatar = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/users/me/avatar', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((r) => r.data)
}
export const uploadBanner = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/users/me/banner', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((r) => r.data)
}

// ===== Growth / Stats (V6: 真实学习数据) =====
export const getGrowthOverview = () =>
  api.get('/growth/overview').then((r) => r.data)
export const getReviewHistory = () =>
  api.get('/growth/review-history').then((r) => r.data)
