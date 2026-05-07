# Herta：基于RAG的协议迁移代码生成与相似度评测系统

## 技术进展报告

---

## 1. 项目概述

Herta是一个面向嵌入式协议开发的智能代码生成系统，核心任务为从源协议（gdwx）的文档与代码库自动生成目标协议（dllg）的配置文件与处理代码，并通过自动化评测量化生成质量。

系统目标为降低协议迁移开发中的人工编码成本，解决跨协议语义映射与代码结构复用的自动化问题。

当前系统已构建完整的RAG pipeline，支持从知识库构建、检索增强生成到相似度评测的全流程实验。

---

## 2. 系统工作流程

### 2.1 知识库构建阶段（Ingestion）

输入源协议文档（gdwx.docx）与代码（C/JSON），经解析后采用四种分块策略（simple/semantic/auto-size/proposition）切分文本。

通过智谱AI embedding-3模型生成1024维向量，构建FAISS索引；同时建立BM25稀疏索引用于关键词检索。

输出为持久化的知识库，包含向量索引、稀疏索引、chunk元数据与构建报告。

### 2.2 生成阶段（Generation）

目标协议文档（dllg.doc）经结构化解析后，触发7阶段Pipeline：Query Rewrite → Fusion Retrieval → Rerank → Context Compression → Structured Context → Prompt Building → LLM Generation。

config.json采用单阶段生成；handler.c采用三阶段生成（Plan → Code → Verification），通过函数清单强制约束生成完整性。

### 2.3 评测阶段（Compare）

对生成的dllg_config.json与dllg_handler.c，分别与真实代码进行结构对比。

Config对比涵盖拓扑结构、命令表、遥测表、内部处理表四个维度；Handler对比采用AST级函数匹配，综合树编辑距离与语义特征计算相似度。

---

## 3. 关键技术与实现细节

### 3.1 RAG（Retrieval-Augmented Generation）

RAG架构通过外部知识检索增强LLM生成能力，解决大模型知识截止与领域特异性不足的问题。

系统实现模块化Pipeline，将检索与生成解耦，支持各阶段独立开关与参数调优。

### 3.2 向量检索（Vector Retrieval）与FAISS

基于智谱AI embedding-3模型将文本编码为稠密向量，通过余弦相似度度量语义相关性。

FAISS（Facebook AI Similarity Search）提供高效的近似最近邻搜索，支持大规模向量索引的毫秒级检索。

### 3.3 语义分块（Semantic Chunking）

按句子切分文档后，计算相邻句子的embedding相似度，在语义转折点（相似度低于阈值）处分割。

相比固定长度分块，保持块内主题一致性，减少跨边界语义断裂，提升检索精度。

### 3.4 命题分块（Proposition Chunking）

使用LLM将文档拆解为原子化的事实命题，每个命题作为独立chunk。

适用于协议字段定义等知识密集型场景，实现精确到事实级别的检索与可追溯性。

### 3.5 两阶段代码生成（Plan → Code）

阶段A生成设计草图，明确函数列表、命令分发逻辑与待确认点；阶段B基于草图生成完整代码。

新增阶段C执行后验证，比对生成代码与函数清单，补充缺失函数。

### 3.6 AST（Abstract Syntax Tree）

使用tree-sitter解析C代码，提取函数定义、调用关系、控制流结构等语法信息。

AST将代码表示为树形结构，捕获代码的语法层次与嵌套关系，为结构相似度计算提供基础。

### 3.7 Tree Edit Distance（APTED算法）

APTED（Adaptive Perimeter Tree Edit Distance）计算两棵AST之间的最小编辑操作数（插入、删除、替换节点）。

归一化后得到结构相似度，反映代码在语法层面的相似程度，权重占AST相似度的70%。

### 3.8 匈牙利算法（Hungarian Algorithm）

用于求解生成函数与真实函数之间的最优一对一匹配，使整体相似度最大化。

算法将函数匹配建模为二分图最大权匹配问题，避免一个生成函数被多个真实函数重复匹配。

### 3.9 Jaccard Similarity

计算两个集合的交集与并集之比，用于语义特征相似度评估。

系统提取函数体内的调用集合、字面量集合、赋值模式等6类语义特征，通过Jaccard度量功能相似性，权重占AST相似度的30%。

---

## 4. 当前结果与表现

### 4.1 配置文件生成（dllg_config.json）

拓扑结构相似度较高（约85%），JSON四层树结构完整，字段存在性基本正确。

字段语义匹配度不足（约60%），desc字段存在语义偏差，handler命名存在不一致，字段值存在虚构现象。

整体config_similarity约60-70分区间，处于"基本可用但需人工校验"水平。

### 4.2 Handler代码生成（dllg_handler.c）

函数覆盖率显著不足（约40-50%），大量目标协议命令对应的处理函数缺失。

少量生成函数匹配成功（相似度>0.3），同名函数AST结构相似度可达0.7-0.8。

整体handler_similarity约30-50分区间，处于"需要较多修改"水平。

### 4.3 RAG检索质量

向量检索可召回语义相关chunk，但对代码结构（函数名、命令字）的精确匹配能力弱。

BM25检索有效补充关键词匹配，但融合权重（α=0.6）可能过度偏向语义，需针对代码场景调优。

检索结果存在噪声，无关代码片段干扰生成质量。

---

## 5. 问题分析

### 5.1 检索问题（Retrieval Failure）

向量检索基于语义相似度，无法精确命中包含特定函数名或命令字的代码结构。

代码标识符（如CMD_QUERY_STATUS）在embedding空间中分散，相似度计算难以区分功能相同但命名不同的代码块。

检索失败直接导致生成阶段缺乏必要的参考上下文，LLM被迫依赖参数化知识进行推测。

### 5.2 上下文问题（Context Noise）

检索返回的Top-K chunk未经筛选与压缩，包含大量与当前生成任务无关的代码片段。

无关上下文占用Prompt长度配额，稀释有效信息密度，干扰LLM注意力分配。

当前Context Compression已实现，但压缩阈值（relevance_threshold=6.0）可能过于宽松，未能有效过滤噪声。

### 5.3 生成约束问题（Generation Constraint）

LLM缺乏显式结构约束，生成过程为开放式文本生成，无法保证函数集合的完整性。

即使注入函数清单，LLM仍可能因上下文长度限制或注意力分散而遗漏部分函数。

后验证机制（Verification）已补充缺失函数，但补充生成质量依赖于二次检索，可能引入新的不一致性。

### 5.4 Schema对齐问题（Config Mismatch）

源协议与目标协议的字段命名、数据类型、枚举值存在差异，LLM缺乏显式的schema映射机制。

生成过程中LLM可能基于训练数据中的类似协议进行"幻觉"填充，导致字段值与目标协议文档不符。

配置生成的schema约束弱于代码生成（无强制字段清单机制），虚构字段风险更高。

---

## 6. 改进方向

### 6.1 Query Rewrite（查询重写）

**待解决问题**：目标协议文档提取的查询为自然语言描述，与代码库中的技术术语存在语义鸿沟。

**改进措施**：实现代码语义化改写模块，将"状态查询命令处理"转换为"CMD_QUERY_STATUS handler function"；引入领域术语词典，建立自然语言到代码标识符的映射；针对config与handler任务采用不同改写策略（structured vs code_semantic）。

### 6.2 Rerank（重排序）

**待解决问题**：向量检索与BM25检索的初排结果质量参差，Top-K中常混入低相关度chunk。

**改进措施**：增强LLM精排器的评分prompt，引入细粒度评分维度（功能相关性、结构可参考性、字段映射清晰度）；实现动态阈值机制，根据查询类型调整接受分数；引入交叉编码器（Cross-Encoder）替代LLM评分，提升精排效率与一致性。

### 6.3 Fusion Retrieval（融合检索）

**待解决问题**：当前固定权重α=0.6可能不适合所有查询类型，代码检索需要更高的关键词匹配权重。

**改进措施**：实现自适应权重调整，根据查询特征（是否包含代码标识符、是否包含命令字）动态调整α；引入Reciprocal Rank Fusion（RRF）替代线性加权，避免分数尺度不一致问题；针对函数名检索增加BM25加权（重要标识符重复索引以提升权重）。

### 6.4 Context Compression（上下文压缩）

**待解决问题**：压缩模块虽已实现，但压缩策略过于保守，未能有效剔除冗余信息。

**改进措施**：引入task-aware压缩策略，config生成任务侧重字段定义，handler生成任务侧重函数实现；实现结构感知压缩，保留函数边界、缩进层次等代码结构信息；增加压缩质量反馈循环，根据生成结果评估压缩效果并调整阈值。

### 6.5 Structured Generation（函数列表约束生成）

**待解决问题**：LLM生成缺乏结构约束，函数覆盖率低且存在遗漏。

**改进措施**：强化Function Registry构建，从目标协议文档提取完整的命令-函数映射关系；引入Function-level Chain-of-Thought，要求LLM先输出函数清单确认，再逐函数生成实现；探索Constrained Decoding技术，通过logits masking强制生成特定函数签名。

---

## 7. 项目完成度评估

| 维度 | 评估 | 说明 |
|------|------|------|
| 架构完成度 | 高 | 五层架构（CLI/解析/知识库/生成/评测）已实现，模块边界清晰，Pipeline模式与传统模式双轨运行 |
| 功能完成度 | 中高 | 核心功能（buildkb/generate/compare）已可用，runall/inspect预留待实现，Pipeline 7阶段全部落地 |
| 生成质量 | 中等偏低 | config.json基本可用（60-70分），handler.c覆盖率低（30-50分），需持续优化检索与生成策略 |
| 可扩展性 | 高 | 模块化设计支持新增协议对、新增分块策略、新增检索算法，YAML配置驱动便于实验调参 |

---

## 8. 相关论文参考

### 8.1 Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks

**核心思想**：提出RAG框架，将预训练语言模型与非参数化记忆（检索索引）结合，解决知识密集型任务中的事实准确性问题。

**与本项目关系**：本系统的RAG Pipeline架构直接继承该论文思想，通过检索源协议知识库增强LLM的协议理解能力，降低生成幻觉。

### 8.2 Self-Consistency Improves Chain of Thought Reasoning in Language Models

**核心思想**：通过多路径采样与多数投票机制，提升大模型在复杂推理任务中的答案一致性与准确性。

**与本项目关系**：Handler代码生成的Plan → Code → Verification三阶段流程借鉴该思想，通过结构化中间表示（设计草图）约束生成一致性，可进一步引入多采样投票机制优化Plan质量。

### 8.3 CodeBERT: A Pre-Trained Model for Programming and Natural Languages

**核心思想**：基于Transformer架构预训练编程语言与自然语言的联合表示，学习代码的语义结构与文档关系。

**与本项目关系**：当前系统使用通用embedding模型（embedding-3），代码检索精度受限；未来可探索CodeBERT或CodeT5等代码专用预训练模型，提升代码语义理解与检索质量。

### 8.4 Graph-based Hierarchical Code Matching

**核心思想**：将代码表示为图结构（控制流图、数据流图），通过图匹配算法计算代码相似度，捕获代码的深层语义关系。

**与本项目关系**：当前AST相似度仅基于语法树结构，未考虑数据依赖与控制依赖；未来可扩展为图级匹配，提升跨协议代码迁移场景下的相似度计算精度。

### 8.5 Dense Passage Retrieval for Open-Domain Question Answering

**核心思想**：使用双编码器架构独立编码查询与文档，通过向量内积高效计算相关性，替代传统的BM25稀疏检索。

**与本项目关系**：本系统的向量检索模块基于相同原理，但采用稠密向量与稀疏检索融合策略；论文中的负采样训练与困难样本挖掘方法可用于优化领域特定的embedding质量。

---

*报告生成时间：2026年4月28日*

*项目负责人：Herta研发团队*
