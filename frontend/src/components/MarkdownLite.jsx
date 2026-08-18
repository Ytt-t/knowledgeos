import React from 'react'

// V6.1: 零依赖轻量 Markdown 渲染（ChatGPT 式阅读体验）
// 支持：**粗体**、#/##/### 标题、- 无序列表、1. 有序列表、段落、行内 `code`、```代码块
// 不支持（字面渲染）：斜体/删除线/链接/表格 —— 出现即原样显示，永不抛错

const INLINE_RE = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g

// 行内解析：`code` 与 **粗体**（代码分支在前，保证反引号内的 ** 不被加粗）
function renderInline(text, keyPrefix) {
  const parts = text.split(INLINE_RE)
  return parts.map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={`${keyPrefix}-${i}`} className="bg-neutral-100 px-1 py-0.5 rounded text-[0.9em] font-mono">
          {part.slice(1, -1)}
        </code>
      )
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong key={`${keyPrefix}-${i}`} className="font-semibold text-neutral-900">
          {part.slice(2, -2)}
        </strong>
      )
    }
    return <React.Fragment key={`${keyPrefix}-${i}`}>{part}</React.Fragment>
  })
}

// 块级解析：按空行分块，按首行判定类型
function renderBlocks(text) {
  const lines = (text || '').replace(/\r\n/g, '\n').split('\n')
  const blocks = []
  let current = []
  let inFence = false

  const flush = () => {
    if (current.length) {
      blocks.push(current)
      current = []
    }
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('```')) {
      flush()
      if (inFence) {
        blocks.push(['```'])
        inFence = false
      } else {
        inFence = true
        current = [line]
      }
      continue
    }
    if (inFence) {
      current.push(line)
      continue
    }
    if (trimmed === '') {
      flush()
      continue
    }
    current.push(line)
  }
  flush()
  if (inFence) blocks.push(['```']) // 未闭合 fence 兜底

  return blocks
}

function Block({ block, index }) {
  const first = block[0].trim()

  // 代码块（``` 开头）
  if (first.startsWith('```')) {
    const code = block.slice(1).join('\n')
    return (
      <pre key={index} className="bg-neutral-50 border border-neutral-100 rounded-lg p-3 my-3 overflow-x-auto text-xs leading-relaxed text-neutral-700">
        {code}
      </pre>
    )
  }

  // 标题（# / ## / ###）
  const heading = first.match(/^(#{1,3})\s+(.*)$/)
  if (heading) {
    const level = heading[1].length
    return (
      <h4
        key={index}
        className={`font-semibold text-neutral-900 ${level === 1 ? 'text-base mt-5 mb-2' : 'text-sm mt-4 mb-2'}`}
      >
        {renderInline(heading[2], `h${index}`)}
      </h4>
    )
  }

  // 无序列表（- / *）：首行判定，续行（LLM 换行包裹）并入上一项
  const isUl = /^[-*]\s+/.test(first)
  if (isUl && block.length > 0) {
    const items = []
    for (const l of block) {
      const t = l.trim()
      if (/^[-*]\s+/.test(t)) {
        items.push(t.replace(/^[-*]\s+/, ''))
      } else if (items.length) {
        items[items.length - 1] += ' ' + t
      } else {
        items.push(t)
      }
    }
    return (
      <ul key={index} className="list-disc pl-5 space-y-1.5 my-2">
        {items.map((text, i) => (
          <li key={i} className="leading-7">
            {renderInline(text, `ul${index}-${i}`)}
          </li>
        ))}
      </ul>
    )
  }

  // 有序列表（1. / 1、）：首行判定，续行并入上一项
  const isOl = /^\d+[.、]\s+/.test(first)
  if (isOl && block.length > 0) {
    const items = []
    for (const l of block) {
      const t = l.trim()
      if (/^\d+[.、]\s+/.test(t)) {
        items.push(t.replace(/^\d+[.、]\s+/, ''))
      } else if (items.length) {
        items[items.length - 1] += ' ' + t
      } else {
        items.push(t)
      }
    }
    return (
      <ol key={index} className="list-decimal pl-5 space-y-1.5 my-2">
        {items.map((text, i) => (
          <li key={i} className="leading-7">
            {renderInline(text, `ol${index}-${i}`)}
          </li>
        ))}
      </ol>
    )
  }

  // 段落
  return (
    <p key={index} className="my-2 leading-7">
      {renderInline(block.join(' '), `p${index}`)}
    </p>
  )
}

export default function MarkdownLite({ text, className = '' }) {
  const blocks = renderBlocks(text)
  return <div className={className}>{blocks.map((b, i) => <Block key={i} block={b} index={i} />)}</div>
}
