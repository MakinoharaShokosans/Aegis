"""三级权限分级与越级判定纯函数单元测试 (guardrails/permission.py)。"""

from types import SimpleNamespace
import pytest

from agent_runtime.config import PermissionsConfig
from agent_runtime.guardrails.permission import (
    ACTION_GLOBAL_ENV,
    ACTION_NETWORK_EGRESS,
    ACTION_PRIVILEGED,
    ACTION_READ,
    ACTION_UNKNOWN,
    ACTION_WORKSPACE_WRITE,
    LEVEL_ORDER,
    action_signature,
    check_permission,
    normalize_level,
    required_level_for,
)


@pytest.fixture
def permissions_config() -> PermissionsConfig:
    """标准测试权限配置。"""
    return PermissionsConfig(
        default_level="workspace_write",
        unknown_tool_level="full_permissions",
        read_only_tools=["view_file", "rag_search", "load_skill", "delegate_research"],
        workspace_write_tools=["write_file", "replace_file"],
        full_permission_tools=["admin_tool"],
        bash_tools=["bash"],
    )


# ==============================================================================
# 1. normalize_level
# ==============================================================================

def test_normalize_level():
    """测试权限级别字符串归一化。"""
    assert normalize_level("read_only") == "read_only"
    assert normalize_level("workspace_write") == "workspace_write"
    assert normalize_level("full_permissions") == "full_permissions"
    assert normalize_level("READ_ONLY") == "read_only"
    assert normalize_level("  Workspace_Write  ") == "workspace_write"

    # 非法或空值回退默认 workspace_write
    assert normalize_level("") == "workspace_write"
    assert normalize_level(None) == "workspace_write"
    assert normalize_level("super_admin") == "workspace_write"
    assert normalize_level(123) == "workspace_write"


# ==============================================================================
# 2. required_level_for
# ==============================================================================

def test_required_level_for_explicit_tool_lists(permissions_config: PermissionsConfig):
    """测试显式工具名单的优先级最高。"""
    # 1. 只读名单
    level, act_type, reason = required_level_for("view_file", {"path": "a.txt"}, permissions_config)
    assert level == "read_only"
    assert act_type == ACTION_READ

    # 2. 工作区写入名单
    level, act_type, reason = required_level_for("write_file", {"path": "a.txt", "content": "hi"}, permissions_config)
    assert level == "workspace_write"
    assert act_type == ACTION_WORKSPACE_WRITE

    # 3. 特权名单
    level, act_type, reason = required_level_for("admin_tool", {}, permissions_config)
    assert level == "full_permissions"
    assert act_type == ACTION_PRIVILEGED


def test_required_level_for_bash_classification(permissions_config: PermissionsConfig):
    """测试 Bash 命令的三分类规则与 action_type 区分。"""
    # 1. 网络外联 -> full_permissions (network_egress)
    net_cmds = [
        "git push origin main",
        "curl -s https://example.com",
        "wget http://test.org/pkg.tar.gz",
        "ssh user@remote",
        "scp file.txt user@remote:/tmp",
    ]
    for cmd in net_cmds:
        level, act_type, _ = required_level_for("bash", {"command": cmd}, permissions_config)
        assert level == "full_permissions", f"Failed on {cmd}"
        assert act_type == ACTION_NETWORK_EGRESS, f"Failed act_type on {cmd}"

    # 2. 全局环境与特权 -> full_permissions (global_env)
    env_cmds = [
        "pip install requests",
        "pip3 install numpy",
        "npm install lodash",
        "sudo apt-get update",
        "docker run -d redis",
    ]
    for cmd in env_cmds:
        level, act_type, _ = required_level_for("bash", {"command": cmd}, permissions_config)
        assert level == "full_permissions", f"Failed on {cmd}"
        assert act_type == ACTION_GLOBAL_ENV, f"Failed act_type on {cmd}"

    # 3. 工作区写入 / 构建 / 测试 -> workspace_write
    write_cmds = [
        "echo 'hello' > output.txt",
        "echo 'append' >> log.txt",
        "rm old.py",
        "mv a.txt b.txt",
        "mkdir -p src/utils",
        "git add .",
        "git commit -m 'fix bug'",
        "make -j4",
        "cargo check",
        "pytest tests/ -v",
        "npm test",
        "sed -i 's/foo/bar/g' main.c",
    ]
    for cmd in write_cmds:
        level, act_type, _ = required_level_for("bash", {"command": cmd}, permissions_config)
        assert level == "workspace_write", f"Failed on {cmd}"
        assert act_type == ACTION_WORKSPACE_WRITE, f"Failed act_type on {cmd}"

    # 4. 只读巡检命令 -> read_only
    read_cmds = [
        "cat README.md",
        "head -n 20 main.py",
        "ls -la src/",
        "find . -name '*.py'",
        "grep -rn 'TODO' .",
        "git status",
        "git diff HEAD~1",
        "git log -n 5",
        "pwd",
    ]
    for cmd in read_cmds:
        level, act_type, _ = required_level_for("bash", {"command": cmd}, permissions_config)
        assert level == "read_only", f"Failed on {cmd}"
        assert act_type == ACTION_READ, f"Failed act_type on {cmd}"


def test_required_level_for_unknown_tool(permissions_config: PermissionsConfig):
    """测试未知工具按 unknown_tool_level 保守处理。"""
    level, act_type, reason = required_level_for("third_party_mcp_tool", {"foo": "bar"}, permissions_config)
    assert level == "full_permissions"
    assert act_type == ACTION_UNKNOWN
    assert "未知工具" in reason

    # 自定义未知工具回退级别
    custom_cfg = SimpleNamespace(
        full_permission_tools=[],
        workspace_write_tools=[],
        read_only_tools=[],
        bash_tools=[],
        unknown_tool_level="workspace_write",
    )
    level, act_type, _ = required_level_for("another_tool", {}, custom_cfg)
    assert level == "workspace_write"


# ==============================================================================
# 3. check_permission
# ==============================================================================

def test_check_permission_allowed_boundaries(permissions_config: PermissionsConfig):
    """测试权限允许放行的偏序边界。"""
    # 1. full_permissions 会话：允许所有级别
    dec = check_permission("full_permissions", "bash", {"command": "git push origin main"}, permissions_config)
    assert dec.allowed is True
    assert dec.current_level == "full_permissions"
    assert dec.required_level == "full_permissions"

    dec = check_permission("full_permissions", "write_file", {"path": "a.txt"}, permissions_config)
    assert dec.allowed is True

    dec = check_permission("full_permissions", "view_file", {"path": "a.txt"}, permissions_config)
    assert dec.allowed is True

    # 2. workspace_write 会话：允许 workspace_write 与 read_only，禁止 full_permissions
    dec_write = check_permission("workspace_write", "write_file", {"path": "a.txt"}, permissions_config)
    assert dec_write.allowed is True
    assert dec_write.required_level == "workspace_write"

    dec_read = check_permission("workspace_write", "view_file", {"path": "a.txt"}, permissions_config)
    assert dec_read.allowed is True
    assert dec_read.required_level == "read_only"

    dec_blocked = check_permission("workspace_write", "bash", {"command": "curl http://evil.com"}, permissions_config)
    assert dec_blocked.allowed is False
    assert dec_blocked.required_level == "full_permissions"
    assert "高于当前级别" in dec_blocked.reason

    # 3. read_only 会话：仅允许 read_only
    dec_ro_ok = check_permission("read_only", "view_file", {"path": "a.txt"}, permissions_config)
    assert dec_ro_ok.allowed is True

    dec_ro_blocked_write = check_permission("read_only", "write_file", {"path": "a.txt"}, permissions_config)
    assert dec_ro_blocked_write.allowed is False
    assert dec_ro_blocked_write.required_level == "workspace_write"

    dec_ro_blocked_full = check_permission("read_only", "bash", {"command": "git push"}, permissions_config)
    assert dec_ro_blocked_full.allowed is False
    assert dec_ro_blocked_full.required_level == "full_permissions"


# ==============================================================================
# 4. action_signature
# ==============================================================================

def test_action_signature():
    """测试会话白名单动作签名一致性与参数哈希。"""
    # 1. 相同工具与入参 -> 签名严格一致
    sig1 = action_signature("bash", {"command": "git push origin main"})
    sig2 = action_signature("bash", {"command": "git push origin main"})
    assert sig1 == sig2
    assert len(sig1) == 16

    # 2. 字典键插入顺序不同 -> 签名仍严格一致 (验证 sort_keys=True)
    args_a = {"command": "make test", "timeout": 30, "env": {"FOO": "1", "BAR": "2"}}
    args_b = {"timeout": 30, "env": {"BAR": "2", "FOO": "1"}, "command": "make test"}
    assert action_signature("bash", args_a) == action_signature("bash", args_b)

    # 3. 参数不同 -> 签名不同
    sig3 = action_signature("bash", {"command": "git push origin dev"})
    assert sig1 != sig3

    # 4. 工具名不同 -> 签名不同
    sig4 = action_signature("custom_bash", {"command": "git push origin main"})
    assert sig1 != sig4
