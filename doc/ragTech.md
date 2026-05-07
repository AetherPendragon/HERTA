# RAG (检索增强生成) 完整教程

## 目录
1. [什么是RAG？](#什么是rag)
2. [RAG基本流程](#rag基本流程)
3. [基础RAG代码实现](#基础rag代码实现)
4. [22种RAG方法对比分析](#22种rag方法对比分析)
   - 分块策略 (4种)
   - 检索优化 (6种)
   - 生成优化 (4种)
   - 高级RAG架构 (8种)
5. [如何选择合适的RAG方法](#如何选择合适的rag方法)
6. [总结与学习路径](#总结与学习路径)

---

## 什么是RAG？

**RAG (Retrieval-Augmented Generation，检索增强生成)** 是一种将信息检索技术与大型语言模型(LLM)相结合的AI架构。

### 为什么需要RAG？

大型语言模型虽然强大，但存在以下问题：
- **知识截止**：模型训练后无法获取最新信息
- **幻觉问题**：可能生成看似合理但实际错误的内容
- **领域知识不足**：对特定专业领域理解有限
- **不可追溯**：无法说明答案来源

### RAG如何解决这些问题？

```
┌─────────────────────────────────────────────────────────────┐
│                       RAG 架构图                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌──────────────┐      ┌──────────────┐      ┌──────────┐ │
│   │   用户查询    │─────▶│   信息检索     │─────▶│  相关文档  │ │
│   │   (Query)    │      │  (Retriever)  │      │(Context) │ │
│   └──────────────┘      └──────────────┘      └────┬─────┘ │
│          │                                         │       │
│          │         ┌───────────────────────────────┘       │
│          │         ▼                                      │
│          │    ┌──────────────┐                          │
│          └───▶│   提示词组装   │                          │
│               │(Prompt Build)│                          │
│               └──────┬───────┘                          │
│                      │                                   │
│                      ▼                                   │
│               ┌──────────────┐                          │
│               │   大语言模型   │                          │
│               │     (LLM)     │                          │
│               └──────┬───────┘                          │
│                      │                                   │
│                      ▼                                   │
│               ┌──────────────┐                          │
│               │    最终答案   │                          │
│               │   (Answer)   │                          │
│               └──────────────┘                          │
│                                                          │
└─────────────────────────────────────────────────────────────┘
```

**核心思想**：在回答问题前，先从知识库中检索相关信息，将检索到的内容作为上下文提供给大模型，让模型基于这些事实生成答案。

---

## RAG基本流程

一个标准的RAG系统包含以下步骤：

### 步骤1：数据摄取 (Ingestion) 准备阶段
```
原始文档 → 文档加载 → 文本提取 → 文档预处理
```

### 步骤2：文档分块 (Chunking) 准备阶段
```
长文档 → 切分成小块 → 保持语义完整
```

### 步骤3：向量化 (Embedding) 准备阶段
```
文本块 → 嵌入模型 → 向量表示
```

### 步骤4：向量存储 (Storage) 准备阶段
```
向量 + 原文 → 向量数据库 (如FAISS)
```


### 步骤5：检索 (Retrieval) 回答阶段
```
用户查询 → 向量化 → 相似度搜索 → 返回Top-K相关块
```

### 步骤6：生成 (Generation) 回答阶段
```
查询 + 检索结果 → 组装Prompt → LLM生成答案
```

---

## 基础RAG代码实现

下面是本项目中最基础的RAG实现（来自 `1_simple_rag.ipynb`）：

### 完整代码

```python
import numpy as np
import fitz  # PyMuPDF
import openai
from sklearn.metrics.pairwise import cosine_similarity

# ==========================================
# 步骤1: 设置API客户端
# ==========================================
client = openai.OpenAI(
    base_url="https://api.studio.nebius.ai/v1/",
    api_key="YOUR_API_KEY"
)

# ==========================================
# 步骤2: 定义嵌入函数
# ==========================================
def get_embedding(text, model="BAAI/bge-en-icl"):
    """将文本转换为向量嵌入"""
    text = text.replace("\n", " ")
    response = client.embeddings.create(
        input=[text],
        model=model
    )
    return response.data[0].embedding

# ==========================================
# 步骤3: 文档处理 - 从PDF提取文本
# ==========================================
def extract_text_from_pdf(pdf_path):
    """从PDF文件提取文本"""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# ==========================================
# 步骤4: 文档分块
# ==========================================
def split_text(text, chunk_size=1000, chunk_overlap=200):
    """将长文本切分成重叠的小块"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - chunk_overlap  # 重叠部分保证上下文连贯
    return chunks

# ==========================================
# 步骤5: 构建向量索引
# ==========================================
class VectorStore:
    def __init__(self):
        self.vectors = []  # 存储向量
        self.texts = []    # 存储原文
    
    def add_documents(self, chunks):
        """添加文档到向量库"""
        for chunk in chunks:
            embedding = get_embedding(chunk)
            self.vectors.append(embedding)
            self.texts.append(chunk)
    
    def search(self, query, top_k=3):
        """检索与查询最相似的文档"""
        query_vector = get_embedding(query)
        similarities = cosine_similarity([query_vector], self.vectors)[0]
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        return [(self.texts[i], similarities[i]) for i in top_indices]

# ==========================================
# 步骤6: RAG主流程
# ==========================================
def rag_query(query, vector_store, model="meta-llama/Meta-Llama-3.1-70B-Instruct"):
    """执行RAG查询"""
    # 6.1 检索相关文档
    relevant_docs = vector_store.search(query, top_k=3)
    context = "\n\n".join([doc for doc, _ in relevant_docs])
    
    # 6.2 组装Prompt
    prompt = f"""基于以下上下文回答问题。如果上下文中没有相关信息，请说"我不知道"。

上下文:
{context}

问题: {query}

答案:"""
    
    # 6.3 调用LLM生成答案
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个有帮助的助手。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    
    return response.choices[0].message.content

# ==========================================
# 完整使用示例
# ==========================================
if __name__ == "__main__":
    # 1. 加载文档
    pdf_text = extract_text_from_pdf("data/AI_Information.pdf")
    
    # 2. 分块
    chunks = split_text(pdf_text, chunk_size=1000, chunk_overlap=200)
    print(f"文档被分割为 {len(chunks)} 个块")
    
    # 3. 构建向量库
    store = VectorStore()
    store.add_documents(chunks)
    print("向量库构建完成")
    
    # 4. 查询
    question = "什么是人工智能？"
    answer = rag_query(question, store)
    print(f"问题: {question}")
    print(f"答案: {answer}")
```

### 代码核心要点解析

| 组件 | 作用 | 关键参数 |
|------|------|----------|
| `chunk_size=1000` | 每个文本块的最大长度 | 太小→上下文断裂；太大→检索不精准 |
| `chunk_overlap=200` | 相邻块的重叠字符数 | 保证跨块语义连贯 |
| `top_k=3` | 检索返回的文档数 | 太少→信息不足；太多→引入噪声 |
| `temperature=0.3` | 生成随机性 | 事实问答用低温度，创意生成用高温度 |

---

## 22种RAG方法对比分析

本项目实现了22种RAG变体，按优化目标可分为4大类：

```
┌────────────────────────────────────────────────────────────────┐
│                      22种RAG方法分类                            │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │   1. 分块策略     │  │  2. 检索优化     │                     │
│  │  (4种方法)       │  │  (6种方法)       │                     │
│  ├──────────────────┤  ├──────────────────┤                     │
│  │ • 简单分块       │  │ • 查询转换       │                     │
│  │ • 语义分块       │  │ • 重排序        │                     │
│  │ • 分块大小选择   │  │ • 上下文压缩     │                     │
│  │ • 命题分块       │  │ • 融合检索       │                     │
│  │                  │  │ • 上下文增强     │                     │
│  │                  │  │ • 相关片段提取   │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │   3. 生成优化     │  │  4. 高级架构     │                     │
│  │  (4种方法)       │  │  (8种方法)       │                     │
│  ├──────────────────┤  ├──────────────────┤                     │
│  │ • 上下文块标题   │  │ • 自适应RAG      │                     │
│  │ • 文档增强       │  │ • 自反思RAG      │                     │
│  │ • 多模态RAG      │  │ • 纠正性RAG      │                     │
│  │ • 强化学习RAG    │  │ • 分层RAG        │                     │
│  │                  │  │ • 图RAG          │                     │
│  │                  │  │ • HyDE          │                     │
│  │                  │  │ • 反馈循环RAG    │                     │
│  │                  │  │ • 大数据知识图谱 │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## 第一类：分块策略优化 (Chunking Strategies)

### 1. 简单分块 (Simple Chunking)
**文件**: `1_simple_rag.ipynb`

```python
def split_text(text, chunk_size=1000, chunk_overlap=200):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - chunk_overlap
    return chunks
```

**特点**：固定长度分块，实现简单，速度快
**缺点**：可能切断语义连贯的段落

---

### 2. 语义分块 (Semantic Chunking)
**文件**: `2_semantic_chunking.ipynb`

```python
def semantic_chunking(text, percentile=90):
    # 1. 先按句子分割
    sentences = split_into_sentences(text)
    
    # 2. 计算相邻句子的相似度
    similarities = []
    for i in range(len(sentences)-1):
        emb1 = get_embedding(sentences[i])
        emb2 = get_embedding(sentences[i+1])
        sim = cosine_similarity([emb1], [emb2])[0][0]
        similarities.append(sim)
    
    # 3. 在相似度低于阈值的边界处分割
    threshold = np.percentile(similarities, percentile)
    chunks = []
    current_chunk = [sentences[0]]
    
    for i, sim in enumerate(similarities):
        if sim < threshold:
            # 语义边界，保存当前块
            chunks.append(" ".join(current_chunk))
            current_chunk = []
        current_chunk.append(sentences[i+1])
    
    return chunks
```

**核心思想**：根据语义相似度而非固定长度分块，在语义转折点分割
**优点**：保持语义连贯性，块内主题一致
**适用场景**：结构化文档、论文、报告

---

### 3. 分块大小选择器 (Chunk Size Selector)
**文件**: `3_chunk_size_selector.ipynb`

```python
def evaluate_chunk_sizes(document, questions, chunk_sizes=[500, 1000, 2000], 
                         overlaps=[100, 200, 400]):
    """评估不同分块配置的效果"""
    results = []
    
    for size in chunk_sizes:
        for overlap in overlaps:
            # 构建索引
            chunks = split_text(document, size, overlap)
            store = VectorStore()
            store.add_documents(chunks)
            
            # 评估
            scores = []
            for q in questions:
                answer = rag_query(q, store)
                score = evaluate_answer_quality(q, answer)
                scores.append(score)
            
            results.append({
                'chunk_size': size,
                'overlap': overlap,
                'avg_score': np.mean(scores)
            })
    
    return max(results, key=lambda x: x['avg_score'])
```

**核心思想**：通过实际评估找到最优分块参数
**优点**：数据驱动的参数选择，适配特定领域
**评估指标**：答案忠实度、相关性、语义相似度

---

### 14. 命题分块 (Proposition Chunking)
**文件**: `14_proposition_chunking.ipynb`

```python
def proposition_chunking(document):
    """将文档分解为原子化的事实命题"""
    
    prompt = f"""将以下文本分解为简单的事实命题。
每个命题应该是一个完整、自包含的事实陈述。

文本: {document}

输出格式:
1. [事实命题1]
2. [事实命题2]
..."""
    
    response = client.chat.completions.create(
        model="meta-llama/Meta-Llama-3.1-70B-Instruct",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # 解析命题列表
    propositions = parse_propositions(response.choices[0].message.content)
    return propositions
```

**核心思想**：用LLM将文档分解为最小事实单元（原子命题）
**优点**：
- 检索精度极高（精确到事实级别）
- 消除冗余信息
- 便于验证答案来源

**适用场景**：需要精确事实检索的法律、医学、科学文献

---

## 第二类：检索优化 (Retrieval Optimization)

### 7. 查询转换 (Query Transform)
**文件**: `7_query_transform.ipynb`

包含三种技术：

#### A. 查询重写 (Query Rewriting)
```python
def rewrite_query(original_query):
    """将模糊查询改写为更清晰的形式"""
    prompt = f"""将以下查询改写得更具体、更清晰，以便搜索。
原始查询: {original_query}
改写后的查询:"""
    
    response = client.chat.completions.create(...)
    return response.choices[0].message.content
```

#### B. Step-back 提示
```python
def step_back_query(original_query):
    """生成更宽泛的step-back查询"""
    prompt = f"""针对以下具体问题，生成一个更宽泛的背景查询，
帮助获取更多相关上下文。
具体查询: {original_query}
Step-back查询:"""
    
    # 同时检索具体和宽泛查询的结果
    specific_results = search(original_query)
    stepback_results = search(step_back_query)
    return combine_results(specific_results, stepback_results)
```

#### C. 子查询分解
```python
def decompose_query(complex_query):
    """将复杂查询分解为子查询"""
    prompt = f"""将以下复杂问题分解为多个简单的子问题。
复杂问题: {complex_query}

子问题:
1. 
2. 
3. """
    
    sub_queries = parse_subqueries(response)
    all_results = []
    for sq in sub_queries:
        all_results.extend(search(sq))
    return merge_and_deduplicate(all_results)
```

**核心思想**：优化查询本身，使其更适合检索
**适用场景**：用户查询模糊、复杂或多跳推理问题

---

### 8. 重排序 (Reranking)
**文件**: `8_reranker.ipynb`

```python
def retrieve_with_rerank(query, vector_store, initial_k=20, final_k=5):
    """两阶段检索：召回 + 精排"""
    
    # 阶段1: 向量检索（高召回）
    candidates = vector_store.search(query, top_k=initial_k)
    
    # 阶段2: 重排序（高精度）
    reranked = []
    for doc, _ in candidates:
        # 使用更强的模型计算相关性分数
        prompt = f"""评估以下文档与查询的相关性(0-10分)。
查询: {query}
文档: {doc}

相关性分数(只输出数字):"""
        
        response = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        score = float(response.choices[0].message.content.strip())
        reranked.append((doc, score))
    
    # 按重排序分数排序
    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked[:final_k]
```

**核心思想**：先用轻量级模型快速召回，再用强模型精准排序
**优点**：平衡效率与精度
**适用场景**：大规模文档库，需要高质量检索结果

---

### 10. 上下文压缩 (Contextual Compression)
**文件**: `10_contextual_compression.ipynb`

```python
def compress_context(query, retrieved_docs):
    """压缩检索结果，只保留相关部分"""
    compressed = []
    
    for doc in retrieved_docs:
        prompt = f"""从以下文档中提取与查询相关的部分，删除无关内容。
如果完全不相关，返回"不相关"。

查询: {query}
文档: {doc}

相关片段:"""
        
        response = client.chat.completions.create(...)
        relevant_part = response.choices[0].message.content
        
        if relevant_part != "不相关":
            compressed.append(relevant_part)
    
    return compressed
```

**核心思想**：过滤掉检索文档中的无关部分，减少噪声
**优点**：
- 降低token消耗
- 减少无关信息干扰
- 提升生成质量

---

### 16. 融合检索 (Fusion Retrieval)
**文件**: `16_fusion_rag.ipynb`

```python
from rank_bm25 import BM25Okapi

def fusion_retrieval(query, vector_store, documents, alpha=0.5, top_k=5):
    """融合向量搜索和BM25关键词搜索"""
    
    # 1. 向量搜索 (语义匹配)
    query_vector = get_embedding(query)
    vector_scores = cosine_similarity([query_vector], vector_store.vectors)[0]
    
    # 2. BM25搜索 (关键词匹配)
    tokenized_docs = [doc.split() for doc in documents]
    bm25 = BM25Okapi(tokenized_docs)
    tokenized_query = query.split()
    bm25_scores = bm25.get_scores(tokenized_query)
    
    # 3. 分数归一化
    vector_scores = (vector_scores - vector_scores.min()) / (vector_scores.max() - vector_scores.min())
    bm25_scores = (bm25_scores - bm25_scores.min()) / (bm25_scores.max() - bm25_scores.min())
    
    # 4. 加权融合
    final_scores = alpha * vector_scores + (1 - alpha) * bm25_scores
    
    # 5. 返回Top-K
    top_indices = np.argsort(final_scores)[-top_k:][::-1]
    return [(documents[i], final_scores[i]) for i in top_indices]
```

**核心思想**：结合向量搜索（语义匹配）和BM25（关键词匹配）
**优点**：
- 兼顾语义理解和精确匹配
- 对专业术语和实体名称效果更好

---

### 4. 上下文增强 (Context Enriched)
**文件**: `4_context_enriched_rag.ipynb`

```python
def retrieve_with_neighbors(vector_store, query, top_k=3, neighbor_range=1):
    """检索时同时获取相邻块，保持上下文连贯"""
    
    # 获取基础检索结果
    base_results = vector_store.search(query, top_k=top_k)
    
    enriched_results = []
    for doc_idx, (doc, score) in enumerate(base_results):
        # 获取前后相邻的块
        start_idx = max(0, doc_idx - neighbor_range)
        end_idx = min(len(vector_store.texts), doc_idx + neighbor_range + 1)
        
        # 合并相邻块
        context_chunks = vector_store.texts[start_idx:end_idx]
        enriched_doc = "\n".join(context_chunks)
        enriched_results.append((enriched_doc, score))
    
    return enriched_results
```

**核心思想**：检索到的块不是孤立的，同时获取相邻块保证上下文连贯
**适用场景**：叙事性文档、故事、连贯性强的文本

---

### 9. 相关片段提取 (RSE)
**文件**: `9_rse.ipynb`

```python
def relevant_segment_extraction(query, chunks, similarity_threshold=0.7):
    """识别并提取连续的相关文本段"""
    
    # 1. 计算每个块与查询的相似度
    similarities = []
    for chunk in chunks:
        chunk_emb = get_embedding(chunk)
        query_emb = get_embedding(query)
        sim = cosine_similarity([chunk_emb], [query_emb])[0][0]
        similarities.append(sim)
    
    # 2. 识别相关块聚类（连续的相似块）
    segments = []
    current_segment = []
    
    for i, sim in enumerate(similarities):
        if sim > similarity_threshold:
            current_segment.append(chunks[i])
        else:
            if current_segment:
                # 保存完整段落后重新开始
                segments.append(" ".join(current_segment))
                current_segment = []
    
    # 添加最后一个段落
    if current_segment:
        segments.append(" ".join(current_segment))
    
    return segments
```

**核心思想**：识别相关的连续块段落，而非独立块，重建原始文本流
**优点**：保持长文本的连贯性和结构

---

## 第三类：生成优化 (Generation Optimization)

### 5. 上下文块标题 (Contextual Chunk Headers, CCH)
**文件**: `5_contextual_chunk_headers_rag.ipynb`

```python
def add_contextual_headers(document, chunks):
    """为每个块添加上下文标题"""
    
    # 1. 提取文档整体结构
    doc_structure = analyze_document_structure(document)
    
    enriched_chunks = []
    for chunk in chunks:
        # 2. 确定块所属章节
        section = find_chunk_section(chunk, doc_structure)
        
        # 3. 添加上下文标题
        header = f"【文档: {doc_structure.title} | 章节: {section.title}】\n"
        enriched_chunk = header + chunk
        enriched_chunks.append(enriched_chunk)
    
    return enriched_chunks
```

**核心思想**：在分块前添加高级上下文（文档标题、章节信息）
**优点**：帮助模型理解文档的层级结构
**适用场景**：结构化文档（论文、报告、手册）

---

### 6. 文档增强 (Document Augmentation)
**文件**: `6_doc_augmentation_rag.ipynb`

```python
def augment_chunks_with_questions(chunks):
    """为每个块生成相关问题，用问题和块共同索引"""
    
    augmented_index = []
    
    for chunk in chunks:
        # 1. 为这个块生成可能的问题
        prompt = f"""基于以下内容，生成3个用户可能会问的问题。
内容: {chunk}

问题:
1."""
        
        response = client.chat.completions.create(...)
        questions = parse_questions(response)
        
        # 2. 将问题和原文都加入索引
        augmented_index.append({
            'text': chunk,
            'questions': questions,
            'embeddings': [
                get_embedding(chunk),
                *[get_embedding(q) for q in questions]
            ]
        })
    
    return augmented_index
```

**核心思想**：为每个块生成相关问题，索引时同时索引块和可能的问题
**优点**：弥合用户查询与文档语言风格的差异
**适用场景**：专业术语多的领域文档

---

### 15. 多模态RAG (Multimodal RAG)
**文件**: `15_multimodel_rag.ipynb`

```python
def process_multimodal_pdf(pdf_path):
    """处理包含文本和图像的PDF"""
    
    doc = fitz.open(pdf_path)
    multimodal_chunks = []
    
    for page_num, page in enumerate(doc):
        # 1. 提取文本
        text = page.get_text()
        
        # 2. 提取图像
        images = page.get_images()
        
        for img_index, img in enumerate(images):
            # 3. 为图像生成描述
            image_description = generate_image_caption(img)
            
            # 4. 组合文本和图像描述
            multimodal_chunk = {
                'page': page_num,
                'text': text,
                'images': [{
                    'index': img_index,
                    'description': image_description
                }],
                'combined_text': f"{text}\n\n[图片描述: {image_description}]"
            }
            multimodal_chunks.append(multimodal_chunk)
    
    return multimodal_chunks
```

**核心思想**：同时处理文本和图像，为图像生成描述后统一索引
**适用场景**：包含图表、图片的文档（年报、教材、说明书）

---

### 21. 强化学习RAG (RAG with RL)
**文件**: `21_rag_with_rl.ipynb`

```python
class RAGWithRL:
    def __init__(self, base_rag, reward_model):
        self.base_rag = base_rag
        self.reward_model = reward_model
        self.policy_network = PolicyNetwork()
    
    def generate_with_rl(self, query, num_samples=5):
        """使用强化学习优化生成"""
        
        candidates = []
        for _ in range(num_samples):
            # 采样生成
            context = self.base_rag.retrieve(query)
            answer = self.base_rag.generate(query, context, temperature=0.7)
            
            # 计算奖励
            reward = self.reward_model.score(query, context, answer)
            candidates.append((answer, reward))
        
        # 选择奖励最高的答案
        best_answer = max(candidates, key=lambda x: x[1])
        return best_answer
```

**核心思想**：用强化学习奖励机制训练生成策略，最大化答案质量
**适用场景**：对答案质量要求极高的场景

---

## 第四类：高级RAG架构 (Advanced Architectures)

### 12. 自适应RAG (Adaptive RAG)
**文件**: `12_adaptive_rag.ipynb`

```python
class AdaptiveRAG:
    def classify_query(self, query):
        """分类查询类型"""
        prompt = f"""分类以下查询的类型:
- factual: 事实查询（需要具体信息）
- analytical: 分析查询（需要推理）
- opinion: 观点查询（主观判断）
- contextual: 上下文查询（基于已有对话）

查询: {query}
类型:"""
        response = client.chat.completions.create(...)
        return response.choices[0].message.content.strip()
    
    def route_and_execute(self, query):
        """根据查询类型选择策略"""
        query_type = self.classify_query(query)
        
        strategies = {
            'factual': self.factual_strategy,      # 精确检索
            'analytical': self.analytical_strategy, # 多跳检索
            'opinion': self.opinion_strategy,       # 多角度检索
            'contextual': self.contextual_strategy  # 对话上下文
        }
        
        return strategies[query_type](query)
```

**核心思想**：根据查询类型动态选择最优检索策略
**查询类型**：
- 事实查询 → 精确检索少量文档
- 分析查询 → 多跳检索，获取推理链条
- 观点查询 → 多角度检索不同立场

---

### 13. 自反思RAG (Self-RAG)
**文件**: `13_self_rag.ipynb`

```python
class SelfRAG:
    def execute(self, query):
        """带有自我反思的RAG流程"""
        
        # 反思点1: 是否需要检索？
        need_retrieval = self.reflect_need_retrieval(query)
        if not need_retrieval:
            return self.direct_generate(query)
        
        # 执行检索
        retrieved_docs = self.retrieve(query)
        
        # 反思点2: 检索结果是否相关？
        relevant_docs = []
        for doc in retrieved_docs:
            is_relevant = self.reflect_relevance(query, doc)
            if is_relevant:
                relevant_docs.append(doc)
        
        if not relevant_docs:
            return "我需要更多信息才能回答这个问题。"
        
        # 生成答案
        answer = self.generate(query, relevant_docs)
        
        # 反思点3: 答案是否得到支持？
        is_supported = self.reflect_support(answer, relevant_docs)
        if not is_supported:
            answer = self.regenerate_with_constraints(query, relevant_docs)
        
        # 反思点4: 答案是否有用？
        usefulness = self.reflect_usefulness(query, answer)
        
        return answer
```

**核心思想**：在流程中设置多个反思点，动态决策
**反思点**：
1. 是否需要检索？
2. 检索结果是否相关？
3. 生成是否得到文档支持？
4. 答案是否有用？

---

### 20. 纠正性RAG (Corrective RAG, CRAG)
**文件**: `20_crag.ipynb`

```python
class CorrectiveRAG:
    def evaluate_and_correct(self, query, retrieved_docs):
        """评估检索质量并纠正"""
        
        # 1. 评估检索质量
        quality_score = self.evaluate_retrieval_quality(query, retrieved_docs)
        
        if quality_score < 0.3:
            # 质量差 → 使用网络搜索补充
            web_results = self.web_search(query)
            corrected_context = self.fuse_contexts(retrieved_docs, web_results)
            
        elif quality_score < 0.7:
            # 质量中等 → 优化现有上下文
            corrected_context = self.optimize_context(query, retrieved_docs)
            
        else:
            # 质量好 → 直接使用
            corrected_context = retrieved_docs
        
        return self.generate(query, corrected_context)
    
    def evaluate_retrieval_quality(self, query, docs):
        """评估检索质量分数"""
        prompt = f"""评估以下检索结果与查询的相关性(0-1分)。
查询: {query}
检索结果: {docs}

质量分数:"""
        response = client.chat.completions.create(...)
        return float(response.choices[0].message.content)
```

**核心思想**：动态评估检索质量，不足时自动纠正（如使用网络搜索）
**适用场景**：知识库不完整或需要最新信息的场景

---

### 18. 分层RAG (Hierarchy RAG)
**文件**: `18_hierarchy_rag.ipynb`

```python
class HierarchyRAG:
    def __init__(self, documents):
        # 第一层: 文档摘要
        self.summaries = self.generate_summaries(documents)
        self.summary_index = VectorStore()
        self.summary_index.add_documents(self.summaries)
        
        # 第二层: 详细内容
        self.detail_chunks = self.chunk_documents(documents)
        self.detail_index = VectorStore()
        self.detail_index.add_documents(self.detail_chunks)
    
    def retrieve(self, query):
        """两级检索"""
        # 第一层: 检索相关摘要，确定相关文档
        relevant_summaries = self.summary_index.search(query, top_k=2)
        relevant_doc_ids = [s.doc_id for s in relevant_summaries]
        
        # 第二层: 在相关文档中检索详细内容
        filtered_chunks = [c for c in self.detail_chunks 
                          if c.doc_id in relevant_doc_ids]
        
        temp_index = VectorStore()
        temp_index.add_documents(filtered_chunks)
        final_results = temp_index.search(query, top_k=5)
        
        return final_results
```

**核心思想**：两级搜索，先粗粒度定位相关文档，再细粒度检索
**优点**：提高大规模文档库的检索效率

---

### 17. 图RAG (Graph RAG)
**文件**: `17_graph_rag.ipynb`

```python
import networkx as nx

class GraphRAG:
    def build_knowledge_graph(self, documents):
        """构建知识图谱"""
        G = nx.Graph()
        
        # 1. 提取实体和关系
        for doc in documents:
            entities, relations = self.extract_entities_relations(doc)
            
            # 2. 添加节点和边
            for entity in entities:
                G.add_node(entity['name'], type=entity['type'])
            
            for rel in relations:
                G.add_edge(rel['source'], rel['target'], 
                          relation=rel['type'])
        
        return G
    
    def retrieve(self, query):
        """基于图的检索"""
        # 1. 提取查询中的实体
        query_entities = self.extract_entities(query)
        
        # 2. 从实体出发遍历图
        relevant_nodes = set()
        for entity in query_entities:
            if entity in self.graph:
                # 获取邻居节点
                neighbors = nx.single_source_shortest_path_length(
                    self.graph, entity, cutoff=2
                )
                relevant_nodes.update(neighbors.keys())
        
        # 3. 返回相关节点的内容
        return [self.node_to_document(n) for n in relevant_nodes]
```

**核心思想**：将知识组织为图结构，支持关系遍历和多跳推理
**适用场景**：需要关系推理的领域（医学知识、法律知识）

---

### 19. HyDE (假设文档嵌入)
**文件**: `19_HyDE_rag.ipynb`

```python
class HyDERAG:
    def retrieve(self, query):
        """使用假设文档进行检索"""
        
        # 1. 生成假设答案
        hypothetical_prompt = f"""基于你的知识，回答以下问题。
即使不确定，也给出最可能的答案。

问题: {query}

答案:"""
        
        hypothetical_answer = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-70B-Instruct",
            messages=[{"role": "user", "content": hypothetical_prompt}]
        ).choices[0].message.content
        
        # 2. 用假设答案嵌入检索
        hypothetical_embedding = get_embedding(hypothetical_answer)
        
        # 3. 在向量库中搜索相似文档
        results = self.vector_store.search_by_vector(hypothetical_embedding)
        
        return results
```

**核心思想**：将短查询扩展为假设答案文档，用答案的语义进行检索
**优点**：解决短查询语义稀疏的问题
**适用场景**：短查询、专业术语与文档表述差异大的情况

---

### 11. 反馈循环RAG (Feedback Loop RAG)
**文件**: `11_feedback_loop_rag.ipynb`

```python
class FeedbackLoopRAG:
    def __init__(self):
        self.query_history = []
        self.feedback_scores = {}
    
    def retrieve_with_feedback(self, query):
        """基于历史反馈优化检索"""
        
        # 1. 基础检索
        base_results = self.vector_store.search(query)
        
        # 2. 应用反馈调整
        adjusted_results = []
        for doc, base_score in base_results:
            # 获取该文档的历史反馈分数
            feedback_bonus = self.feedback_scores.get(doc.id, 0)
            
            # 调整分数
            adjusted_score = base_score + feedback_bonus
            adjusted_results.append((doc, adjusted_score))
        
        # 3. 重新排序
        adjusted_results.sort(key=lambda x: x[1], reverse=True)
        return adjusted_results
    
    def collect_feedback(self, query, results, user_rating):
        """收集用户反馈"""
        for doc in results:
            if doc.id not in self.feedback_scores:
                self.feedback_scores[doc.id] = 0
            self.feedback_scores[doc.id] += user_rating * 0.1
```

**核心思想**：收集用户反馈，动态调整文档相关性评分
**优点**：系统持续学习用户偏好
**适用场景**：长期运行的生产系统

---

### 22. 大数据知识图谱 (Big Data with KG)
**文件**: `22_Big_data_with_KG.ipynb`

```python
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS

class BigDataKnowledgeGraph:
    def __init__(self):
        self.graph = Graph()
        self.EX = Namespace("http://example.org/")
    
    def extract_to_rdf(self, text):
        """使用LLM提取RDF三元组"""
        
        prompt = f"""从以下新闻文本中提取知识图谱三元组(主语-谓语-宾语)。
格式: 主语 | 关系 | 宾语

文本: {text}

三元组:"""
        
        response = client.chat.completions.create(...)
        triples = parse_triples(response)
        
        # 添加到RDF图
        for subj, pred, obj in triples:
            s = URIRef(self.EX[subj.replace(" ", "_")])
            p = URIRef(self.EX[pred.replace(" ", "_")])
            o = URIRef(self.EX[obj.replace(" ", "_")]) if not obj.isdigit() else Literal(obj)
            
            self.graph.add((s, p, o))
    
    def query_kg(self, query):
        """使用SPARQL查询知识图谱"""
        
        # 1. 将自然语言转换为SPARQL
        sparql = self.nl_to_sparql(query)
        
        # 2. 执行查询
        results = self.graph.query(sparql)
        
        return results
```

**核心思想**：将非结构化文本转换为结构化知识图谱(RDF)，支持复杂推理查询
**适用场景**：大规模知识管理、需要复杂关系查询的场景

---

## 方法对比总结表

| 编号 | 方法 | 核心优化点 | 适用场景 | 实现复杂度 |
|------|------|-----------|---------|-----------|
| 1 | 简单RAG | 基础流程 | 入门学习 | ⭐ |
| 2 | 语义分块 | 分块质量 | 结构化文档 | ⭐⭐ |
| 3 | 分块大小选择 | 参数优化 | 领域适配 | ⭐⭐ |
| 4 | 上下文增强 | 连贯性 | 叙事文档 | ⭐ |
| 5 | 上下文块标题 | 结构理解 | 层级文档 | ⭐⭐ |
| 6 | 文档增强 | 检索匹配 | 专业领域 | ⭐⭐ |
| 7 | 查询转换 | 查询质量 | 复杂查询 | ⭐⭐ |
| 8 | 重排序 | 检索精度 | 大规模库 | ⭐⭐ |
| 9 | RSE | 连续片段 | 长文档 | ⭐⭐ |
| 10 | 上下文压缩 | 去噪 | 长检索结果 | ⭐⭐ |
| 11 | 反馈循环 | 持续优化 | 生产系统 | ⭐⭐⭐ |
| 12 | 自适应RAG | 动态策略 | 多样查询 | ⭐⭐⭐ |
| 13 | 自反思RAG | 质量控制 | 高可靠性 | ⭐⭐⭐⭐ |
| 14 | 命题分块 | 粒度精度 | 事实检索 | ⭐⭐ |
| 15 | 多模态RAG | 图像处理 | 富媒体文档 | ⭐⭐⭐ |
| 16 | 融合检索 | 多策略 | 混合需求 | ⭐⭐ |
| 17 | 图RAG | 关系推理 | 知识推理 | ⭐⭐⭐⭐ |
| 18 | 分层RAG | 检索效率 | 超大规模库 | ⭐⭐⭐ |
| 19 | HyDE | 短查询优化 | 查询-文档差异 | ⭐⭐ |
| 20 | CRAG | 质量纠正 | 不确定场景 | ⭐⭐⭐ |
| 21 | RL RAG | 生成优化 | 高质量要求 | ⭐⭐⭐⭐ |
| 22 | 知识图谱 | 结构化 | 复杂推理 | ⭐⭐⭐⭐ |

---

## 如何选择合适的RAG方法

### 决策流程图

```
                    ┌─────────────────┐
                    │   开始RAG选型    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ 文档是否结构化？  │
                    └────────┬────────┘
                         是 /   \ 否
                          /     \
                         ▼       ▼
              ┌─────────────┐   ┌─────────────┐
              │ 使用语义分块  │   │使用简单分块  │
              │ 或命题分块   │   │或上下文增强  │
              └──────┬──────┘   └──────┬──────┘
                     │                 │
                     └────────┬────────┘
                              ▼
                    ┌─────────────────┐
                    │ 查询是否复杂？   │
                    └────────┬────────┘
                         是 /   \ 否
                          /     \
                         ▼       ▼
              ┌─────────────┐   ┌─────────────┐
              │ 使用查询转换  │   │ 基础检索    │
              │ + 自反思RAG   │   │            │
              └──────┬──────┘   └──────┬──────┘
                     │                 │
                     └────────┬────────┘
                              ▼
                    ┌─────────────────┐
                    │ 需要高精度？   │
                    └────────┬────────┘
                         是 /   \ 否
                          /     \
                         ▼       ▼
              ┌─────────────┐   ┌─────────────┐
              │ 使用重排序   │   │ 保持基础    │
              │ + 上下文压缩 │   │            │
              └──────┬──────┘   └──────┬──────┘
                     │                 │
                     └────────┬────────┘
                              ▼
                    ┌─────────────────┐
                    │ 需要关系推理？  │
                    └────────┬────────┘
                         是 /   \ 否
                          /     \
                         ▼       ▼
              ┌─────────────┐   ┌─────────────┐
              │ 使用图RAG    │   │ 检查其他需求 │
              │ 或知识图谱   │   │            │
              └─────────────┘   └─────────────┘
```

### 场景-方法速查表

| 场景 | 推荐方法 | 备选方案 |
|------|---------|---------|
| 快速原型验证 | 简单RAG (1) | - |
| 企业知识库 | 重排序 (8) + 上下文压缩 (10) | 自适应RAG (12) |
| 法律/医疗文档 | 命题分块 (14) + 自反思RAG (13) | 图RAG (17) |
| 客服对话系统 | 反馈循环RAG (11) | 分层RAG (18) |
| 研究论文分析 | 语义分块 (2) + HyDE (19) | 上下文块标题 (5) |
| 多语言混合 | 融合检索 (16) | 文档增强 (6) |
| 实时问答 | CRAG (20) | 自适应RAG (12) |
| 海量文档库 | 分层RAG (18) + 重排序 (8) | 大数据KG (22) |

---

## 总结与学习路径

### 核心概念回顾

1. **RAG的本质**：检索 + 生成，用外部知识增强LLM
2. **分块策略**：从简单固定分块到语义分块再到原子命题
3. **检索优化**：查询转换、重排序、多策略融合
4. **生成优化**：上下文压缩、自我反思、强化学习
5. **高级架构**：自适应路由、图结构、知识图谱

### 推荐学习路径

```
Week 1: 基础掌握
├── 学习简单RAG (1) 理解核心流程
├── 实践分块策略对比 (2, 3, 14)
└── 掌握向量检索基础

Week 2: 检索优化
├── 学习查询转换 (7)
├── 实践重排序 (8) 和融合检索 (16)
└── 掌握上下文压缩 (10)

Week 3: 高级架构
├── 学习自适应RAG (12)
├── 实践自反思RAG (13) 和 CRAG (20)
└── 了解图RAG (17) 基础

Week 4: 生产实践
├── 学习反馈循环RAG (11)
├── 实践多模态RAG (15)
└── 掌握知识图谱 (22) 基础
```

### 实践建议

1. **从简到繁**：先掌握基础RAG，再逐步添加优化
2. **评估驱动**：使用 `best_rag_finder.ipynb` 评估不同方法
3. **组合使用**：多种方法可以组合（如语义分块 + 重排序）
4. **领域适配**：根据具体领域选择最适合的方法组合

### 评估指标说明

本项目使用以下指标评估RAG效果：

| 指标 | 说明 | 理想值 |
|------|------|--------|
| Faithfulness | 答案是否基于检索上下文 | 越高越好 |
| Relevancy | 答案是否与问题相关 | 越高越好 |
| Semantic Similarity | 与标准答案的语义相似度 | 越高越好 |

---

## 附录：运行环境准备

### 依赖安装

```bash
# 基础依赖
pip install openai numpy pandas scikit-learn

# PDF处理
pip install PyMuPDF

# 向量检索
pip install faiss-cpu

# 图处理（Graph RAG）
pip install networkx

# 知识图谱（Big Data KG）
pip install rdflib spacy
python -m spacy download en_core_web_sm

# BM25（Fusion RAG）
pip install rank-bm25

# 进度显示
pip install tqdm ipywidgets
```

### API配置

本项目使用 Nebius AI API（OpenAI兼容接口）：

```python
import openai

client = openai.OpenAI(
    base_url="https://api.studio.nebius.ai/v1/",
    api_key="your-api-key"
)
```

---

*本教程基于RAGtech项目编写，涵盖了RAG的基础概念、代码实现和22种方法的详细分析。建议按学习路径循序渐进，结合实际项目需求选择合适的方法组合。*
