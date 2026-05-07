# META

* 可以直接用 **Z.ai Python SDK** 或 REST API 调用对话模型与 embedding 模型；官方 SDK 当前文档给出的安装方式是 `pip install zai-sdk`，并通过 `ZhipuAiClient` 创建客户端。([BigModel Documentation][1])
* 文本向量可以直接走官方 **`/paas/v4/embeddings`** 接口，`embedding-3` 支持 256/512/1024/2048 维可选，单条输入最多 3072 tokens、单次最多 64 条；`embedding-2` 固定 1024 维、单条最多 512 tokens。([BigModel Documentation][2])
* 文档解析可以用官方**文件解析服务**，它支持 PDF、Word、Excel、PPT、CSV、TXT、MD 等格式，并可输出纯文本或 Markdown/结构化结果。([BigModel Documentation][3])
* 智谱还提供了**托管知识库/检索 API**，支持向量检索、关键词检索、混合检索、查询重写、重排等能力。([BigModel Documentation][4])

但对你这个项目，我更建议采用这条路线：

> **智谱负责：文档解析（可选）+ embeddings + LLM 生成**
> **你自己的系统负责：切块、metadata、向量库、检索编排、代码生成流程控制**

原因很简单：你现在要做的是**协议工程生成系统**，后续还会持续调整 chunk 策略、检索策略、prompt 和生成约束。自己掌握 chunk 和向量库，会比把知识库全托管到平台上更容易调试，也更适合 Cursor 分阶段落代码。官方托管知识库可以作为后续备选方案。([BigModel Documentation][3])

2026.4.20.19.00

# 一、在接入 BigModel API 后的最小可跑通方案

## 1. 总体目标

当前阶段只做两件事：

1. **构建知识库**

   * 解析源协议文档与代码
   * 切块
   * 生成 embedding
   * 建立本地向量索引

2. **基于目标协议生成代码**

   * 解析目标协议文档
   * 从知识库检索相关上下文
   * 调用智谱 LLM
   * 生成：

     * `config.json`
     * `handler.c`

暂时**不做比较模块**，这和你当前目标一致。

---

# 二、建议采用的系统架构

## 2.1 推荐架构

```text
输入文件
├─ 源协议文档/代码
│  ├─ gdwx.docx
│  ├─ gdwx_config.json
│  ├─ cmd_handler.c
│  ├─ gdwx_handler.c
│  └─ internal_handler.c
└─ 目标协议文档
   └─ dllg.doc

流程A：构建知识库
1. 文档解析
2. 文本预处理
3. 文本切块
4. 调用 BigModel embeddings
5. 本地向量库存储（FAISS）
6. 保存 chunks + metadata

流程B：生成 config.json / handler.c
1. 解析目标协议文档
2. 抽取生成任务所需结构化信息
3. 生成查询
4. 检索知识库
5. 组装 Prompt
6. 调用 BigModel chat completions
7. 输出 config.json 和 handler.c
```

---

# 三、BigModel API 在这个项目里的职责分工

## 3.1 你会实际用到的官方能力

### A. 对话模型 API

官方提供同步对话补全接口 **`POST /paas/v4/chat/completions`**，支持普通文本对话、工具调用、流式/非流式输出；文档中列出的可用模型包括 `glm-5.1`、`glm-5-turbo`、`glm-5`、`glm-4.7`、`glm-4.6`、`glm-4.5-air`、`glm-4.5-flash` 等。([BigModel Documentation][5])

在你的项目中，它主要负责：

* 从目标协议文档抽取结构化协议信息
* 根据检索上下文生成 `config.json`
* 根据检索上下文生成 `handler.c`

### B. Embedding API

官方 embedding 接口是 **`POST /paas/v4/embeddings`**。`embedding-3` 支持字符串或字符串数组输入，默认 2048 维，可选 256/512/1024/2048 维；`embedding-2` 固定 1024 维。([BigModel Documentation][2])

在你的项目中，它主要负责：

* 为 chunk 生成向量
* 为检索 query 生成向量

### C. 文件解析服务

官方文件解析服务支持 `PDF、Word、Excel、PPT、CSV、MD、TXT` 等格式，并能输出纯文本或 Markdown/结构化结果，典型应用场景就包含知识库构建。([BigModel Documentation][3])

在你的项目中，它适合：

* 解析 `gdwx.docx` / `dllg.doc` 这类协议文档
* 降低 Word/PDF 手工清洗难度

---

# 四、为什么不建议第一阶段直接用智谱托管知识库

智谱确实有知识库 API：可以创建知识库，也支持检索，而且检索支持向量检索、关键词检索、混合检索、查询重写、重排等。([BigModel Documentation][6])

但你这个项目第一阶段不建议直接依赖它，原因有四个：

1. **你需要自定义切块策略**
   你已经明确要支持固定分块、语义分块、分块大小选择、命题分块。托管知识库虽然会自动处理切片，但对 chunk 细节控制较弱。([BigModel Documentation][7])

2. **你需要精细 metadata**
   例如：

   * 来源文件名
   * 文档章节
   * 是配置样例还是处理逻辑
   * 关联命令字/字段名
   * chunk 所属代码函数

   这些对后续生成 `config.json` 和 `handler.c` 都很关键。

3. **你需要能精确调试检索上下文**
   本地 FAISS + `chunks.jsonl` 更容易排查“为什么没召回某块”。

4. **你后面要让 Cursor 分阶段写代码**
   本地向量库方案最适合分模块实现和调试。

所以第一阶段建议：
**BigModel = 模型能力提供者**，
**Herta = RAG orchestrator（编排器）**。

---

# 五、如何跑通“构建知识库”

## 5.1 输入来源

### 源协议侧

* `gdwx.docx`
* `gdwx_config.json`
* `cmd_handler.c`
* `gdwx_handler.c`
* `internal_handler.c`

### 目标协议侧

* `dllg.doc`

---

## 5.2 文档解析

### 文档文件

对 `doc/docx/pdf`，优先两种方式：

* **方案1：官方文件解析服务**

  * 优点：对复杂版式友好
  * 适合后续扩展
* **方案2：本地解析**

  * docx: `python-docx`
  * pdf: `PyMuPDF`

对于你的第一阶段，我建议：

* `doc/docx/pdf`：优先预留“官方文件解析服务适配器”
* `json/c`：直接本地读取即可，不需要走文件解析 API

因为 C 代码和 JSON 原本就是结构化文本，直接读文件更稳。

---

## 5.3 文本标准化

不管文本来自官方解析服务还是本地解析，都要先统一做预处理：

* 去掉多余空白
* 统一换行
* 保留标题层级
* 为代码块保留语言类型
* 把“协议字段定义 / 示例配置 / 处理函数”打上类型标签

建议输出中间结构：

```json
{
  "source": "gdwx",
  "file": "gdwx.docx",
  "kind": "document",
  "section": "遥测帧格式",
  "text": "..."
}
```

---

## 5.4 文本切块

你现在已经确定系统要支持四类 chunking。
在 BigModel API 条件下，这四类都能做，因为 **切块本身不依赖特定平台能力**，只是 embedding 和后续生成会调用 BigModel。

建议规则如下：

### 1）简单分块

适合先跑通主流程。

```python
chunk_size = 1000
chunk_overlap = 200
```

### 2）语义分块

先按句子或段落切，再根据相邻单元 embedding 相似度决定边界。
这里的句子/段落 embedding 仍然直接调用 BigModel 的 embedding 接口。([BigModel Documentation][2])

### 3）分块大小选择

对多组 `(chunk_size, overlap)` 试跑，选对协议生成任务最有效的参数。
第一阶段可以先只做“离线评估模式”，不必一上来就自动化很重。

### 4）命题分块

这类需要先调用对话模型，把长文本拆成原子事实，再把事实列表作为 chunk。
也就是：

* 输入：文档段落
* 调用：chat completions
* 输出：命题列表
* 然后再对命题做 embedding

这一步完全可以由智谱对话模型完成。([BigModel Documentation][5])

---

## 5.5 调用 BigModel Embedding API 生成向量

### 推荐模型

第一阶段建议默认用 **`embedding-3`**。
原因是它支持更长单条输入和可选维度，适合你后面在精度/成本之间调优。官方文档写明 `embedding-3` 单条最多 3072 tokens，最多 64 条数组输入，且维度可选 256/512/1024/2048。([BigModel Documentation][2])

### 推荐维度

第一阶段建议先用：

* `dimensions = 1024`

理由：

* 比 2048 更省空间
* 比 256/512 更稳
* 足够先跑通协议类知识库检索

### Python SDK 调用方式

官方 SDK 使用 `ZhipuAiClient`。([BigModel Documentation][1])

示意代码：

```python
from zai import ZhipuAiClient
import os

client = ZhipuAiClient(api_key=os.getenv("ZAI_API_KEY"))

resp = client.embeddings.create(
    model="embedding-3",
    input=["chunk1 text", "chunk2 text"],
    dimensions=1024,
)

vectors = [item.embedding for item in resp.data]
```

如果你后面更想用 REST，也可以直接调：

* `POST https://open.bigmodel.cn/api/paas/v4/embeddings` ([BigModel Documentation][2])

---

## 5.6 构建本地向量知识库

第一阶段建议本地使用 **FAISS**。

保存四类产物：

```text
data/kb/gdwx/
├── chunks.jsonl
├── meta.json
├── embeddings.npy
└── vector.index
```

### `chunks.jsonl`

每一行一个 chunk：

```json
{
  "chunk_id": "gdwx_000012",
  "source": "gdwx",
  "file": "gdwx.docx",
  "kind": "document",
  "section": "遥测字段定义",
  "chunk_strategy": "semantic",
  "chunk_index": 12,
  "text": "...",
  "token_count": 280
}
```

### `vector.index`

FAISS 索引。

### `embeddings.npy`

原始向量数组。

### `meta.json`

记录：

* embedding 模型
* 向量维度
* 分块策略
* 构建时间
* 输入文件列表

---

# 六、如何跑通“检索知识库”

## 6.1 基础检索流程

当你要生成 `config.json` 或 `handler.c` 时，系统先构造 query，然后：

1. 把 query 发给 embedding API
2. 得到 query vector
3. 在本地 FAISS 中做 Top-K 检索
4. 读回对应 chunk 文本与 metadata
5. 组装 prompt 给 chat model

这一步只需要 BigModel 的 embedding，不需要把检索也托管到平台。

---

## 6.2 建议的检索粒度

### 生成 `config.json` 时

优先召回：

* 源协议配置样例块
* 文档中字段定义块
* 命令/帧结构说明块
* 目标协议文档里的字段说明摘要

### 生成 `handler.c` 时

优先召回：

* 源协议 handler 代码块
* 目标协议文档中的流程说明块
* 命令处理分支示例
* 遥测处理函数示例
* 配置映射相关块

---

## 6.3 建议的 query 模板

### config 生成 query

```text
目标协议配置字段定义、参数映射规则、命令字、遥测字段、配置文件结构
```

### handler 生成 query

```text
目标协议 handler 处理流程、命令分发逻辑、遥测解析逻辑、内部通信逻辑、函数组织方式
```

---

## 6.4 第一阶段先不做的检索增强

你说现在聚焦跑通，所以这些先不要上：

* rerank
* HyDE
* query rewrite
* context compression
* adaptive RAG

后面有需要再加。虽然智谱知识库检索已经支持其中一部分能力，但第一阶段先不要引入过多变量。([BigModel Documentation][4])

---

# 七、如何调用 BigModel LLM 生成 `config.json`

## 7.1 生成目标

输入：

* 目标协议文档解析结果
* 检索到的源协议知识块
* 预定义输出 schema

输出：

* `dllg_config.json`

---

## 7.2 推荐模型

第一阶段建议：

* 默认：`glm-5.1`
* 追求成本/速度时：`glm-5-turbo`

因为官方对话补全文档把 `glm-5.1` 和 `glm-5-turbo` 列为当前旗舰系列。([BigModel Documentation][5])

---

## 7.3 Prompt 设计原则

系统提示要明确三件事：

1. 你是协议配置生成器
2. 必须严格按 schema 输出
3. 只能基于给定上下文生成，缺失字段要显式标注

### 建议 Prompt 骨架

```text
系统角色：
你是一个协议配置生成助手，负责根据目标协议文档和参考协议知识，生成目标协议的 config.json。

任务要求：
1. 严格输出 JSON，不要附加解释。
2. 字段名称必须符合给定 schema。
3. 只能依据提供的上下文生成。
4. 无法确定的值使用 null 或 "TODO"。
5. 不要臆造不存在的命令字、字段名或处理逻辑。

输入：
- 目标协议摘要
- 检索上下文
- 输出 schema
```

---

## 7.4 调用方式

官方同步接口是：

* `POST /paas/v4/chat/completions` ([BigModel Documentation][5])

Python SDK 示例风格也是 `client.chat.completions.create(...)`。([BigModel Documentation][1])

示意代码：

```python
from zai import ZhipuAiClient
import os

client = ZhipuAiClient(api_key=os.getenv("ZAI_API_KEY"))

response = client.chat.completions.create(
    model="glm-5.1",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    temperature=0.1,
    stream=False,
)

json_text = response.choices[0].message.content
```

### 参数建议

* `temperature = 0.1`
* 非流式先跑通
* 后处理时校验 JSON 是否可解析

原因：配置生成是结构化任务，温度要低。

---

# 八、如何调用 BigModel LLM 生成 `handler.c`

## 8.1 生成目标

输入：

* 目标协议文档中与处理流程相关的结构化摘要
* 检索到的源协议 handler 代码片段
* 你预定义的代码模板/接口规范

输出：

* `dllg_handler.c`

---

## 8.2 推荐做法：分两步生成

不要一步让模型直接吐完整 `handler.c`。
建议拆成：

### 第一步：生成 handler 设计草图

让模型先输出：

* 需要哪些函数
* 每个函数职责
* 命令分发逻辑
* 数据结构依赖
* 哪些信息不足

### 第二步：再生成完整 C 文件

把第一步设计草图 + 检索上下文 + 模板约束一起喂给模型，生成最终代码。

这样更稳，也更方便 Cursor 后面分阶段实现。

---

## 8.3 Prompt 约束

系统提示应明确：

* 输出必须是合法 C 代码
* 不要生成伪代码
* 不要补充解释文字
* 优先复用源协议 handler 的组织风格
* 遇到信息缺失时用 `TODO` 注释标识

建议骨架：

```text
你是嵌入式协议处理代码生成助手。

请根据：
1. 目标协议说明
2. 参考协议 handler 实现片段
3. 函数接口约束

生成一个可编译风格的 C 源文件。

要求：
- 只输出 C 代码
- 保留必要注释
- 不要输出 Markdown 代码围栏
- 未确定的实现处使用 TODO 注释
- 结构要清晰：include、宏、静态函数、主处理入口
```

---

# 九、建议的命令行流程

## 9.1 构建知识库

```bash
herta buildkb --source gdwx --chunk-strategy simple
```

内部做的事：

1. 解析文档和代码
2. 切块
3. 调 BigModel embeddings
4. 建 FAISS
5. 输出知识库

---

## 9.2 生成配置

```bash
herta generate config --target dllg
```

内部做的事：

1. 解析 `dllg.doc`
2. 抽取配置相关 query
3. 检索知识库
4. 调 BigModel chat completions
5. 输出 `output/generated/dllg/dllg_config.json`

---

## 9.3 生成 handler

```bash
herta generate handler --target dllg
```

内部做的事：

1. 解析 `dllg.doc`
2. 抽取 handler 相关 query
3. 检索知识库
4. 先生成设计草图
5. 再生成 `dllg_handler.c`

---

# 十、第一阶段最推荐的技术选型

## 10.1 模型选型

### 生成模型

* 默认：`glm-5.1`
* 备选：`glm-5-turbo` ([BigModel Documentation][5])

### embedding 模型

* 默认：`embedding-3`
* 维度：`1024` ([BigModel Documentation][2])

---

## 10.2 本地组件

* 向量库：FAISS
* 文档解析：

  * docx/pdf 预留智谱文件解析服务适配器
  * json/c 本地直接读取
* 语言：Python
* LLM SDK：`zai-sdk` ([BigModel Documentation][1])

---

# 十一、第一阶段你最应该避免的坑

## 11.1 不要把“知识库构建”和“代码生成”绑死在一个大函数里

要拆成清晰模块：

* parser
* chunker
* embedder
* vector store
* retriever
* generator

## 11.2 不要一开始就接入太多 RAG 高级能力

先别上：

* 重排序
* 自反思
* CRAG
* 图 RAG
* 多模态 RAG

## 11.3 不要一步生成完整 handler.c

最好“两阶段生成”。

## 11.4 不要把 BigModel 托管知识库作为第一实现

第一阶段自己掌握 chunk 和检索最重要。

---

# 十二、最小可行实现顺序

建议你后面让 Cursor 按这个顺序写：

### 第 1 阶段：基础通路

* 接入 `zai-sdk`
* 跑通 chat completions
* 跑通 embeddings
* 本地保存 FAISS

### 第 2 阶段：buildkb

* 文档解析
* 简单分块
* 向量化
* 建知识库

### 第 3 阶段：generate config

* 解析目标协议文档
* 检索上下文
* 生成 `config.json`

### 第 4 阶段：generate handler

* 检索 handler 相关上下文
* 两阶段生成 `handler.c`

### 第 5 阶段：再加高级 chunking

* semantic
* auto-size
* proposition

---

# 十三、结论

一句话总结：

> **用智谱官方 SDK / API 提供 embeddings 和对话生成能力；文档解析可接智谱文件解析服务；切块、向量库存储、检索编排和代码生成流程由 Herta 自己控制。**

它既能用上 BigModel API，又不会把系统控制权交出去。([BigModel Documentation][1])

**“让 Cursor 分阶段生成代码”的提示词方案**。

[1]: https://docs.bigmodel.cn/cn/guide/develop/python/introduction "官方 Python SDK - 智谱AI开放文档"
[2]: https://docs.bigmodel.cn/api-reference/%E6%A8%A1%E5%9E%8B-api/%E6%96%87%E6%9C%AC%E5%B5%8C%E5%85%A5 "文本嵌入 - 智谱AI开放文档"
[3]: https://docs.bigmodel.cn/cn/guide/tools/file-parser "新文件解析服务 - 智谱AI开放文档"
[4]: https://docs.bigmodel.cn/api-reference/%E7%9F%A5%E8%AF%86%E5%BA%93-api/%E5%85%A8%E6%A8%A1%E6%80%81%E7%9F%A5%E8%AF%86%E5%BA%93%E6%A3%80%E7%B4%A2?utm_source=chatgpt.com "全模态知识库检索 - 智谱AI开放文档"
[5]: https://docs.bigmodel.cn/api-reference/%E6%A8%A1%E5%9E%8B-api/%E5%AF%B9%E8%AF%9D%E8%A1%A5%E5%85%A8?utm_source=chatgpt.com "对话补全 - 智谱AI开放文档"
[6]: https://docs.bigmodel.cn/api-reference/%E7%9F%A5%E8%AF%86%E5%BA%93-api/%E5%88%9B%E5%BB%BA%E7%9F%A5%E8%AF%86%E5%BA%93?utm_source=chatgpt.com "创建知识库 - 智谱AI开放文档"
[7]: https://docs.bigmodel.cn/cn/guide/tools/knowledge/guide?utm_source=chatgpt.com "知识库帮助手册 - 智谱AI开放文档"
