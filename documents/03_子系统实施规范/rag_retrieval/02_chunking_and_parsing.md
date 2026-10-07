# 语法感知切分与索引触发规范

> **责任领域**：`AegisRAG/src/indexer/`
> **状态**： 规划中，尚未实现
> **核心原则**：语法边界完整优先于定长切片、证据元数据强制注入、幂等可重复索引。

---

## 1. 索引触发时机（设计空白补全）

**现状**：ADR 与里程碑文档都只定义了 `POST /api/v1/documents/ingest` 这个入口存在，**从未说明谁在什么时机调用它**。这是当前最大的设计空白，实现前必须先定下来，否则 Ingest 流水线无从触发。

**本规范给出的方案**（需在实现前与设计者确认，不是既成决策）：

1. **主触发路径——工作区注册时机**：`AegisAgent` 的 `POST /workspaces` 或会话首次绑定某个目标仓库路径时，由 Agent API 层异步调用一次 `POST /api/v1/documents/ingest`（全量索引），不阻塞工作区创建的响应本身（fire-and-forget + 后续可查询索引状态）。
2. **兜底触发路径——按需索引**：若工作区注册时的自动索引被跳过或失败，`rag_search` 工具在收到 `COLLECTION_NOT_READY`（见 `05` §2）时，Agent 侧应能感知并提示"该工作区尚未建立索引"，引导用户或 Agent 显式触发一次 `ingest`（而不是静默返回空结果，让模型误以为代码库里真的没有相关内容）。
3. **增量再索引**：不提供"文件系统 watch 自动感知变更"（那是持续运行的后台服务能力，超出当前单机、按任务生命周期运行的定位）。改为**内容哈希幂等**策略（见 §4）——每次 `ingest` 调用都可以对同一仓库重复执行，未变更文件的切片天然被跳过（哈希相同），变更文件的旧切片被覆盖，删除的文件的残留切片被清理（见 `03` §4）。调用方（Agent 或用户）自行决定何时触发一次"重新索引"，服务端保证重复调用是廉价、幂等的。

## 2. 语言分发与切分器选择

按文件扩展名匹配 `[indexer].supported_languages`，分发到三类切分器之一：

| 文件类型 | 切分器 | 依赖 | 状态 |
| :--- | :--- | :--- | :--: |
| `.c` `.h` | `ast_splitter.py`（tree-sitter-c） | `tree-sitter-c` | ，依赖已在 `pyproject.toml` 锁定 |
| `.cpp` `.cc` `.hpp` `.cxx` | `ast_splitter.py`（tree-sitter-cpp） | `tree-sitter-cpp` | ，依赖已锁定 |
| `.go` | `ast_splitter.py`（tree-sitter-go） | `tree-sitter-go` | ，依赖已锁定 |
| `.md` `.mdx` | `markdown_splitter.py`（`MarkdownHeaderTextSplitter`） | `langchain-text-splitters` | ，依赖已锁定 |
| `.py` 及其它未匹配 AST 语法包的源码 | `fallback_splitter.py`（见 §3） | `langchain-text-splitters` | ，**本规范新增，milestone 未列出** |

## 3. 关于 `python`/`rust` 的纠偏：为什么不是"真 AST"

现存三份文档对语言支持范围的说法互相矛盾，实现前必须先对齐：

* **ADR**（`技术选型/rag_retrieval.md` §2.4）：只提到 C/C++、Go；
* **`rag_config.toml`**：`supported_languages = ["c", "cpp", "go", "python"]`——包含 `python`；
* **里程碑草案**（`documents/里程碑/AegisRAG/rag_retrieval.md` 二）：写"支持 C/C++、Go、Python、**Rust** 语法树解析"；
* **`pyproject.toml` 实际锁定依赖**：只有 `tree-sitter-c` / `tree-sitter-cpp` / `tree-sitter-go`，**没有 `tree-sitter-python`，也没有 `tree-sitter-rust`**。

**本规范的裁决**（以 ADR 为权威、以已锁定依赖为地面真相）：

1. **真 AST 语法切分范围锁定为 C/C++/Go**，不额外引入 `tree-sitter-python`/`tree-sitter-rust` 这类新的 C 扩展重依赖——这与本子系统"物理独立正是为了隔离 C 扩展风险"的定位（`01` §1）是一致的，为了 Python 支持再引入一个新的 C 扩展来源，是在架构上开倒车。
2. **`python` 走 `fallback_splitter.py`**：使用已经锁定的 `langchain-text-splitters` 提供的 `RecursiveCharacterTextSplitter.from_language(Language.PYTHON)`——这是启发式（按 `def`/`class`/缩进边界切分），不是真正的语法树解析，但不需要新依赖，且能保持函数级别的大致完整性，作为务实的折中。`rag_config.toml` 里保留 `python` 是合理的，只是要在文档里说清楚它走的是哪条路径，不能让人误以为和 C/C++/Go 是同等精度。
3. **`rust` 移出当前范围**：milestone 草案里的 `Rust` 缺乏 ADR 背书、缺乏依赖锁定，属于文档起草时的超前表述。建议后续在里程碑文档里把 `Rust` 一项移到"未来可选、当前无依赖"的备注中，避免继续误导。
4. **完全未匹配任何规则的文件**（如 `.json` `.yaml` `.sh` `.toml`）：同样走 `fallback_splitter.py`，但使用通用的定长切分（`RecursiveCharacterTextSplitter` 默认策略，按 `[indexer].chunk_size`/`chunk_overlap`），不做语言特定优化——这也是 `[indexer].chunk_size`/`chunk_overlap` 两项配置**真正生效的唯一场景**：AST 与 Markdown 切分都以语法边界为准，不消费这两个配置值。

## 4. AST 切分规则（C/C++/Go）

* **切分边界节点**：`function_definition`（函数体）、`struct_specifier`/`type_declaration`（结构体/类型定义）、`enum_specifier`（枚举）、顶层 `preproc_function_def`/`#define` 宏定义（C/C++）；Go 额外覆盖 `method_declaration`、`type_spec`（`struct`/`interface`）。
* **保持语法块完整**：切分永远沿着 tree-sitter 语法树的节点边界走，**不允许把一个函数体从中腰斩**——这是 ADR 的核心诉求（§2.4），必须作为硬约束。
* **超大函数的处理**（ADR 未覆盖的边界情况）：单个函数体本身就超过合理切片长度（例如超过 `[embedding].max_length` 对应的 token 数）时，不能违反"保持语法块完整"的原则去暴力腰斩，而应该：整块保留为一个切片，交给 `03` §1 的截断策略在向量化前处理（截断参与 embedding 的文本，但落盘的 `content` 与元数据保留完整原文），并在切片元数据里标记 `oversized=true`，供检索结果展示时提示"内容已截断，建议结合行号直接查看源文件"。
* **文件级失败降级**：单个文件 AST 解析失败（语法错误、tree-sitter 不支持的语言变体）不应中断整批 `ingest`，该文件降级走 `fallback_splitter.py` 并在 ingest 响应里的 `skipped`/`degraded` 列表中如实上报（见 `05` §2），不能静默吞掉。

## 5. Markdown 切分规则

`MarkdownHeaderTextSplitter` 按标题层级（H1/H2/H3）切分，每个切片携带其标题面包屑路径（如 `# 一 > ## 1.1`）作为元数据的一部分，保证切片脱离原文后仍能看出所属章节上下文——直接复用本仓库 `documents/` 自身大量使用的标题层级结构作为天然测试语料。

## 6. 证据元数据 Schema（所有切分器统一输出）

无论走哪条切分路径，输出的切片对象必须携带以下字段（对齐 Agent 侧 `rag_search.py` 已实现的字段消费）：

| 字段 | 说明 | 消费方 |
| :--- | :--- | :--- |
| `file_path` | 相对仓库根目录的路径 | `rag_search.py` 拼接 `location` 展示 |
| `start_line` / `end_line` | 起止行号（1-indexed，闭区间） | 同上 |
| `content` | 切片原文（未截断的完整版本） | 同上 |
| `git_commit` | 索引时刻 `git rev-parse HEAD` 取得的提交哈希 | 同上（可选展示） |
| `language` | 切分器判定的语言标签 | `rag_search.py` 的 `filters.language` 过滤依据 |
| `repo_name` | 仓库标识，供多仓库场景下的 Payload 过滤 | `04` §2 的预过滤 |
| `content_hash` | 切片原文的确定性哈希（如 `sha1(content)`） | `03` §3 幂等写入与增量判定的关键字段 |
| `chunk_type` | `function` / `struct` / `markdown_section` / `generic` 等 | 未来可用于结果展示分类，当前非强制消费 |
| `enclosing_scope` | 切片所属的封闭作用域路径（如 `namespace::ClassName::method_name`，或 Markdown 的标题面包屑） | `03` §5（CCH 上下文标题头，未来增强） |
| `chunk_index` | 切片在其所属文件内的**顺序序号**（从 0 起，按 `start_line` 排序） | `04` §7（RSE 相邻段落缝合，未来增强）——AST/Markdown 切分器天然按文件遍历顺序产出，赋序号零额外成本 |

**元数据缺失即拒绝入库**：`file_path`/`start_line`/`end_line`/`content_hash` 四项任一缺失，该切片不得写入 Qdrant（宁可少索引，不能让证据链断裂——这是 ADR "强元数据注入"诉求的具体化落地标准）。`enclosing_scope`/`chunk_index` 两项是为 §7 未来增强预留的字段，当前阶段**不作为拒绝入库的强制项**——切分器拿不到时留空即可，不影响核心检索链路。

## 7. 未来增强：上下文与检索质量优化（非本轮核心范围）

以下技术点来自对通用 RAG 实践的调研（`知识库/技术栈学习/RAG/TEMP/`），已判断与本项目"C/C++/Go 源码检索、单机 CPU、零 GPU"的定位不冲突，但**不是** `01`~`05` 当前核心范围的一部分——先把核心链路（AST 切分 + Dense/Sparse + RRF + Cross-Encoder 精排）落地并用 `06_evaluation_and_benchmarking.md` 跑出基线后，再决定是否值得投入。此处只做设计记录，避免未来重新调研一遍。

* **上下文切片标题头（CCH, Contextual Chunk Headers）**——具体方案见 `03` §6，涉及的元数据来源（`enclosing_scope`）在本节 §6 已预留字段位。
* **相邻段落缝合（RSE）**——见 `04` §6，本节仅负责在切分阶段把它需要的原始信号（`chunk_index`）备好。

> 查询侧的语义改写类技术（如查询扩写/假设性文档生成）不在本节讨论范围内——那类技术的本质是"推理"而非"切分/检索"，不属于 AegisRAG 职责，边界说明见 `01` §6。
