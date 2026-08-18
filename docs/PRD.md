# KnowledgeOS V3.0 产品需求文档（PRD）

版本：V3.0

## 产品定位

AI个人知识操作系统（Personal Knowledge OS）

## 产品目标

帮助用户完成： 输入 → 理解 → 沉淀 → 复习 → 应用

形成个人AI第二大脑。

## 核心问题

-   信息碎片化，知识难沉淀
-   AI总结停留在摘要层面
-   知识无法复用
-   普通聊天AI无法理解个人知识资产

## 功能架构

KnowledgeOS

-   首页 Dashboard
-   知识管理 Knowledge Library
-   AI Copilot
-   学习复习 Review

## 首页 Dashboard

设计要求： - 黑白极简 - 高级留白 - 类 Linear / Notion 风格 - 禁止AI
emoji、卡通元素

标题： Build your second brain.

副标题： Turn scattered information into structured knowledge.

## Capture Agent

支持： - B站视频 - 小红书链接 - 抖音链接 - PDF - Word - 图片 - 文本

流程：

输入内容 → 内容解析 → AI知识蒸馏 → 生成知识卡片 → 用户确认保存

## AI知识蒸馏

输出：

1.  一句话理解
2.  核心概念
3.  知识结构
4.  实践应用
5.  下一步学习建议

## Knowledge Card

包含： - 标题 - 核心理解 - 知识点 - 标签 - 来源 - 学习状态

支持： - 删除 - 编辑 - 收藏 - 修改标签

## 知识分类

取消AI强制分类。

采用用户自定义知识空间：

-   AI产品经理
-   Python
-   英语
-   求职
-   课程学习

AI仅提供标签建议。

## AI Copilot

三种模式：

### 知识问答

基于个人知识库回答，并引用来源。

### 知识连接

发现不同知识之间的关系。

### 学习辅助

生成学习路线、面试题和实践任务。

## Multi-Agent

Knowledge Analyst Agent： 负责内容理解和重点提取。

Knowledge Editor Agent： 负责结构化输出和知识卡片生成。

Learning Coach Agent： 负责复习和学习规划。

## 学习复习 Review

用户选择：

-   最近学习
-   指定知识空间
-   指定知识卡片
-   薄弱知识

模式：

-   理解模式
-   应用模式
-   面试模式
-   快速检测

题型：

-   概念题
-   应用题
-   思考题

## RAG能力

Document → Embedding → Vector Database → Retriever → LLM

实现： - 私人知识库检索 - 个性化问答 - 来源引用

## MVP优先级

P0： - 多格式输入 - AI知识蒸馏 - 知识卡片 - Personal RAG - AI Copilot

P1： - 标签体系 - 智能复习 - 知识关联

P2： - 知识地图 - 成长评分 - AI能力评价

## 开发要求

请基于该PRD： 1. 重构AI输出质量； 2. 优化知识卡片； 3. 实现Personal
RAG； 4. 删除低价值功能； 5.
提升产品从"AI总结工具"到"个人知识操作系统"的能力。
