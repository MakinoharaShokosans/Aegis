# Bash 执行沙箱 - 命令审计与工作区沙箱规范

> **责任领域**：`AegisAgent/src/services/bash_shell/audit.py` 与 `sandbox.py`  
> **核心原则**：高危破坏性指令前置正则拦截、工作目录绑定工作区根路径 (CWD)、路径越界逃逸防护、工作区修改与内部产物落盘严格物理解耦。

---

## 1. 高危指令前置正则审计 (`CommandAudit`)

大模型在面对复杂的系统排查时，可能因幻觉误生成高危破坏性指令。系统在命令派发至子进程前，实施硬编码的高危正则匹配。

### 1.1 拦截黑名单矩阵

```text
┌──────────────────────┬────────────────────────────────────────────┬─────────────────────────────┐
│ 风险等级             │ 典型高危指令特征                           │ 拦截处理与响应状态           │
├──────────────────────┼────────────────────────────────────────────┼─────────────────────────────┤
│ 灾难级破坏 (CRITICAL) │ rm -rf /、rm -rf /*、mkfs.*、dd if=/dev/.. │ 立即拒绝，返回 403 阻断告警 │
├──────────────────────┼────────────────────────────────────────────┼─────────────────────────────┤
│ 宿主系统侵入 (SYSTEM) │ 修改 /etc/shadow、/etc/passwd、修改系统服务 │ 立即阻断，严防逃逸宿主机    │
├──────────────────────┼────────────────────────────────────────────┼─────────────────────────────┤
│ 恶性耗尽 (RESOURCE)  │ :(){ :|:& };: (Fork 炸弹)                  │ 立即拦截                    │
├──────────────────────┼────────────────────────────────────────────┼─────────────────────────────┤
│ 交互式挂起 (HANG)    │ 裸 sudo、无 -y 参数的包安装交互式命令      │ 提示缺少非交互参数          │
└──────────────────────┴────────────────────────────────────────────┴─────────────────────────────┘
```

### 1.2 审计代码规范 (`audit.py`)

```python
import re
from typing import Tuple

DANGEROUS_PATTERNS = [
    (r"\brm\s+-[rfRF]{1,4}\s+/\s*$", "禁止全盘删除根目录操作"),
    (r"\brm\s+-[rfRF]{1,4}\s+/\*", "禁止通配删除根目录操作"),
    (r"\bmkfs(\.\w+)?\b", "禁止格式化文件系统操作"),
    (r"\bdd\s+if=.*?of=/dev/[svh]d[a-z]", "禁止裸写物理磁盘"),
    (r":\(\)\{\s*:\|:&\s*\};:", "检测到 Fork 炸弹恶意语法"),
    (r"\b(shutdown|reboot|init\s+0|halt)\b", "禁止关闭或重启宿主机"),
]

def audit_command(command: str) -> Tuple[bool, str]:
    """
    检查命令安全性
    Returns:
        (is_safe, error_message)
    """
    clean_cmd = command.strip()
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, clean_cmd):
            return False, f"[安全红线拦截] 命令包含高危行为: {reason}"
    return True, ""
```

---

## 2. 工作区沙箱绑定规范 (Workspace-bound CWD)

### 2.1 历史教训：CWD 与落盘目录的混淆
* **原错误设计**：曾有人尝试将子进程 `cwd` 锁定在临时目录（如 `/tmp/aegis_sandbox`）以求"绝对安全"；
* **根本矛盾**：Aegis 的定位是**代码工程研究与修改智能体**，若 `cwd` 锁在临时目录，Agent 执行 `make`、`git diff`、修代码均无法作用在目标工程上，导致任务根本无法完成；
* **裁决结论**：**执行目录（`cwd`）必须强绑定目标工作区的物理根路径 `root_path`！**

```python
# 必须由上层携带工作区标识与根路径，并做一致性校验
workspace_root = Path(request.workspace_root).resolve()
if not workspace_root.is_dir():
    raise HTTPException(status_code=400, detail="工作区物理根路径不存在")
```

---

## 3. 路径越界逃逸防护 (Path Escape Guard)

为防止命令通过 `../../` 恶意操作宿主机其他敏感工程目录：
1. **显式路径校验**：对所有随请求下发的文件参数进行 `Path.resolve()` 解析；
2. **子树包含断言**：断言目标解析后的绝对路径必须以 `workspace_root` 作为前缀：
   ```python
   def assert_within_workspace(target_path: Path, workspace_root: Path) -> None:
       resolved_target = target_path.resolve()
       resolved_root = workspace_root.resolve()
       if not str(resolved_target).startswith(str(resolved_root)):
           raise PermissionError(
               f"路径逃逸违规: 目标路径 {resolved_target} 超出工作区根目录 {resolved_root}"
           )
   ```

---

## 4. 目标工程与内部资产隔离原则

* **用户工程（`root_path`）**：仅允许 Agent 生成或修改用户业务代码、测试用例和补丁文件；
* **Aegis 内部资产（`storage/`）**：执行日志、产物离线卸载、Checkpoint 快照一律写入 Aegis 自己的 `storage/artifacts/{task_id}/`，**严禁向用户目标工程中倾倒任何 Aegis 运行时系统垃圾**。
