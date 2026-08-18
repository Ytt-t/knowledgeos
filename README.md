# 📚 KnowledgeOS

> **Build your second brain.**
> 把散落在各处的内容自动蒸馏成结构化知识，再让 AI 帮你真正学进脑子里。

[![Status](https://img.shields.io/badge/Status-可运行-3fb950)]()
[![Python](https://img.shields.io/badge/Python-3.13+-3776ab)]()
[![React](https://img.shields.io/badge/React-18-61dafb)]()
[![License](https://img.shields.io/badge/License-Private-grey)]()

**KnowledgeOS** 是一个 AI 个人知识操作系统。从「输入任意内容」到「真正内化为自己的知识」，全链路打通——支持 B 站/小红书/抖音视频、B 站/PDF/Word/图片、网页链接，多模态内容自动解析、AI 蒸馏成结构化知识卡片，再用 AI Copilot 问答、AI 播客、智能复习巩固。

---

## 🎬 Demo 截图

> 📌 **截图待补**：跑起来后存到 [`screenshots/`](./screenshots/) 目录，README 里的引用就能直接显示。

| 页面 | 截图 |
|---|---|
| 首页 Dashboard | ![Home](./screenshots/01_home_dashboard.png) |
| AI 知识蒸馏生成 | ![Capture](./screenshots/02_capture_ai_distillation.png) |
| 知识空间 / 卡片库 | ![Library](./screenshots/03_card_library.png) |
| AI Copilot 知识问答 | ![Copilot](./screenshots/04_ai_copilot_qa.png) |
| 复习模式 | ![Review](./screenshots/05_review_session.png) |
| AI 播客 | ![Podcast](./screenshots/06_podcast_player.png) |
| 错题本 | ![WrongBook](./screenshots/07_wrong_book.png) |

---

## ✨ 它解决什么问题

| 痛点 | 这项目怎么解 |
|---|---|
| 📱 信息碎片化，学过就忘 | 一个入口收纳所有形态内容（B 站/小红书/PDF/图片/链接），自动结构化 |
| 🤖 AI 总结停在摘要层面 | 不是摘要，是**蒸馏**：一句话理解 + 核心要点 + 知识结构 + 应用案例 + 下一步建议 |
| 📚 知识无法复用 | Personal RAG：**基于自己的知识库**问答，回答带引用来源 |
| 🔁 学完不复习等于没学 | 四种复习模式 + AI 出题 + 自动评分 + 错题自动进错题本 |
| ⏰ 没整块时间学习 | AI 播客：把卡片转成双人对话，走路听 |
| 🗂️ AI 强制定类，用户失去控制 | **AI 只建议，用户决定**分类、归档、重要性 |

---

## 🧠 核心能力一图看懂

```
┌─────────────────────────────────────────────────────────┐
│  Frontend: React 18 + Vite + TailwindCSS（黑白极简）     │
├──────────────────────┬──────────────────────────────────┤
│  Backend: FastAPI    │  Multi-Agent（6 个）              │
│  + SQLite/faiss     │  ┌─ Summarizer  知识蒸馏（深度版）│
│  + DeepSeek API      │  ├─ Structuring 概念拆分         │
│  + yt-dlp/whisper   │  ├─ Organizer  标签建议 + 空间推荐│
│                      │  ├─ QA          三模式 RAG 问答  │
│                      │  ├─ Podcast    双人对话播客脚本  │
│                      │  └─ Orchestrator 状态机调度      │
└──────────────────────┴──────────────────────────────────┘
```

---

## 🤖 AI Agent 设计（核心亮点）

KnowledgeOS 的灵魂在 **6 个协同的 Agent**，每个 Agent 一句话 + 完整 prompt 都在 [`prompts/`](./prompts/)：

| Agent | 一句话职责 |
|---|---|
| **Summarizer** | 把任意内容蒸馏成 Card 2.0 五要素卡片（one_liner / core_points / structure / cases / next_steps） |
| **Structuring** | 一段内容可能涉及多个概念，自动拆成 N 张独立卡片 |
| **Organizer** | 给内容打具体标签 + 推荐知识空间（**仅建议不强制**） |
| **QA (Retriever)** | 三模式 RAG 问答：知识问答 / 知识连接 / 学习辅助 |
| **Podcast** | 把卡片转成双人对话播客脚本（NotebookLM 式） |
| **Orchestrator** | 解析→去重→蒸馏→分类 状态机调度 |

**三条设计原则**贯穿所有 Agent：

1. **轻任务走小模型**（Organizer 用 V3 `chat_json`，快且便宜）
2. **重任务走 R1 深度思考** + V3 转 JSON（Summarizer / QA 经过 `smart_json` 路由）
3. **AI 不替用户做决定**——分类、归档、重要性 → 用户说了算

📄 完整 PRD：[`docs/PRD.md`](./docs/PRD.md)
📜 完整 Prompt 索引：[`prompts/README.md`](./prompts/README.md)

---

## 🚀 快速开始

### 环境要求

- **Python 3.13+**（需支持 torch / faiss 的版本）
- **Node.js 18+**
- 一个 **DeepSeek API Key**（[platform.deepseek.com](https://platform.deepseek.com) 注册即得，国内邮箱）

### 1️⃣ 启动后端

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt

# 可选依赖（按需安装，视频/OCR/语音功能才有）
pip install yt-dlp edge-tts sentence-transformers faiss-cpu torch easyocr

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY（申请：platform.deepseek.com）

# 启动（首次启动会加载 embedding 模型，约 1-2 分钟）
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2️⃣ 启动前端

```bash
cd frontend
npm install
npm run dev
# 浏览器打开 http://localhost:5173
```

前后端默认走 Vite 代理（`/api` → `http://localhost:8000`），**无需额外配置 CORS**。

---

## 📁 项目结构

```
knowledgegeos/                    ← GitHub 仓库根
├── README.md                     ← 你正在看的
├── docs/
│   └── PRD.md                    ← 产品需求文档（V3.0）
├── prompts/
│   └── README.md                 ← 6 个 Agent 的系统提示词索引
├── screenshots/                  ← Demo 截图目录（待填充）
├── backend/
│   ├── app/
│   │   ├── agents/               ← Multi-Agent 核心逻辑
│   │   │   ├── summarizer.py     ← 知识蒸馏
│   │   │   ├── structuring.py    ← 概念拆分
│   │   │   ├── organizer.py      ← 标签 + 空间推荐
│   │   │   ├── qa.py             ← RAG 三模式问答
│   │   │   ├── podcast_agent.py  ← 双人播客脚本
│   │   │   └── orchestrator.py   ← 状态机调度
│   │   ├── api/                  ← REST 接口
│   │   ├── services/             ← 向量库 / DeepSeek / 内容解析
│   │   ├── models/               ← SQLAlchemy 数据模型
│   │   ├── core/                 ← 配置
│   │   └── main.py               ← FastAPI 入口
│   ├── .env.example
│   └── requirements.txt
└── frontend/
    └── src/
        ├── pages/                ← 8 个页面（Home/Copilot/Card/Space/Review/Podcast/Settings/WrongBook）
        ├── components/
        ├── api/
        ├── App.jsx
        └── main.jsx
```

---

## 🛡️ 安全说明

- `.env`（含 API Key / Cookie）已在 `.gitignore` 中排除，**绝不含敏感信息**
- `knowledgeos.db` / `uploads/` / `chroma_db/` / `*.log` / `cloudflared.exe` 均为本地运行时产物，**不会进入版本库**
- 测试文件 `test_*.pdf / test_*.png / gen_test_*.py` 也已忽略

## 📄 License

MIT（私有项目，仅供学习交流）

---

<sub>Powered by DeepSeek · Built with FastAPI + React · V3.0 build</sub>
