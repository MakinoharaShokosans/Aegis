# 05 安全对抗测试与红队攻防路线规范 (Security & Red-Teaming Index)

> **定位**：Aegis 体系中针对系统安全边界、权限黑名单规避、批量越级合谋、Prompt 注入攻击与凭据外泄的对抗性测试与红队攻防靶场路线。
> **核心原则**：假设模型不可信、假设输入有敌意、零宽/同形字/管道拼接全覆盖、越级动作与凭据外泄零容忍。

---

## 📁 安全对抗测试文档导航

| 序号 | 文档名称 | 攻防靶向目标 | 核心渗透用例 | 对应实际测试模块 |
| :--- :| :--- | :--- | :--- | :--- |
| **01** | [`01_权限越级与沙箱合谋对抗测试路线.md`](01_权限越级与沙箱合谋对抗测试路线.md) | `permission.py` 正则分类器、`tool_runner.py` 审批挂起与 `TaskRegistry` 白名单 | 分隔符/子命令绕过、Base64管道混淆、单批次混杂越级合谋、恶意/畸形resume payload | `tests/guardrails/test_permission_adversarial.py`<br/>`tests/mcps/test_vetting_adversarial.py` |
| **02** | [`02_Prompt注入与Canary金丝雀红队测试路线.md`](02_Prompt注入与Canary金丝雀红队测试路线.md) | 工具观察值 XML 沙箱隔离、`CanaryGuard` 动态金丝雀探针与安全闸门 | 越狱 Prompt 诱导、工具输出伪造系统指令、金丝雀 Token 片段变形泄露与硬熔断 | `tests/guardrails/test_canary_guard.py`<br/>`tests/test_prompt_isolation.py` |

---

## 🛠️ 快速执行命令

```bash
cd /home/Skualeilu/Projects/Aegis/AegisAgent

# 1. 运行权限分类器对抗测试 (含 Hypothesis 属性模糊测试)
uv run pytest tests/guardrails/test_permission_adversarial.py -v

# 2. 运行 MCP 静态审查与 Prompt 注入规避测试
uv run pytest tests/mcps/test_vetting_adversarial.py -v

# 3. 运行金丝雀泄露探测与 XML 沙箱隔离测试
uv run pytest tests/guardrails/test_canary_guard.py tests/test_prompt_isolation.py -v
```
