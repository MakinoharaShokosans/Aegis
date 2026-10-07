# AegisRAG 切分与向量单元测试路线图 (Unit Test Roadmap)

> **定位**：`AegisRAG` 独立代码检索子系统中关于 Tree-sitter AST 解析、Markdown 结构分块、双路向量化模型推理与确定性哈希算法的单元测试路线。
> **原则**：纯 CPU 离线计算、Tree-sitter 内存直接解析、ONNX 离线模型加载、数据幂等绝对可复现。

---

## 1. 现状盘点：切分算法与向量模型覆盖矩阵

| 目标源码模块 | 对应测试文件 | 状态 | 核心验证重点 |
| :--- | :--- | :---: | :--- |
| `src/indexer/ast_splitter.py` | `tests/indexer/test_ast_splitter_c_cpp.py`<br/>`tests/indexer/test_ast_splitter_go.py` | `[x] [x]` | C/C++/Go 语法边界完整性、尾随分号吸收、宏与模板捕获、超长切片标记 |
| `src/indexer/markdown_splitter.py` | `tests/indexer/test_markdown_splitter.py` | `[x] [x]` | H1~H3 标题段落切分、面包屑作用域注入、行号单调递增性 |
| `src/indexer/fallback_splitter.py`<br/>`src/indexer/dispatch.py` | `tests/indexer/test_dispatch_and_fallback.py` | `[x] [x]` | 未识别文件定长切分、非法语法容错降级、隐藏文件与二进制忽略 |
| `src/indexer/metadata.py` | `tests/indexer/test_metadata.py` | `[x] [x]` | Pydantic 强类型约束、SHA-1 内容哈希计算、工厂方法 `build()` |
| `src/embeddings/sparse_embed.py` | `tests/embeddings/test_sparse_embedding.py` | `[x] [x]` | BM25 稀疏权重生成、`(indices, values)` 二元组格式校验、空列表安全 |
| `src/embeddings/dense_embed.py` | `tests/embeddings/test_dense_local.py` | `[x] [x]` | ONNX Runtime CPU 推理、1024 维输出、分批并发一致性 |
| `src/storage/ids.py` | `tests/storage/test_ids_and_idempotency.py` | `[x] [x]` | UUIDv5 确定性散列、元数据敏感性校验、已存在点批量过滤 |

---

## 2. 细分测试用例规范

### 2.1 Tree-sitter AST 语法感知切分器
- **C/C++ 函数与结构体边界 (`tests/indexer/test_ast_splitter_c_cpp.py`)**：
  - 完整切出 `function_definition`，绝不腰斩函数签名与函数体；
  - 完整识别 `struct_specifier`、`class_specifier`，正确将尾随分号 `;` 作为兄弟节点吸收入同一切片；
  - 模板声明（`template<typename T> class Foo`）整体打包为单个切片，禁止内部嵌套类重复分块。
- **Go 语言结构体与方法 (`tests/indexer/test_ast_splitter_go.py`)**：
  - 区分普通函数 `function_declaration` 与绑定制结构体方法 `method_declaration`；
  - 正确解析 `type Config struct { ... }`，行号定位绝对准确。

### 2.2 Markdown 面包屑与结构切分 (`tests/indexer/test_markdown_splitter.py`)
- **层级继承**：子标题切片携带上层面包屑链条（如 `"架构设计 > 存储引擎 > Qdrant 选型"`）；
- **行号追溯**：切片的 `start_line` 与 `end_line` 与原始 `.md` 文件严格对齐。

### 2.3 双路向量生成管道 (`tests/embeddings/`)
- **Sparse BM25 词法向量**：输出稀疏索引与正数词频权重，空字符串返回空列表不报错；
- **Dense 语义向量**：加载 `jinaai/jina-embeddings-v3` ONNX 权重，断言生成向量维度严格为 1024 维且 L2 范数归一化（$\|v\|_2 \approx 1.0$）。

### 2.4 确定性 Point ID 生成算法 (`tests/storage/test_ids_and_idempotency.py`)
- 计算公式：$\text{UUIDv5}(\text{NAMESPACE\_DNS}, \text{repo\_name} + ":" + \text{file\_path} + ":" + \text{start\_line} + ":" + \text{content\_hash})$；
- 多次重复计算输出完全一致；任何单项元数据变动必定输出互斥 UUID。

---

## 3. 验收标准与执行

- 全部测试在本地离线 CPU 环境下秒级完成；
- 切分器不出现代码断句或语法残损；
- 执行命令：
  ```bash
  cd /home/Skualeilu/Projects/Aegis/AegisRAG
  uv run pytest tests/indexer/ tests/embeddings/test_dense_local.py tests/embeddings/test_sparse_embedding.py tests/storage/test_ids_and_idempotency.py -v
  ```
