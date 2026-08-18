# KnowledgeOS

> Build your second brain.
> Turn scattered information into structured knowledge.

![Python](https://img.shields.io/badge/Python-3.13%2B-3776ab) ![FastAPI](https://img.shields.io/badge/FastAPI-009485) ![React](https://img.shields.io/badge/React_18-61dafb) ![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-4D6BFE)

KnowledgeOS 是一个 AI 个人知识操作系统（Personal Knowledge OS），覆盖「输入 → 理解 → 沉淀 → 复习 → 应用」的完整链路：任意形态的内容（视频、文档、网页、图片）经解析后由多个协同的 AI Agent 蒸馏为结构化知识卡片，沉淀进个人知识库，再通过基于个人知识的 RAG 问答与多模式复习完成内化。

产品设计文档见 [docs/PRD.md](./docs/PRD.md)，各 Agent 的完整系统提示词见 [prompts/](./prompts/)。

---

## 背景

学习者在日常场景中面临的问题：

- 信息碎片化，内容散落在 B 站、小红书、PDF、网页等各处，难以沉淀
- 常规 AI 总结停留在摘要层面，读完即忘，无法形成结构化理解
- 收藏的内容缺少复用机制，知识无法被检索和组合
- 通用对话 AI 不了解个人已有的知识资产，回答无法建立在自己的知识体系之上

KnowledgeOS 针对以上问题提供一体的解决方案。

## 产品设计

### 多模态输入（Capture）

支持 B 站 / 小红书 / 抖音视频链接、PDF、Word、图片、网页链接与纯文本。处理流程：

```
输入内容 → 内容解析 → AI 知识蒸馏 → 生成知识卡片 → 用户确认保存
```

![Capture](./screenshots/02_capture_ai_distillation.png)

### 知识蒸馏（Card 2.0）

每张知识卡片由五个要素构成，而非一段摘要：

| 要素 | 说明 |
|---|---|
| one_liner | 一句话理解 |
| core_points | 核心概念 |
| structure | 知识结构 |
| cases | 实践应用 |
| next_steps | 下一步学习建议 |

### 知识空间（Knowledge Library）

取消 AI 强制分类，采用用户自定义知识空间（如「AI 产品经理」「Python」「求职」）。AI 仅提供标签建议，归档与分类由用户决定。

![Library](./screenshots/03_card_library.png)

### AI Copilot

基于个人知识库的 RAG 问答，回答附带来源引用。提供三种模式：

- **知识问答**：基于个人知识库回答，引用来源
- **知识连接**：发现不同知识之间的关系
- **学习辅助**：生成学习路线、面试题与实践任务

![Copilot](./screenshots/04_ai_copilot_qa.png)

### 复习（Review）

从最近学习、指定知识空间、薄弱知识等范围出题，支持理解 / 应用 / 面试 / 快速检测四种模式，AI 自动评分，错题进入错题本。

![Review](./screenshots/05_review_session.png) ![WrongBook](./screenshots/07_wrong_book.png)

### 首页 Dashboard

![Home](./screenshots/01_home_dashboard.png)

## 系统设计

前后端分离架构：FastAPI 后端承担内容解析、向量检索与 Multi-Agent 调度；React 前端为黑白极简风格（遵循 PRD 的界面设计约束）。

五个 Agent 协同工作：

| Agent | 职责 | 实现 |
|---|---|---|
| Summarizer | 内容蒸馏为 Card 2.0 五要素卡片 | [`summarizer.py`](./backend/app/agents/summarizer.py) |
| Structuring | 将一段总结拆分为 N 个独立概念卡 | [`structuring.py`](./backend/app/agents/structuring.py) |
| Organizer | 标签建议与知识空间推荐（仅建议） | [`organizer.py`](./backend/app/agents/organizer.py) |
| QA | 三模式 RAG 问答 | [`qa.py`](./backend/app/agents/qa.py) |
| Orchestrator | 解析 → 去重 → 蒸馏 → 分类的状态机调度 | [`orchestrator.py`](./backend/app/agents/orchestrator.py) |

三条设计原则：

1. **轻任务走小模型**：标签分类等任务使用 DeepSeek V3 的 `chat_json`，控制成本与延迟
2. **重任务走深度推理**：知识蒸馏与问答经 `smart_json` 路由至 DeepSeek R1，再由 V3 转为结构化 JSON
3. **AI 不替用户做决定**：分类、归档、重要性判断均由用户最终确认

### 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + Vite + TailwindCSS |
| 后端 | FastAPI + SQLAlchemy + SQLite |
| 检索 | sentence-transformers + faiss |
| 大模型 | DeepSeek API（V3 / R1） |
| 内容解析 | yt-dlp（视频）、python-docx、easyocr（图片） |

## 快速开始

环境要求：Python 3.13+、Node.js 18+、DeepSeek API Key（[platform.deepseek.com](https://platform.deepseek.com) 申请）。

### 启动后端

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate   macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt

# 可选依赖（视频解析 / OCR / 向量检索需要）
pip install yt-dlp edge-tts sentence-transformers faiss-cpu torch easyocr

cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

首次启动会加载 embedding 模型，约 1-2 分钟。

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 。前后端通过 Vite 代理通信（`/api` → `http://localhost:8000`），无需额外配置 CORS。

## 项目结构

```
knowledgeos/
├── docs/
│   └── PRD.md                    # 产品需求文档（V3.0）
├── prompts/
│   └── README.md                 # Agent 系统提示词索引
├── screenshots/                  # 界面截图
├── backend/
│   ├── app/
│   │   ├── agents/               # Multi-Agent 实现
│   │   ├── api/                  # REST 接口
│   │   ├── services/             # 向量库 / DeepSeek / 内容解析
│   │   ├── models/               # SQLAlchemy 数据模型
│   │   ├── core/                 # 配置
│   │   └── main.py               # FastAPI 入口
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/                # 页面组件
        ├── components/
        ├── api/
        ├── App.jsx
        └── main.jsx
```

## 说明

`.env`、数据库文件、上传目录、日志等本地运行产物均已通过 `.gitignore` 排除，仓库中不含任何密钥与个人数据。

## License

MIT
