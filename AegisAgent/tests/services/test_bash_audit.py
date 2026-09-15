"""Bash Shell 前置审计与越界拦截单元测试。"""

from pathlib import Path
import pytest

from services.bash_shell.audit import (
    AuditRejected,
    CommandAudit,
    PathEscapeError,
    ensure_within_root,
)


def test_command_audit_dangerous_commands_rejected():
    """测试高危指令黑名单正则前置拦截。"""
    audit = CommandAudit()

    # 1. rm -rf / 及其变体
    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("rm -rf /")
    assert exc_info.value.rule == "RM_RF_ROOT"

    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("rm -fr /")
    assert exc_info.value.rule == "RM_RF_ROOT"

    # 2. mkfs 格式化
    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("mkfs.ext4 /dev/sdb1")
    assert exc_info.value.rule == "MKFS"

    # 3. 裸设备写入
    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("dd if=/dev/zero of=/dev/sda bs=1M")
    assert exc_info.value.rule == "DD_TO_DEVICE"

    # 4. 关机与重启
    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("shutdown -h now")
    assert exc_info.value.rule == "POWER_CONTROL"

    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("systemctl reboot")
    assert exc_info.value.rule == "POWER_CONTROL"

    # 5. Shell fork bomb
    with pytest.raises(AuditRejected) as exc_info:
        audit.audit(":(){ :|:& };:")
    assert exc_info.value.rule == "FORK_BOMB"

    # 6. 敏感系统路径写操作
    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("echo 'hacked' >> /etc/passwd")
    assert exc_info.value.rule == "SENSITIVE_SYSTEM_WRITE"

    # 7. 递归放开根目录权限
    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("chmod -R 777 /")
    assert exc_info.value.rule == "RECURSIVE_ROOT_PERMISSION"

    # 8. 空命令拦截
    with pytest.raises(AuditRejected) as exc_info:
        audit.audit("   ")
    assert exc_info.value.rule == "EMPTY_COMMAND"


def test_command_audit_safe_commands_allowed():
    """测试正常和只读指令安全放行，不产生误报。"""
    audit = CommandAudit()

    safe_commands = [
        "ls -la /tmp",
        "cat /etc/passwd",  # 读敏感文件只读允许
        "grep 'root' /etc/shadow",  # 只读允许
        "echo 'hello world' > ./output.txt",
        "python -m pytest tests/ -v",
        "echo 'data' > /dev/null",  # 安全伪设备
    ]

    for cmd in safe_commands:
        # 不应抛出 AuditRejected
        audit.audit(cmd)


def test_command_audit_write_target_extraction():
    """测试从命令中提取显式重定向和写入目标。"""
    audit = CommandAudit()

    cmd = "echo a > out.txt && cat out.txt | tee log.txt >> append.txt 2> /dev/null"
    targets = audit.extract_write_targets(cmd)

    assert "out.txt" in targets
    assert "log.txt" in targets
    assert "append.txt" in targets
    assert "/dev/null" not in targets  # 自动过滤安全设备


def test_ensure_within_root_boundary(tmp_path: Path):
    """测试路径越界边界校验。"""
    root = tmp_path / "workspace"
    root.mkdir()
    sub_dir = root / "sub"
    sub_dir.mkdir()
    test_file = sub_dir / "test.txt"
    test_file.touch()

    # 1. 正常子路径
    resolved = ensure_within_root("sub/test.txt", root)
    assert resolved == test_file.resolve()

    # 2. 根目录自身也合法
    assert ensure_within_root(".", root) == root.resolve()

    # 3. 越界路径抛出 PathEscapeError
    with pytest.raises(PathEscapeError):
        ensure_within_root("../escape.txt", root)

    with pytest.raises(PathEscapeError):
        ensure_within_root("/etc/passwd", root)
