# RAG 检索服务 - 服务契约与客户端适配规范

> **责任领域**：`AegisRAG/src/api/`（📋 待创建）与 `AegisAgent/src/tools/builtin/rag_search.py`（✅ 已实现）
> **核心原则**：HTTP REST 契约化通信、响应字段与既有客户端严格对齐、解耦红线（禁止反向依赖 `agent_runtime`）。

---

## 1. 服务接口定义（FastAPI 端点，📋 待实现）

AegisRAG 作为独立微服务（默认运行于 `127.0.0.1:8001`），需要暴露以下接口。**服务端字段命名必须与下方 §1.1 对齐**——这不是自由设计空间，而是要去匹配 `AegisAgent/src/tools/builtin/rag_search.py` 里已经写死、已经在跑的客户端代码。

### 1.1 检索端点：`POST /api/v1/retrieve`

#### 请求体（`RetrieveRequest`）

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--: | :--- |
| `query` | str | ✅ | 检索意图文本 |
| `top_k` | int | — | 返回切片数量上限；缺省取 `[retrieval].default_top_k`（服务端配置，见 `04` §3、`README.md` §4），非硬编码值 |
| `filters` | object | — | 可选 Payload 过滤条件，当前仅约定 `{"language": str}`（见 `04` §2），未来可扩展 `repo_name`/`file_path_prefix` |

```json
{
  "query": "如何初始化 GlobalMemoryBudget 内存池",
  "top_k": 5,
  "filters": {"language": "python"}
}
```

#### 响应体（`RetrieveResponse`）

**关键约束**：`rag_search.py` 现有实现读取字段时写的是 `data.get("results") or data.get("chunks") or []`——即客户端同时容忍 `results` 与 `chunks` 两种命名。**服务端实现时应只使用 `results` 作为唯一权威字段**（`chunks` 兼容分支是既有客户端为了兼容不确定的服务端命名而留的双保险，不代表服务端可以随意选用其中之一；新写服务端代码时不要利用这个容忍度引入第二个事实上的字段名，否则未来任何人读代码都要同时确认两个字段是否语义一致）。

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `results` | array | 切片数组，见下 |
| `results[].chunk_id` | str | Qdrant 确定性 Point ID（`03` §3），**不可省略**——见下方说明 |
| `results[].file_path` | str | 相对仓库根目录路径 |
| `results[].start_line` / `end_line` | int | 起止行号 |
| `results[].content` | str | 切片原文（完整未截断，见 `03` §1） |
| `results[].git_commit` | str \| null | 索引时的提交哈希，可选展示 |
| `results[].score` | float | 精排相关性分数（`rag_search.py` 当前未读取，服务端仍需提供，见 `04` §3） |
| `low_confidence` | bool | 见 `04` §4，全部结果精排分数偏低时置 `true` |

> **`chunk_id` 是本规范新增的必填字段，不是可选装饰**：`rag_search.py` 当前确实不读取它（客户端只关心展示），但 `src/evaluation/rag_bench/` 现成的评测 harness（`dataset.py::EvalCase.gold_chunk_ids` + `evaluate_retrieval.py::RetrievalResult`）是靠比对"检索返回的 ID 序列"与"标注金标 ID 集合"算 HitRate/MRR/NDCG 的——如果响应体里没有稳定 ID，`06_evaluation_and_benchmarking.md` 描述的评测链路根本没有能挂接的字段，服务端实现时不能把它省掉。`chunk_id` 直接复用 `03` §3 的确定性 Point ID（`uuid5(...)` 结果的字符串形式），这样它在"内容不变"的多次 `ingest` 之间保持稳定，标注一次金标集可以长期复用而不会因为重新索引就集体失效。

```json
{
  "results": [
    {
      "chunk_id": "a1b2c3d4-e5f6-5789-9abc-def012345678",
      "file_path": "src/services/bash_shell/memory_pool.py",
      "start_line": 42,
      "end_line": 78,
      "content": "class GlobalMemoryBudget:\n    ...",
      "git_commit": "5a55892a2155ec5a69ebf7b672a5a661f658fe75",
      "score": 0.87
    }
  ],
  "low_confidence": false
}
```

**空结果**（`rag_search.py` 已实现对应分支，✅）：`results` 为空数组时，客户端把它渲染为 `"未检索到相关代码片段。"` 并设 `meta={"hits": 0}`，不视为错误。

### 1.2 索引写入端点：`POST /api/v1/documents/ingest`

#### 请求体（`IngestRequest`）

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--: | :--- |
| `repo_root` | str | ✅ | 目标仓库绝对路径 |
| `repo_name` | str | ✅ | 仓库标识（Payload 过滤用，见 `03` §2） |
| `incremental` | bool | — | `true`（默认）：走 `02` §1 / `03` §3 的哈希增量策略；`false`：忽略现存哈希强制全量重新向量化（用于模型或切分逻辑升级后的重建） |

#### 响应体（`IngestResponse`）

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `indexed` | int | 新写入/更新的切片数 |
| `skipped` | int | 内容未变、跳过向量化的切片数（见 `03` §3） |
| `deleted` | int | 因源文件已不存在而清理的旧切片数（见 `03` §4） |
| `degraded_files` | array\<str\> | AST 解析失败、降级走通用切分的文件列表（见 `02` §4，必须如实上报，不能吞掉） |
| `duration_ms` | int | 本次 ingest 总耗时 |

### 1.3 健康检查：`GET /api/v1/health`

```json
{
  "status": "ok",
  "service": "aegis-rag",
  "version": "0.1.0",
  "qdrant": {
    "mode": "local",
    "collection_ready": true,
    "point_count": 18432,
    "vector_size": 384
  },
  "embedding_model_loaded": true
}
```

`collection_ready=false` 或 `embedding_model_loaded=false` 时，`status` 应整体置为 `"degraded"`——对齐 `01` §5 的故障隔离契约，Agent 的依赖探测（`api/routes/health.py`）打的就是这个端点。

## 2. 错误码与降级契约

| HTTP | 错误码 | 产生原因 | Agent 侧处理策略 |
| :--- | :--- | :--- | :--- |
| `200` | — | 正常检索，含空结果 | 空结果按 §1.1 处理，非错误 |
| `503` | `COLLECTION_NOT_READY` | Qdrant 未连接、Collection 未初始化，或该 `repo_name` 从未 `ingest` 过 | 提示"该工作区尚未建立索引"，引导触发 `ingest`（见 `02` §1） |
| `500` | `DIMENSION_MISMATCH` | 启动期已做强校验（`03` §2），此错误码理论上不应在运行期出现；若出现说明启动校验被绕过，属于服务端 bug | 计入连续错误，不应引导模型重试同一操作 |
| `422` | `VALIDATION_ERROR` | 请求体不满足 DTO 约束 | 装配层 bug，检查请求字段 |
| `404` | `REPO_NOT_INDEXED`（`ingest` 场景外） | 对不存在的 `repo_root` 发起检索 | 同 `COLLECTION_NOT_READY` |
| `502` | `UPSTREAM_MODEL_ERROR`（v2 新增） | `[embedding]`/`[rerank]` `mode="remote"` 时上游网关（默认 `api.openlux.ai/v1`）请求失败：网络异常、鉴权失败、非 2xx 响应、返回条目数与请求不符 | 计入连续错误；与 `COLLECTION_NOT_READY` 的区别是"AegisRAG 自身正常，是它依赖的上游出了问题" |

**统一错误体**（对齐 `bash_shell`/`web_search` 既有约定）：

```json
{
  "error": {
    "code": "COLLECTION_NOT_READY",
    "message": "仓库 aegis-agent 尚未建立索引，请先调用 /api/v1/documents/ingest"
  }
}
```

## 3. Agent ToolLayer 客户端适配器（`tools/builtin/rag_search.py`，✅ 已实现）

已实现代码见 `AegisAgent/src/tools/builtin/rag_search.py`，无需在服务端开发时改动，仅在服务端字段与本节约定不一致时才需要回头核对。三个容易忽略的对接细节：

1. `RagSearchTool.invoke` 只透传 `query` / `top_k` / `filters.language` 三项，`repo_name`/`repo_root` 不在工具入参里——说明**当前的 `rag_search` 工具调用隐式假设"检索范围是当前任务绑定的唯一工作区"**，服务端若要支持多仓库检索，`repo_name` 的确定需要由更上层（Agent 装配 `RagSearchTool` 实例时的构造参数，类似 `BashTool` 的 `workspace_id`）注入，而不是由模型每次调用时指定——这与 `BashTool`/`bash_shell` 服务的既有模式一致，实现时应保持同构；
2. 客户端超时固定 `self.timeout_sec = 60.0`，与 `AegisAgent/config/config.toml` `[services].timeout_sec` 独立配置，服务端响应时间预算（`04` §5）需要控制在这个上限之内；
3. `DependencyUnavailableError` 是唯一的网络层失败出口——服务端返回的 4xx/5xx 业务错误体（§2）需要经由 `ServiceClient` 转换后仍能被 `RagSearchTool` 正确识别为"工具失败"而非"未捕获异常"，实现服务端 API 时对照 `bash_shell`/`web_search` 的 `ServiceClient` 错误处理路径保持一致的转换约定。
