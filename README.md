# Herta - 基于 RAG 的协议生成系统

Herta 是一个基于检索增强生成（RAG）的协议生成系统，用于从源协议文档和代码构建知识库，并基于目标协议文档自动生成配置文件和处理代码。

## 核心功能

- **知识库构建**：解析源协议文档（docx/pdf）和代码（C/JSON），构建可检索的向量知识库
- **配置生成**：基于目标协议文档，生成结构化的协议配置文件（config.json）
- **代码生成**：采用两阶段生成策略（设计草图 + 完整代码），生成协议处理代码（handler.c）
- **对比评测**：比较生成结果与真实代码的相似度，输出详细的评测报告

## 快速开始

### 安装

```bash
# 克隆仓库
git clone <repository-url>
cd herta

# 创建虚拟环境
conda create -n herta-rag python=3.12 -y
conda activate herta-rag

# 安装依赖
pip install -e .
```

### 配置环境变量

```bash
export ZAI_API_KEY='your-zhipu-api-key'

# export ZAI_API_KEY='3e490246f5d84188bc140aa3d4ef8cd3.WeMO7N9B7vu8UqDI'
```

### 运行示例

```bash
# 1. 构建知识库
herta buildkb --source gdwx

# 2. 生成配置和代码
herta generate config --target dllg
herta generate handler --target dllg --save-plan

# 3. 对比评测
herta compare --target dllg
```

## 项目结构

```
herta/
├── data/                       # 数据目录
│   ├── source_proto/gdwx/     # 源协议文档和代码
│   ├── target_proto/dllg/     # 目标协议文档和代码
│   └── kb/gdwx/               # 知识库（自动生成）
├── doc/                        # 文档
│   ├── architecture.md         # 架构设计文档
│   ├── cli.md                  # CLI 使用说明
│   └── similarity_calculation.md  # 相似度计算详解
├── prompts/                    # Prompt 模板
│   ├── generate_config.md
│   ├── generate_handler_plan.md
│   └── generate_handler_code.md
├── src/herta/                  # 核心代码
│   ├── cli/                    # CLI 命令
│   ├── parser/                 # 文档和代码解析
│   ├── kb/                     # 知识库构建
│   │   ├── bm25_index.py      # BM25 稀疏索引（新增）
│   │   └── hybrid_store.py    # 融合检索存储（新增）
│   ├── generator/              # 生成模块
│   │   ├── pipeline/          # 统一 Pipeline（新增）
│   │   │   ├── base.py        # Pipeline 基类
│   │   │   ├── config.py      # Pipeline 配置
│   │   │   └── stages.py      # 7 个 Stage 实现
│   │   ├── query_rewriter.py  # 查询改写（新增）
│   │   ├── reranker.py        # LLM 精排（新增）
│   │   ├── context_compressor.py  # 上下文压缩（新增）
│   │   ├── function_registry.py   # 函数清单（新增）
│   │   ├── retriever.py       # 检索器（增强：融合检索）
│   │   ├── handler_generator.py   # Handler 生成器（增强）
│   │   └── config_generator.py    # 配置生成器（增强）
│   ├── compare/                # 对比评测
│   └── llm/                    # LLM 客户端
├── output/                     # 输出目录
│   ├── generated/dllg/        # 生成的配置和代码
│   └── reports/dllg/          # 对比评测报告
└── pyproject.toml             # 项目配置
```

## 支持的命令

### herta buildkb - 构建知识库

```bash
# 使用默认路径构建
herta buildkb --source gdwx

# 指定分块策略
herta buildkb --source gdwx --chunk-strategy semantic

# 强制重建
herta buildkb --source gdwx --force
```

**支持的分块策略**：
- `simple`: 固定大小滑动窗口
- `semantic`: 基于语义相似度的分块
- `autosize`: 自动选择最优分块大小
- `proposition`: 基于原子事实命题的分块

### herta generate - 生成配置和代码

```bash
# 生成配置文件
herta generate config --target dllg

# 生成 handler 代码（两阶段生成）
herta generate handler --target dllg --save-plan
```

### herta compare - 对比评测

```bash
# 对比生成结果与真实代码
herta compare --target dllg

# 输出：
# - output/reports/dllg/metrics.json
# - output/reports/dllg/comparison_report.md
```

**相似度指标**：
- **Config Similarity**: JSON 配置的相似度（拓扑结构、命令表、遥测表、内部处理表）
- **Handler Similarity**: C 代码的 AST 级相似度（基于 tree-edit distance + 语义特征）
- **Overall Similarity**: 整体相似度 = 0.35 × config + 0.65 × handler

## 技术栈

- **CLI 框架**: Typer
- **LLM 接口**: 智谱 AI (BigModel API)
- **向量检索**: FAISS
- **稀疏检索**: BM25 (rank-bm25) ✅ **新增**
- **中文分词**: jieba ✅ **新增**
- **融合检索**: Vector + BM25 ✅ **新增**
- **文档解析**: python-docx, PyMuPDF
- **AST 解析**: tree-sitter
- **相似度计算**: apted (树编辑距离), rapidfuzz (模糊匹配), scipy (匈牙利算法)
- **配置管理**: PyYAML ✅ **新增**

## RAG 技术实现状态

### 已实现的 RAG 技术

#### 1. 分块策略 (Chunking)

**Simple Chunking（简单分块）**
- 基于固定大小和重叠进行滑动窗口分块
- 实现简单，构建速度快
- 使用方法：`herta buildkb --source gdwx --chunk-strategy simple `

**Semantic Chunking（语义分块）**
- 按句子切分，计算相邻句子的 embedding 相似度
- 当相似度低于阈值时切分，保持语义连贯性
- 使用方法：`herta buildkb --source gdwx --chunk-strategy semantic --semantic-threshold-percentile 0.5`

**Auto-size Chunking（自动分块大小选择）**
- 评估多组候选参数，选择最优配置
- 基于平均大小、均匀性、数量平衡等启发式评分
- 使用方法：`herta buildkb --source gdwx --chunk-strategy autosize --candidate-sizes "300,500,800"`

**Proposition Chunking（命题分块）**
- 使用 LLM 将文本拆解为原子事实命题
- 适合知识密集型文档，每个命题成为独立 chunk
- 使用方法：`herta buildkb --source gdwx --chunk-strategy proposition --proposition-model glm-5.1`

#### 2. 检索增强技术

**融合检索 (Fusion Retrieval)** ✅ **新增**
- **向量检索 + BM25 关键词检索联合召回**
- 向量检索捕捉语义相似性，BM25 捕捉精确关键词匹配（函数名、命令字）
- 加权融合：final_score = α*vector_score + (1-α)*bm25_score（默认 α=0.6）
- 显著提升 handler 函数名和命令字的匹配准确率
- 自动集成于 `KnowledgeRetriever`，支持通过参数启用

**重排序 (Reranking)** ✅ **新增**
- **两阶段检索架构**：召回阶段(top 20) → 精排阶段(top 5)
- 使用 LLM 对候选 chunk 进行相关性评分（0-10 分）
- 过滤低分 chunk，提升上下文质量
- 实现模块：`ChunkReranker`

**查询改写 (Query Rewrite)** ✅ **新增**
- **代码语义化改写**：将自然语言查询转换为代码友好的检索形式
- 支持多种模式：`code_semantic`, `structured`, `llm_enhanced`, `hybrid`
- 自动识别函数名、命令字等技术术语
- 实现模块：`QueryRewriter`

#### 3. 上下文优化技术

**上下文压缩 (Contextual Compression)** ✅ **新增**
- **智能压缩**：使用 LLM 提取 chunk 中与任务相关的部分
- 丢弃无关代码/描述，减少 prompt 噪声
- 保持代码结构完整性（函数边界识别）
- 支持 task-aware 压缩策略（config vs handler）
- 实现模块：`ContextCompressor`

**结构化上下文注入 (Structured Context Injection)** ✅ **新增**
- **函数清单强制约束**：从目标协议提取所有需要生成的函数
- 构建 `FunctionList`，包含函数名、类型、命令字映射、依赖关系
- 将函数清单注入 Prompt，强制 LLM 生成完整函数集合
- 后验证机制：检查生成代码中缺失的函数并补充生成
- 实现模块：`FunctionRegistryBuilder`

#### 4. 生成优化技术

**模块化 Pipeline 架构** ✅ **新增**
- **7 阶段统一 Pipeline**：Query Rewrite → Fusion Retrieval → Rerank → Compression → Structured Context → Prompt Building → LLM Generation
- 每个阶段可独立开关，通过 YAML 配置控制
- 支持 Pipeline 模式和传统模式切换（向后兼容）
- 配置路径：`config/rag_pipeline.yaml`
- 实现模块：`UnifiedPipeline`, `PipelineConfig`

**Handler 两阶段生成**
- 阶段A：生成设计草图（plan）- 包含函数列表、命令分发逻辑、TODO 标注
- 阶段B：基于 plan 生成完整 C 代码
- **阶段C（新增）**：后验证与补充生成 - 检查函数完整性并补充缺失函数
- 使用方法：`herta generate handler --target dllg --save-plan`

#### 5. 向量检索（基础）

**基于 FAISS 的相似度检索**
- 使用智谱 AI embedding-3 模型生成 1024 维向量
- 构建 FAISS IndexFlatIP 索引，支持余弦相似度检索
- 自动集成于生成流程中，从知识库召回相关上下文

---

### 新增模块列表

| 模块 | 功能 | 位置 |
|------|------|------|
| `QueryRewriter` | 查询改写（代码语义化） | `generator/query_rewriter.py` |
| `ChunkReranker` | LLM 精排（0-10 评分） | `generator/reranker.py` |
| `ContextCompressor` | 上下文压缩 | `generator/context_compressor.py` |
| `FunctionRegistryBuilder` | 函数清单构建 | `generator/function_registry.py` |
| `BM25Index` | BM25 稀疏索引 | `kb/bm25_index.py` |
| `HybridIndexStore` | 融合索引存储 | `kb/hybrid_store.py` |
| `UnifiedPipeline` | 统一 Pipeline 编排器 | `generator/pipeline/` |

---

### 未实现的 RAG 技术（后续扩展方向）

#### 1. 检索优化方向

- **上下文增强 (Context Enriched Retrieval)**：自动补充前后相邻块，恢复完整上下文
- **相关片段提取 (Relevant Segment Extraction)**：从多个连续块拼接成完整语义片段

#### 2. 生成优化方向

- **上下文块标题 (Contextual Chunk Headers)**：chunk 中加入文档标题、章节信息，增强层级理解
- **文档增强 (Document Augmentation)**：为 chunk 生成问题、标签、摘要并索引
- **多模态 RAG (Multimodal RAG)**：支持图片、表格、流程图等多模态内容
- **强化学习 RAG (RAG with RL)**：基于生成质量反馈优化检索与生成策略

#### 3. 高级 RAG 架构方向

- **自适应 RAG (Adaptive RAG)**：根据任务类型动态选择检索与生成策略
- **自反思 RAG (Self-RAG)**：增加自我评估步骤，降低幻觉风险
- **纠正性 RAG (CRAG)**：评估检索质量，不足时触发纠正流程
- **分层 RAG (Hierarchy RAG)**：建立摘要层与细节层两级索引
- **图 RAG (Graph RAG)**：抽取实体与关系，构建知识图谱，支持多跳推理
- **HyDE (Hypothetical Document Embeddings)**：生成假设答案向量进行检索
- **反馈循环 RAG (Feedback Loop RAG)**：记录用户反馈持续优化策略

## 文档

- [架构设计文档](doc/architecture.md) - 系统架构、模块设计、数据流
- [CLI 使用说明](doc/cli.md) - 详细的命令说明和参数介绍
- [相似度计算详解](doc/similarity_calculation.md) - config.json 和 handler.c 的相似度计算方法

## 开发状态

| 功能 | 状态 | 说明 |
|------|------|------|
| CLI 框架 | ✅ 完成 | Typer 框架 |
| 知识库构建 (4 种分块策略) | ✅ 完成 | simple/semantic/auto-size/proposition |
| **BM25 稀疏索引** | ✅ **新增** | rank-bm25 实现 |
| **融合检索** | ✅ **新增** | Vector + BM25，α=0.6 |
| **Query 改写** | ✅ **新增** | 4 种模式：code_semantic/structured/llm_enhanced/hybrid |
| **两阶段检索** | ✅ **新增** | 召回 20 → 精排 5 |
| **上下文压缩** | ✅ **新增** | LLM 提取相关部分 |
| **函数清单注入** | ✅ **新增** | 强制生成完整函数集合 |
| **Pipeline 架构** | ✅ **新增** | 7 阶段模块化 Pipeline |
| 配置生成 (config.json) | ✅ 完成 | 支持 Pipeline 和传统模式 |
| Handler 生成 (两阶段→三阶段) | ✅ 完成 | Plan + Code + Verification |
| 对比评测 (JSON + C 代码) | ✅ 完成 | AST 级相似度计算 |
| runall 一键执行 | 📝 预留 | 尚未实现 |


## 致谢

本项目使用以下开源库：
- [Typer](https://github.com/tiangolo/typer) - CLI 框架
- [FAISS](https://github.com/facebookresearch/faiss) - 向量检索
- [rank-bm25](https://github.com/dorianbrown/rank_bm25) - BM25 稀疏检索 ✅ **新增**
- [jieba](https://github.com/fxsjy/jieba) - 中文分词 ✅ **新增**
- [tree-sitter](https://github.com/tree-sitter/tree-sitter) - AST 解析
- [apted](https://github.com/MichaelHahsler/apted) - 树编辑距离
- [rapidfuzz](https://github.com/maxbachmann/RapidFuzz) - 模糊字符串匹配
- [PyYAML](https://pyyaml.org/) - YAML 配置解析 ✅ **新增**
