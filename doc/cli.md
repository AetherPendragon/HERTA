# 1. 文档目的

本文档定义 Herta 软件系统的命令行接口规范，供 Cursor 后续实现 `herta` 可执行命令时参考。

Herta 不直接通过 `python cli.py ...` 形式使用，而是封装为统一入口命令：

```bash
herta <command> [options]
```

通过 `pyproject.toml` 将 `herta` 注册为控制台命令。

---

# 2. CLI 设计目标

Herta CLI 应满足以下要求：

* 命令短小直观。
* 默认路径尽量基于项目目录自动推断。
* 同一实验流程可以拆开执行，也可以一键执行。
* 输出尽量结构化，便于日志记录和脚本集成。
* 适配当前实验目录结构。

---

# 3. 根命令

```bash
herta --help
```

功能：

* 展示全局帮助信息。
* 列出所有子命令。

推荐全局选项：

* `--project-root <path>`：指定项目根目录，默认当前工作目录。
* `--config <path>`：指定系统配置文件。
* `--verbose`：输出详细日志。
* `--quiet`：仅输出关键结果。
* `--dry-run`：仅检查流程和参数，不真正执行。

---

# 4. 命令总览

Herta 目前提供的子命令：

1. `buildkb`：构建源协议知识库
2. `generate`：基于目标协议文档生成代码
   - `generate config`：生成 config.json
   - `generate handler`：生成 handler.c
3. `compare`：比较生成结果与真实结果

预留子命令（尚未实现）：

4. `runall`：一键完成完整的实验流程
---

# 5. 命令详细说明

## 5.1 `herta buildkb`

### 作用

从源协议文档与配套代码构建本地知识库。

### 典型用法

#### 用默认目录构建 `gdwx` 知识库

```bash
herta buildkb --source gdwx
```

#### 显式指定路径构建知识库

```bash
herta buildkb \
  --source gdwx \
  --input data/source_proto/gdwx/internal_handler.c \
  --out data/kb/gdwx
```

### 参数说明

* `--source <name>`：源协议名称，例如 `gdwx`
* `--input <path>`：用于构建知识库的文件夹所在的路径
* `--out <path>`：知识库输出目录路径
* `--force`：如果知识库已存在则强制覆盖重建
* `--embed-model <name>`：指定 embedding 模型名称
* `--chunk-strategy <name>`：分块策略
* `--build-bm25`：同时构建 BM25 稀疏索引（用于融合检索）✅ **新增**

#### 分块用参数详细介绍

* `--chunk-strategy <name>`：分块策略，可选值：

  * `simple`
  * `semantic`
  * `auto-size`
  * `proposition`

默认: `simple`


#### 简单分块参数（`simple`）

* `--chunk-size <int>`：固定分块大小
* `--chunk-overlap <int>`：相邻块重叠大小

默认：

* `chunk-size = 1000`
* `chunk-overlap = 200`

#### 语义分块参数（`semantic`）

基于句子嵌入相似度识别语义边界进行分块，适合内容语义边界清晰的文档。

* `--semantic-threshold-percentile <int>`：语义边界阈值分位数，例如 `90`
* `--semantic-min-sentences <int>`：每个块至少包含的句子数
* `--semantic-max-chars <int>`：单个语义块最大字符数，避免块过大

#### 分块大小选择参数（`auto-size`）

启发式评估多个候选参数组合，自动选择最优分块配置。

* `--candidate-sizes <list>`：候选 chunk size 列表，例如 `500,1000,1500`
* `--candidate-overlaps <list>`：候选 overlap 列表，例如 `100,200,300`
* `--eval-questions <path>`：评估问题集路径
* `--eval-metric <name>`：参数选择时的评估指标，例如：

  * `faithfulness`
  * `relevancy`
  * `semantic-similarity`
  * `hybrid`
* `--selection-output <path>`：保存最优参数选择结果

#### 命题分块参数（`proposition`）

使用 LLM 将文本分解为原子事实命题，适合需要细粒度语义检索的场景。

* `--proposition-model <name>`：命题抽取所用模型
* `--max-propositions-per-chunk <int>`：每个 chunk 允许的最大命题数
* `--proposition-batch-size <int>`：命题抽取批处理大小
* `--proposition-cache`：启用命题抽取缓存，避免重复调用模型


### 默认路径推断规则

当只提供 `--source gdwx` 时，系统默认使用：

*  构建知识库的文件 ：`data/source_proto/gdwx/`
*  输出 ：`data/kb/gdwx/`

### 输出

成功后输出：

* 知识库目录所在路径
* chunk 数量
* 索引构建状态
* 元数据文件位置

### 用法示例

#### 1. 使用默认配置构建 `gdwx` 知识库

```bash
herta buildkb --source gdwx
```

#### 2. 使用简单分块构建知识库

```bash
herta buildkb \
  --source gdwx \
  --chunk-strategy simple \
  --chunk-size 1000 \
  --chunk-overlap 200
```

#### 3. 使用语义分块构建知识库

```bash
herta buildkb \
  --source gdwx \
  --chunk-strategy semantic \
  --semantic-threshold-percentile 90
```

#### 4. 使用分块大小选择器自动挑选最佳参数

```bash
herta buildkb \
  --source gdwx \
  --chunk-strategy auto-size \
  --candidate-sizes 500,1000,1500 \
  --candidate-overlaps 100,200,300 \
  --eval-questions data/eval/gdwx_questions.json
```

#### 5. 使用命题分块构建知识库

```bash
herta buildkb \
  --source gdwx \
  --chunk-strategy proposition \
  --proposition-model gpt-4.1 \
  --max-propositions-per-chunk 8
```

### 执行逻辑

1. 解析输入文件路径。
2. 加载源协议文档和代码文件。
3. 根据 `--chunk-strategy` 选择分块器。
4. 生成 chunk 与 metadata。
5. 计算 embedding。
6. 构建并保存向量索引（FAISS）。
7. **构建 BM25 稀疏索引（可选）** ✅ **新增**
8. 输出构建报告。

### 融合检索支持 ✅ **新增**

当使用 `--build-bm25` 参数构建知识库时，系统会同时生成：
- `vector.index` - FAISS 向量索引（语义检索）
- `bm25_index.pkl` - BM25 稀疏索引（关键词检索）

在生成阶段，可以启用融合检索：
```bash
# 启用融合检索（alpha 控制向量权重，默认 0.6）
herta generate handler --kb gdwx --target dllg --fusion-alpha 0.6
```

融合检索公式：`final_score = α * vector_score + (1-α) * bm25_score`

推荐值：
- `α=0.6`：平衡语义和关键词匹配（默认）
- `α=0.8`：更侧重语义匹配
- `α=0.4`：更侧重关键词匹配（适合函数名检索）

### 输出

成功后输出：

* 知识库目录
* chunk 数量
* 所用分块策略
* 关键分块参数
* 索引构建状态
* 元数据文件位置
* 构建报告位置

### 建议生成的构建报告

建议新增：

* `data/kb/gdwx/build_report.json`

内容至少包括：

* 输入文件列表
* 分块策略
* 分块参数
* chunk 总数
* 平均 chunk 长度
* embedding 模型
* 构建耗时
* 是否成功





---

## 5.2 `herta generate`

### 作用

读取目标协议文档，结合已构建知识库和 LLM API，生成目标协议配置与处理代码。

### 典型用法

#### 使用 `gdwx` 知识库生成 `dllg`

```bash
herta generate --kb gdwx --target dllg
```

#### 显式指定目标文档和输出目录

```bash
herta generate \
  --kb data/kb/gdwx \
  --target-doc data/target_proto/dllg/dllg.doc \
  --out output/generated/dllg
```

### 参数说明

* `--kb <path>`：知识库路径，默认 data/kb/gdwx
* `--target <name>`：目标协议名称
* `--target-doc <path>`：目标协议文档路径，默认 data/target_proto/dllg/dllg.doc
* `--out <path>`：生成文件输出目录
* `--model <name>`：指定 LLM 模型名称
* `--use-pipeline`：启用 Pipeline 模式（默认启用）✅ **新增**
* `--pipeline-config <path>`：指定 Pipeline 配置文件路径，默认 config/rag_pipeline.yaml ✅ **新增**
* `--fusion-alpha <float>`：融合检索权重（0-1），默认 0.6 ✅ **新增**
* `--top-k <int>`：检索候选数量，默认 20（Pipeline 召回阶段）✅ **新增**
* `--save-plan`：（handler 生成）保存设计计划
* `--save-prompts`：保存生成的 Prompt 文本
* `--save-context`：保存检索到的上下文

#### Pipeline 模式配置 ✅ **新增**

Pipeline 模式通过 YAML 配置文件控制各阶段开关：

```bash
# 使用默认 Pipeline 配置生成 handler
herta generate handler --kb gdwx --target dllg

# 使用自定义 Pipeline 配置
herta generate handler --kb gdwx --target dllg --pipeline-config my_pipeline.yaml

# 禁用 Pipeline，使用传统模式
herta generate handler --kb gdwx --target dllg --use-pipeline=false
```

Pipeline 阶段开关配置（config/rag_pipeline.yaml）：
- `query_rewrite`: 查询改写（代码语义化）
- `retrieval`: 融合检索（Vector + BM25）
- `rerank`: LLM 精排（0-10 评分）
- `context_compression`: 上下文压缩
- `structured_context`: 函数清单注入（仅 handler）
- `prompt_building`: Prompt 构建
- `llm_generation`: LLM 生成


### 默认路径推断规则

当使用：

```bash
herta generate --kb gdwx --target dllg
```

默认解析为：

* 知识库：`data/kb/gdwx/`
* 目标文档：`data/target_proto/dllg/dllg.doc`
* 输出目录：`output/generated/dllg/`
* 中间产物目录：`output/intermediate/dllg/`

### 默认输出文件

* `output/generated/dllg/dllg_config.json`
* `output/generated/dllg/dllg_handler.c`

### 执行逻辑（Pipeline 模式）✅ **更新**

1. 解析目标协议文档。
2. **Query Rewrite**：改写查询为代码语义化形式。
3. **Fusion Retrieval**：执行向量检索 + BM25 检索，召回候选。
4. **Rerank**：使用 LLM 对候选 chunk 评分，取 top 5。
5. **Context Compression**：压缩上下文，提取相关部分。
6. **Structured Context**（仅 handler）：构建函数清单，注入 Prompt。
7. **Prompt Building**：组装最终 Prompt。
8. **LLM Generation**：生成配置文件或 handler 代码。
9. **后验证**（仅 handler）：检查函数完整性，补充缺失函数。
10. 保存中间产物和模型输出。

### 执行逻辑（传统模式，向后兼容）

1. 解析目标协议文档。
2. 从知识库检索相关上下文（纯向量检索）。
3. 生成配置文件或 handler 代码。
4. 保存中间产物和模型输出。

---

## 5.3 `herta compare`

### 作用

比较 LLM 生成的 `config.json` 与 `handler.c` 和预期真实文件之间的相似度，输出结构化的 `metrics.json` 与可读性强的 `comparison_report.md`。

对比维度：
- **Config JSON**：拓扑结构、命令表、遥测表、内部处理表（4 个维度 + 加权总分）
- **Handler C**：基于 AST 的函数级相似度（tree-edit distance + 语义特征）

### 典型用法

#### 使用默认目录比较 `dllg`

```bash
herta compare --target dllg
```

#### 显式指定生成文件与真实文件

```bash
herta compare \
  --target dllg \
  --gen-config output/generated/dllg/dllg_config.json \
  --gt-config data/target_proto/dllg/dllg_config.json \
  --gen-handler output/generated/dllg/dllg_handler.c \
  --gt-handler data/target_proto/dllg/dllg_handler.c \
  --report output/reports/dllg/comparison_report.md \
  --metrics output/reports/dllg/metrics.json
```

### 参数说明

#### 输入参数

* `--target <name>`：目标协议名称（必填），用于默认路径推断
* `--gen-config <path>`：生成的配置文件路径（默认自动推断）
* `--gt-config <path>`：真实的配置文件路径（默认自动推断）
* `--gen-handler <path>`：生成的 handler.c 路径（默认自动推断）
* `--gt-handler <path>`：真实的 handler.c 路径（默认自动推断）

#### 输出参数

* `--report <path>`：Markdown 报告输出路径（默认：`output/reports/<target>/comparison_report.md`）
* `--metrics <path>`：JSON 指标输出路径（默认：`output/reports/<target>/metrics.json`）

### 默认路径推断规则

当只提供 `--target`：

```bash
herta compare --target dllg
```

默认使用：

| 文件类型 | 默认路径 |
|---------|---------|
| 生成配置 | `output/generated/dllg/dllg_config.json` |
| 真实配置 | `data/target_proto/dllg/dllg_config.json` |
| 生成代码 | `output/generated/dllg/dllg_handler.c` |
| 真实代码 | `data/target_proto/dllg/dllg_handler.c` |
| Markdown 报告 | `output/reports/dllg/comparison_report.md` |
| JSON 指标 | `output/reports/dllg/metrics.json` |

### 对比算法说明

#### Config JSON 比较

1. **topology_similarity** (20% 权重)
   - 检查 4 层树结构：根节点 → 6 个顶层字段 → 3 个列表 → 列表元素字段
   - 归一化为 0~100 百分制

2. **cmd_list_similarity** (30% 权重)
   - 按 `cmd` 字段对齐命令项
   - 比较 `handler` 精确匹配和 `desc` 模糊匹配（rapidfuzz）

3. **tele_handler_similarity** (30% 权重)
   - 按 `handler` 对齐遥测项
   - 比较 `len`、`desc` 字段

4. **internal_handler_similarity** (20% 权重)
   - 按 `handler` 对齐内部处理项
   - 比较 `len`、`desc` 字段

5. **config_similarity** (加权总分)
   - 加权公式：0.2*topology + 0.3*cmd_list + 0.3*tele_handler + 0.2*internal

#### Handler C 比较

1. **AST 解析**：使用 tree-sitter 解析 C 代码，提取函数定义
2. **相似度计算**：
   - tree_edit_similarity (70%)：使用 apted 算法计算树编辑距离
   - semantic_feature_similarity (30%)：比较调用函数、字面量、赋值模式等
3. **函数匹配**：使用 scipy.optimize.linear_sum_assignment（匈牙利算法）求解最优一对一匹配
4. **handler_similarity**：基于所有真实函数的平均相似度 + 覆盖率 + 同名率

5. **overall_similarity** (整体相似度)
   - 加权公式：0.35*config_similarity + 0.65*handler_similarity

### 输出内容

#### metrics.json 结构

```json
{
  "target": "dllg",
  "generated_at": "2024-01-01T00:00:00",
  "topology_similarity": 85.0,
  "cmd_list_similarity": 78.5,
  "tele_handler_similarity": 82.0,
  "internal_handler_similarity": 75.5,
  "config_similarity": 80.2,
  "handler_similarity": 72.8,
  "overall_similarity": 75.4,
  "config_details": { ... },
  "function_match_results": [ ... ],
  "unmatched_gt_functions": [ ... ],
  "unmatched_gen_functions": [ ... ]
}
```

#### comparison_report.md 结构

- 总体评分和雷达图（文字描述）
- Config 详细分析（4 个维度逐项展示）
- Handler 代码分析（函数匹配表格、未匹配函数列表）
- 总结与改进建议

### 相似度评分标准

| 分数范围 | 评价 | 建议 |
|---------|------|------|
| 80-100 | 优秀 | 生成结果与真实代码高度相似 |
| 60-79 | 良好 | 生成结果基本可用，部分细节需调整 |
| 40-59 | 一般 | 生成结果需要较多修改 |
| 0-39 | 较差 | 建议重新生成或调整策略 |

### 依赖要求

compare 命令需要以下额外依赖（已包含在 requirements.txt）：
- `tree-sitter` + `tree-sitter-c`：C 代码 AST 解析
- `apted`：树编辑距离算法
- `rapidfuzz`：模糊字符串匹配
- `scipy`：匈牙利算法（linear_sum_assignment）

安装命令：
```bash
pip install tree-sitter tree-sitter-c apted rapidfuzz scipy
```

---

## 5.4 `herta runall`【预留】

### 作用

一键执行完整实验：构建知识库、生成代码、对比评测。

### 状态

**该命令为预留功能，尚未实现。**

### 计划用法

```bash
herta runall --source gdwx --target dllg
```

### 预计参数

* `--source <name>`：源协议名称
* `--target <name>`：目标协议名称
* `--source-dir <path>`：源协议目录
* `--target-dir <path>`：目标协议目录
* `--kb-out <path>`：知识库输出目录
* `--gen-out <path>`：生成结果输出目录
* `--report-out <path>`：报告输出目录
* `--skip-compare`：跳过对比评测
* `--force`：强制覆盖旧结果

### 预计执行顺序

1. `buildkb`
2. `generate`
3. `compare`

### 使用场景

适用于一次性完成完整实验验证。

**当前替代方案**：需依次手动执行 `buildkb`、`generate config`、`generate handler`、`compare` 命令。

---


# 6. 推荐使用示例

## 6.1 典型完整实验流程

### 第一步：构建知识库（启用 BM25 用于融合检索）✅ **更新**

```bash
herta buildkb --source gdwx --build-bm25
```

### 第二步：生成 `dllg` 代码（Pipeline 模式）✅ **更新**

生成配置文件（Pipeline 模式）：
```bash
herta generate config --kb gdwx --target dllg --save-prompts --save-context
```

生成 handler 代码（Pipeline 模式，融合检索 + 函数清单）：
```bash
herta generate handler --kb gdwx --target dllg --save-plan --save-prompts --fusion-alpha 0.6
```

### 高级用法：自定义 Pipeline 配置 ✅ **新增**

```bash
# 使用自定义 Pipeline 配置
herta generate handler --kb gdwx --target dllg --pipeline-config config/my_pipeline.yaml

# 禁用 Query Rewrite
herta generate handler --kb gdwx --target dllg --no-query-rewrite

# 调整融合检索权重（更侧重函数名匹配）
herta generate handler --kb gdwx --target dllg --fusion-alpha 0.4
```

### 第三步：对比结果

```bash
herta compare --target dllg
```

对比完成后，查看生成的报告：
```bash
cat output/reports/dllg/comparison_report.md
```

---

## 6.2 一键执行【预留】

```bash
herta runall --source gdwx --target dllg --force
```

**注意**：`runall` 命令为预留功能，尚未实现。当前需依次执行 `buildkb`、`generate config`、`generate handler`、`compare` 命令。

---

# 7. 退出码约定

建议 CLI 遵循以下退出码：

* `0`：成功
* `1`：通用错误
* `2`：参数错误
* `3`：文件不存在或路径错误
* `4`：知识库不存在
* `5`：LLM 调用失败
* `6`：输出解析失败
* `7`：对比评测失败

---

## 8. 后续可扩展命令

未来可增加：

* `herta env`：检查环境变量和依赖
* `herta clean`：清理输出和缓存
* `herta init`：初始化项目

---

# 9. 当前可用命令集合

## 已实现的命令（基础功能）

* `herta buildkb --source gdwx`
* `herta generate config --kb gdwx --target dllg`
* `herta generate handler --kb gdwx --target dllg`
* `herta compare --target dllg`

## 已实现的命令（增强功能）✅ **新增**

* `herta buildkb --source gdwx --build-bm25` - 构建融合检索知识库
* `herta generate config --kb gdwx --target dllg --use-pipeline` - Pipeline 模式生成配置
* `herta generate handler --kb gdwx --target dllg --fusion-alpha 0.6` - 融合检索生成 handler

## 预留的命令

* `herta runall --source gdwx --target dllg`（尚未实现）
