# Agent Prompt 索引

> 5 个 Agent 的完整系统提示词归档，对应代码实现在 [`backend/app/agents/`](../backend/app/agents/)。

| Agent | 职责 | 文件 |
|---|---|---|
| **Summarizer** | 知识蒸馏：从原始内容生成结构化知识卡片（Card 2.0 五要素） | [`summarizer.py`](../backend/app/agents/summarizer.py) |
| **Structuring** | 概念拆分：把一段总结拆成 1~N 个独立核心概念卡 | [`structuring.py`](../backend/app/agents/structuring.py) |
| **Organizer** | 标签建议 + 知识空间推荐（不强制分类） | [`organizer.py`](../backend/app/agents/organizer.py) |
| **QA (Retriever)** | 三模式 RAG 问答：知识问答 / 知识连接 / 学习辅助 | [`qa.py`](../backend/app/agents/qa.py) |
| **Orchestrator** | 状态机：parsing → summarizing → classifying → done | [`orchestrator.py`](../backend/app/agents/orchestrator.py) |

---

## 1. Summarizer — 知识蒸馏（核心）

**设计哲学**：用户说 "这总结还不如去问豆包" 是最大的失败。要给出深度理解，不是目录式要点。

### 输出五要素（Card 2.0）

- **one_liner**：一句话金句，不超过 25 字，必须点破核心洞察
- **core_points**：3-5 条，每条带 `point`（≤20 字）+ `detail`（1-2 句机制/例子）+ `importance`（高/中/低）
- **knowledge_structure**：dict 形式，主题 → 子主题列表
- **key_cases**：1-3 个具体应用场景 + 如何应用
- **next_steps**：2-4 条「具体行动 + 资源方向」，禁止"建议深入学习"废话

### 关键约束

1. 全部用中文输出（专有名词可保留英文）
2. **一语道破优先**：先找核心洞察，再点出次要点
3. **深度优先**：每条 detail 要回答"为什么"和"怎么做"
4. summary 必须用 Markdown 段落 + 关键概念 **加粗**
5. 基于原文提炼，**禁止编造**案例和数据
6. **importance 不再由 AI 输出** —— 重要性由用户自己决定（V6 决策）

### 完整代码

→ [`backend/app/agents/summarizer.py`](../backend/app/agents/summarizer.py) 第 28-83 行 `SYSTEM_PROMPT`

---

## 2. Structuring — 概念拆分

**适用场景**：一个 source 可能涉及多个独立概念（比如一个视频同时讲 RAG 和 Agent），需要拆成多张卡片。

### 输出字段

- `concept_name`：概念名（如 "RAG"），简短
- `one_line_explanation`：一句话让外行也能懂
- `knowledge_structure`：dict，key 概念 / value 子概念列表
- `application_scenarios`：2-4 个具体场景
- `learning_suggestion`：下一步学习方向

### 关键约束

- 概念名准确，业界通用术语优先
- 一句话解释要让外行也能懂
- 全部中文输出

→ [`backend/app/agents/structuring.py`](../backend/app/agents/structuring.py) 第 17-35 行

---

## 3. Organizer — 标签建议 + 空间推荐

**V6 决策**：取消 AI 强制分类。AI 只做**建议**（标签 + 空间），**用户决定**最终分类与归档。

### 两件事

1. **tags**：3-5 个具体标签（比"数据库"更好的"向量数据库"）
2. **suggested_space**：从已有空间选最贴切的 → 匹配不到给新空间名建议 → 太杂返回 null

### 关键约束

- 不替用户归档、不替用户删内容
- 标签不要和空间名重复
- 轻任务走 V3 `chat_json`，不走 R1

→ [`backend/app/agents/organizer.py`](../backend/app/agents/organizer.py) 第 17-27 行

---

## 4. QA (Retriever) — RAG 问答三模式

**位置**：基于用户**个人知识库**回答，三种模式（PRD V3.0 P0）：

| 模式 | 用途 | 关键 prompt |
|---|---|---|
| **free** | 通用自由问答（V8 新增） | 不检索知识库，DeepSeek 原味 |
| **kb / qa** | 知识库问答（严格 RAG） | 引用来源、结构化输出 |
| **connect** | 知识连接发现 | 找关联 / 对比 / 互补 |
| **learn** | 学习辅助 | 生成路线 / 面试题 / 实践任务 |

### 检索增强（V9）

**双通道召回**：
- **向量通道**：sentence-transformers + faiss
- **关键词通道**：英文 token + 卡片关键词/标签 + CJK 二元组重叠

中文 embedding 相似度普遍偏低，关键词通道兜底，召回率大幅提升。

### 输出 schema（统一）

```json
{
  "conclusion": "2-4 句完整结论段落",
  "key_points": [{"point": "...", "detail": "1-3 句解释"}],
  "source_knowledge": [{"title": "来源卡片", "point": "关键内容"}],
  "extended_thinking": "2-4 句延伸思考",
  "action_advice": ["具体可执行建议 1", "建议 2"]
}
```

→ [`backend/app/agents/qa.py`](../backend/app/agents/qa.py) 第 124-239 行

---

## 5. Orchestrator — 状态机调度

**不是 LLM Agent，是流程编排**。状态机：

```
pending → parsing → (去重检测) → summarizing → classifying → done/failed
```

### 关键决策点

- **V7 幂等护栏**：已完成/处理中不重复执行
- **去重检测**：embedding 命中已有卡片 → 标记 duplicate，等用户决策（省 R1 蒸馏费用）
- **失败兜底**：状态转入 failed，写入 error_message

→ [`backend/app/agents/orchestrator.py`](../backend/app/agents/orchestrator.py) 第 35-213 行

---

## 设计模式总结

整个项目的 Agent 架构遵循的三个原则：

1. **轻任务走小模型**（organizer 用 V3 chat_json）
2. **重任务走 R1 深度思考 + V3 转 JSON**（summarizer、qa 通过 `smart_json` 路由）
3. **AI 不替用户做决定**（分类 / 归档 / 重要性 → 用户说了算）

后续如果要加新 Agent，按相同模式：`system_prompt` + `user_template` + 清洗函数 + 一个 schema 兜底。
