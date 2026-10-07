# Web Search - 内容去重与离线卸载规范

> **责任领域**：`AegisAgent/src/services/web_search/dedup.py` 与 `extractor.py`
> **核心原则**：MD5 内容指纹去重、超长正文物理落盘卸载 (Artifacts Offloading)、精准证据链闭环。

---

## 1. 镜像站与转载内容指纹去重 (`dedup.py`)

### 1.1 痛点：互联网中文技术社区的严重转载冗余
在检索常见技术报错（如“`C++ undefined reference to vtable`”）时，前 10 条结果往往由不同技术博客对同一篇官方文档或 StackOverflow 答案进行全文搬运或镜像。若全部塞给模型，不仅浪费上下文空间，更会引发模型注意力被同质内容误导。

### 1.2 MD5 内容指纹去重算法
由于不同站点的 HTML 外壳不同，去重必须在**正文清洗之后**进行：

1. **规范化文本预处理**：对 `trafilatura` 提取出的 Markdown 正文去除首尾空白，转换为无格式文本流；
2. **计算 MD5 摘要**：取其前 8 位 Hex 哈希作为该网页的正文指纹：
   $$\text{Fingerprint} = \text{MD5}(\text{CleanContent})[:8]$$
3. **哈希集过滤**：单次搜索结果集中维护 `seen_fingerprints = set()`。一旦后续网页的指纹已在集合中，判定为“镜像转载”，直接丢弃该条结果，优先保留最先发现的原始源。

```python
import hashlib

class ContentDeduplicator:
    def __init__(self):
        self.seen_hashes = set()

    def is_unique(self, text: str) -> bool:
        if not text or len(text.strip()) < 50:
            return True
        content_hash = hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:8]
        if content_hash in self.seen_hashes:
            return False
        self.seen_hashes.add(content_hash)
        return True
```

---

## 2. 超长网页正文离线落盘卸载 (Artifacts Offloading)

### 2.1 物理 Token 阈值控制
技术文档（如完整的 GCC 手册或 Linux 内核补丁 diff）单篇可能长达数万字符。系统设定严格的阈值：
* **`max_content_tokens = 1500`**：单篇正文若超过 1500 Token，触发物理落盘机制；
* **`preview_chars = 200`**：落盘后只向 Agent 上下文返回前 200 字符的精简前瞻摘要。

### 2.2 离线落盘路径与命名规范
* **存储目录**：`storage/artifacts/{task_id}/web_{hash}.md`
* **落盘正文结构**：

```markdown
<!--
URL: https://gcc.gnu.org/onlinedocs/gcc/Warning-Options.html
Title: GCC Warning Options (Official Manual)
Fetched At: 2026-09-15 16:45:00 UTC
Task ID: 9b1e7c54-46c5-4428-a408-dbcbcf123456
-->

# GCC Warning Options

(此处为几千行完整的官方手册 Markdown 正文)
```

### 2.3 上下文注入规范
向 Agent 返回的搜索条目被压缩为高密度句柄：

```json
{
  "title": "GCC Warning Options (Official Manual)",
  "url": "https://gcc.gnu.org/onlinedocs/gcc/Warning-Options.html",
  "snippet": "Options to Request or Suppress Warnings. Warnings are diagnostic messages that report constructions that are not inherently erroneous but that are risky...",
  "is_offloaded": true,
  "artifact_path": "storage/artifacts/9b1e.../web_8f3a9e12.md"
}
```

Agent 在思考时若确需阅读完整参数列表，可调用 `view_file` 工具按行号或关键词精准查阅该落盘文件，彻底实现**按需读取、证据闭环**。
