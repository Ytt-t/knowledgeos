<p align="center">
  <img src="./screenshots/01_home_dashboard.png" width="720" alt="KnowledgeOS">
</p>

<h1 align="center">KnowledgeOS</h1>

<p align="center">
  AI 个人知识操作系统 · Build your second brain.
  <br/>
  Turn scattered information into structured knowledge.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13%2B-3776ab" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009485" alt="FastAPI">
  <img src="https://img.shields.io/badge/React%2018-61dafb" alt="React 18">
  <img src="https://img.shields.io/badge/RAG-检索增强-4D6BFE" alt="RAG">
  <img src="https://img.shields.io/badge/LLM-DeepSeek%20V3%20%2F%20R1-4D6BFE" alt="DeepSeek">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

---

## 简介

**KnowledgeOS** 是一个 AI 个人知识操作系统，覆盖「输入 → 理解 → 沉淀 → 复习 → 应用」的完整链路：任意形态的内容（视频、文档、网页、图片）经多智能体（Multi-Agent）协同蒸馏为结构化知识卡片，沉淀进个人知识库，再通过基于个人知识的 RAG 问答与多模式复习完成内化，最终形成个人专属的 AI 第二大脑。

产品设计文档见 [`docs/PRD.md`](./docs/PRD.md)，各 Agent 的完整系统提示词见 [`prompts/`](./prompts/)。

## 核心特性

### 多模态输入（Capture）

支持 B 站 / 小红书 / 抖音视频、PDF、Word、图片、网页链接与纯文本，统一解析为可处理的文本内容。

```
输入内容 → 内容解析 → AI 知识蒸馏 → 生成知识卡片 → 用户确认保存
```

<p align="center">
  <img src="./screenshots/02_capture_ai_distillation.png" width="720" alt="Capture 知识蒸馏">
</p>

### 深度知识蒸馏（Card 2.0）

不是一段摘要，而是由五个要素构成的结构化知识卡片，讲清「是什么 / 为什么重要 / 怎么用 / 常见坑」。

| 要素 | 说明 |
|---|---|
| **one_liner** | 一句话点破核心洞察 |
| **core_points** | 核心知识点 + 机制解释 |
| **knowledge_structure** | 知识结构树 |
| **key_cases** | 实践应用场景 |
| **next_steps** | 下一步学习建议 |

### 个人知识库（Knowledge Library）

取消 AI 强制分类。采用用户自定义知识空间（如「AI 产品经理」「Python」「求职」），AI 仅提供标签建议，归档与分类完全由用户决定。

<p align="center">
  <img src="./screenshots/03_card_library.png" width="720" alt="知识库">
</p>

### AI Copilot

基于个人知识库的 RAG 问答，回答附带来源引用，支持三种模式：

- **知识问答**：基于个人知识库回答并引用来源
- **知识连接**：发现不同知识卡片之间的关联
- **学习辅助**：生成学习路线、面试题与实践任务

<p align="center">
  <img src="./screenshots/04_ai_copilot_qa.png" width="720" alt="AI Copilot">
</p>

### 智能复习（Review）

从最近学习、指定知识空间、薄弱知识等范围出题，覆盖理解 / 应用 / 面试 / 快速检测四种模式，AI 自动评分，错题自动沉淀进错题本。

<p align="center">
  <img src="./screenshots/05_review_session.png" width="720" alt="复习">
</p>

<p align="center">
  <img src="./screenshots/07_wrong_book.png" width="720" alt="错题本">
</p>

## 技术架构

前后端分离架构：**FastAPI** 后端承担内容解析、向量检索与 Multi-Agent 调度；**React** 前端为黑白极简风格界面。

### Multi-Agent 协同

五个 Agent 各司其职，由 Orchestrator 以状态机统一编排：

| Agent | 职责 | 实现 |
|---|---|---|
| **Summarizer** | 将内容蒸馏为 Card 2.0 五要素知识卡片 | [`summarizer.py`](./backend/app/agents/summarizer.py) |
| **Structuring** | 将一段总结拆分为 N 个独立概念卡 | [`structuring.py`](./backend/app/agents/structuring.py) |
| **Organizer** | 标签建议与知识空间推荐（仅建议，不强制） | [`organizer.py`](./backend/app/agents/organizer.py) |
| **QA** | 三模式 RAG 问答 | [`qa.py`](./backend/app/agents/qa.py) |
| **Orchestrator** | 解析 → 去重 → 蒸馏 → 分类的状态机调度 | [`orchestrator.py`](./backend/app/agents/orchestrator.py) |

三条设计原则：

1. **轻任务走小模型**：标签分类等任务使用 DeepSeek V3 的 `chat_json`，控制成本与延迟
2. **重任务走深度推理**：知识蒸馏与问答经 `smart_json` 路由至 DeepSeek R1，再由 V3 转为结构化 JSON
3. **AI 不替用户做决定**：分类、归档、重要性判断均由用户最终确认

### 检索增强（RAG）

采用**双通道召回**提升中文场景召回率：

- **向量通道**：sentence-transformers + faiss
- **关键词通道**：英文 token + 卡片关键词 / 标签 + CJK 二元组重叠

### 技术栈

| 分层 | 技术 |
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

cp .env.example .env   # 编辑 .env，填入 DEEPSEEK_API_KEY

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> 首次启动会加载 embedding 模型，约需 1-2 分钟。

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
│   └── PRD.md                    # 产品需求文档
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