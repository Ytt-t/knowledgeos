// V4 状态机: pending → parsing → summarizing → classifying → done/failed
// V7: duplicate = 命中重复内容（终态，等待用户决策，不属于处理中）
export const STATUS_TEXT = {
  pending: '等待处理',
  parsing: '解析内容中',
  summarizing: 'AI 总结中',
  classifying: '自动分类中',
  done: '已完成',
  failed: '处理失败',
  duplicate: '发现重复内容',
}

// 黑白极简配色：处理中=浅灰，完成=黑底白字，失败=深灰
export const STATUS_COLOR = {
  pending: 'bg-neutral-100 text-neutral-500',
  parsing: 'bg-neutral-100 text-neutral-600',
  summarizing: 'bg-neutral-200 text-neutral-700',
  classifying: 'bg-neutral-200 text-neutral-700',
  done: 'bg-neutral-900 text-white',
  failed: 'bg-neutral-300 text-neutral-600',
  duplicate: 'bg-neutral-200 text-neutral-700',
}

export const PROCESSING_STATUSES = ['pending', 'parsing', 'summarizing', 'classifying']

// V4 内容类型标签
export const CONTENT_TYPE_LABEL = {
  video: '视频',
  document: '文档',
  image: '图片',
}
