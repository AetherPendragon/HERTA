# Herta

基于 RAG 的工业协议处理器代码自动生成系统。从已有协议文档和代码构建知识库，结合 LLM 自动生成目标协议的配置文件和处理代码，并提供多维度的评测对比。

## 功能概览

| 模块 | 说明 |
|------|------|
| 知识库构建 | 解析协议文档（docx/pdf）、C 源码、JSON 配置，构建向量检索索引 |
| Config 生成 | 基于目标协议文档，通过 RAG 检索相关知识生成结构化 JSON 配置 |
| Handler 生成 | 两阶段策略（设计草图 + 完整代码）生成协议处理 C 代码 |
| 评测对比 | 多维相似度计算（拓扑/命令表/遥测/内部处理）+ 函数级 AST 匹配 |
| Web 前端 | Next.js 可视化界面，支持知识库管理、代码生成、评测结果展示 |
| Embedding 可视化 | UMAP 2D 投影展示知识库向量空间分布 |

## 快速开始

### 环境要求

- Python >= 3.12
- Node.js >= 18
- npm

### 后端安装

```bash
# 克隆仓库
git clone https://github.com/fangzheng649/HERTA.git
cd HERTA

# 创建虚拟环境
conda create -n herta python=3.12 -y
conda activate herta

# 安装依赖
pip install -e .
```

### 前端安装

```bash
cd frontend
npm install --legacy-peer-deps
cd ..
```

### 配置

```bash
# 设置智谱 AI API Key
export ZAI_API_KEY='your-api-key'

# 或在 Web 界面 "设置" 页面中配置
```

### 启动服务

```bash
# 启动后端 API（端口 8000）
herta api

# 启动前端开发服务器（端口 3000）
cd frontend && npm run dev
```

访问 http://localhost:3000 即可使用 Web 界面。

### CLI 使用

```bash
# 1. 构建知识库（从源协议 gdwx）
herta buildkb --source gdwx

# 2. 生成目标协议配置
herta generate config --target dllg

# 3. 生成目标协议处理代码
herta generate handler --target dllg

# 4. 评测对比
herta compare --target dllg
```

## 项目结构

```
HERTA/
├── src/herta/                  # 核心代码
│   ├── api/                    # FastAPI 后端（REST API）
│   │   ├── app.py              # 应用入口
│   │   ├── routes/             # API 路由（kb/generate/compare/settings）
│   │   └── task_store.py       # 异步任务管理
│   ├── cli/                    # CLI 命令
│   │   ├── buildkb.py          # 知识库构建
│   │   ├── generate.py         # 代码生成
│   │   ├── compare.py          # 评测对比
│   │   └── app.py              # API 服务启动
│   ├── kb/                     # 知识库模块
│   │   ├── builder.py          # 构建流程编排
│   │   ├── chunker.py          # 分块策略（simple/semantic/proposition）
│   │   ├── code_chunker.py     # 代码专用分块（保持函数/JSON 完整性）
│   │   └── store.py            # FAISS 向量索引
│   ├── generator/              # 生成模块
│   │   ├── config_generator.py # Config 生成（多 query 检索 + 重排序）
│   │   ├── handler_generator.py# Handler 生成（两阶段：plan + code）
│   │   ├── retriever.py        # 知识检索器（向量检索 + bigram 重排序）
│   │   └── target_parser.py    # 目标文档解析
│   ├── compare/                # 评测模块
│   │   ├── json_compare.py     # JSON 配置对比（拓扑/字段/列表）
│   │   ├── function_matcher.py # 函数匹配（匈牙利算法）
│   │   ├── ast_similarity.py   # AST 相似度（树编辑距离）
│   │   └── report_builder.py   # 报告生成
│   ├── parser/                 # 解析器
│   │   ├── doc_parser.py       # 文档解析（docx/pdf）
│   │   └── code_parser.py      # 代码解析（C/JSON）
│   └── llm/                    # LLM 客户端（智谱 AI）
├── frontend/                   # Web 前端
│   ├── src/app/                # Next.js 页面
│   │   ├── (dashboard)/        # 仪表盘
│   │   ├── knowledge/          # 知识库管理 + Embedding 可视化
│   │   ├── generate/           # 代码生成
│   │   ├── compare/            # 评测对比
│   │   └── settings/           # 系统设置
│   ├── src/components/         # UI 组件
│   │   ├── chart-blocks/       # VChart 图表（散点图/柱状图）
│   │   ├── nav/                # 侧边栏导航
│   │   └── ui/                 # shadcn/ui 基础组件
│   └── src/lib/                # API 客户端、工具函数
├── prompts/                    # Prompt 模板
│   ├── generate_config.md
│   ├── generate_handler_plan.md
│   └── generate_handler_code.md
├── data/                       # 数据目录
│   ├── source_proto/gdwx/      # 源协议（文档 + 代码 + 配置）
│   └── target_proto/dllg/      # 目标协议（Ground Truth）
└── output/                     # 输出目录（自动生成）
    ├── generated/              # 生成的配置和代码
    ├── reports/                # 评测报告
    └── visualization/          # UMAP 投影数据
```

## Web 界面

系统提供 5 个主要页面：

| 页面 | 功能 |
|------|------|
| 仪表盘 | 系统概览、最新评测指标、Config 相似度分维图表 |
| 知识库 | 知识库列表、构建/重建、Embedding 2D 散点图可视化 |
| 代码生成 | 选择目标协议和知识库，生成 Config 和 Handler |
| 评测对比 | 选择目标运行评测，展示 7 维分数卡片、柱状图、函数匹配表 |
| 设置 | API Key、LLM 模型配置 |

## 评测指标

Config 相似度（4 个维度加权）：
- **拓扑结构** — 字段完整性、列表类型、元素字段检查
- **命令表** — cmd_list 条目覆盖率和内容匹配
- **遥测处理** — tele_handler 条目覆盖率和内容匹配
- **内部处理** — internal_handler 条目覆盖率和内容匹配

Handler 相似度：
- AST 结构相似度（树编辑距离）
- 语义特征相似度（函数签名、调用关系）
- 匈牙利算法最优匹配

整体相似度 = 0.35 × Config + 0.65 × Handler

## 技术栈

**后端**：Python 3.12, FastAPI, Typer, FAISS, tree-sitter, 智谱 AI (BigModel)

**前端**：Next.js 15, React 19, TypeScript, Tailwind CSS, VChart (VisActor), shadcn/ui

**RAG 链路**：向量检索 + 字符 bigram 重排序 + 多 query 召回 + 结构优先级上下文组装

## 文档

- [架构设计](doc/architecture.md)
- [CLI 使用说明](doc/cli.md)
- [相似度计算](doc/similarity_calculation.md)

## 开发状态

| 功能 | 状态 |
|------|------|
| CLI 框架 | ✅ 完成 |
| 知识库构建（3 种分块策略） | ✅ 完成 |
| 代码专用分块（保持结构完整） | ✅ 完成 |
| Config 生成（RAG 检索增强） | ✅ 完成 |
| Handler 生成（两阶段） | ✅ 完成 |
| 评测对比（JSON + C 代码） | ✅ 完成 |
| Web API（FastAPI） | ✅ 完成 |
| Web 前端（Next.js） | ✅ 完成 |
| Embedding 可视化 | ✅ 完成 |
| 深色主题 | ✅ 完成 |
