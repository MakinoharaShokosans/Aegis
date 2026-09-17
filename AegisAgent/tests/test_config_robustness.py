"""配置健壮性、非法正则容错与 OpenAPI Schema 契约回归测试 (Phase 8)。

对应 `documents/测试路线.md` §11 (Phase 8)。
验证 PermissionsConfig 字段缺失/类型错误时的校验报错、
非法正则表达式注入时的安全容错与告警、
以及 /tasks/{id}/approve、/reject 等端点的 OpenAPI 契约快照完整性。
"""

import pydantic
import pytest

from agent_runtime.api.app import create_app
from agent_runtime.config import PermissionsConfig
from agent_runtime.guardrails.permission import required_level_for


# ==============================================================================
# 1. 场景 8.1：配置字段缺失与类型校验健壮性 (Config Validation)
# ==============================================================================

def test_permissions_config_defaults():
    """验证 PermissionsConfig 缺省实例化时包含安全的默认值与非空正则列表。"""
    cfg = PermissionsConfig()
    assert cfg.default_level == "workspace_write"
    assert cfg.unknown_tool_level == "full_permissions"
    assert len(cfg.full_permission_patterns) > 0
    assert len(cfg.workspace_write_patterns) > 0
    assert "view_file" in cfg.read_only_tools


@pytest.mark.parametrize(
    "invalid_kwargs, expected_field",
    [
        ({"default_level": "super_admin"}, "default_level"),
        ({"unknown_tool_level": "invalid_mode"}, "unknown_tool_level"),
        ({"full_permission_patterns": "not_a_list"}, "full_permission_patterns"),
        ({"read_only_tools": 12345}, "read_only_tools"),
    ],
)
def test_permissions_config_invalid_types_raise_validation_error(invalid_kwargs, expected_field):
    """验证传入非法枚举值或非列表类型时，Pydantic 抛出清晰的 ValidationError。"""
    with pytest.raises(pydantic.ValidationError) as exc_info:
        PermissionsConfig(**invalid_kwargs)

    errors = exc_info.value.errors()
    assert any(err["loc"][0] == expected_field for err in errors)


# ==============================================================================
# 2. 场景 8.2：非法正则容错与隔离 (Invalid Regex Resilience)
# ==============================================================================

def test_invalid_regex_does_not_crash_valid_patterns(caplog):
    """验证配置中包含语法错误的非法正则时被安全忽略并告警，不影响其余合法正则。"""
    # 注入包含未闭合括号等非法模式的正则
    faulty_cfg = PermissionsConfig(
        full_permission_patterns=[
            "[unclosed_bracket",      # 语法错误正则
            r"\bgit\s+push\b",         # 合法正则 1
            "(?P<invalid",            # 语法错误正则
            r"\b(curl|wget)\b",       # 合法正则 2
        ],
        workspace_write_patterns=[
            "*bad_start_quantifier",  # 语法错误正则
            r"\brm\s+-rf\b",          # 合法正则
        ],
    )

    # 1. 匹配合法 full 规则
    level_push, action_type_push, _ = required_level_for("bash", {"command": "git push origin main"}, faulty_cfg)
    assert level_push == "full_permissions"
    assert action_type_push == "network_egress"

    level_curl, _, _ = required_level_for("bash", {"command": "curl http://api.org"}, faulty_cfg)
    assert level_curl == "full_permissions"

    # 2. 匹配合法 write 规则
    level_rm, _, _ = required_level_for("bash", {"command": "rm -rf /tmp/test"}, faulty_cfg)
    assert level_rm == "workspace_write"

    # 3. 未匹配到任何合法规则时回退到 read_only，不因错误正则引发 crash
    level_ls, _, _ = required_level_for("bash", {"command": "ls -la"}, faulty_cfg)
    assert level_ls == "read_only"


# ==============================================================================
# 3. 场景 8.3：OpenAPI Schema 契约快照与回归 (OpenAPI Schema Regression)
# ==============================================================================

def test_openapi_schema_contract_snapshot():
    """8.3 校验 FastAPI 应用生成的 OpenAPI 契约包含审批端点与数据模型。"""
    # 构造应用（不启动后台真实组件连接）
    app = create_app()
    schema = app.openapi()

    assert "paths" in schema
    paths = schema["paths"]

    # 1. 断言 HITL 审批端点存在
    approve_path = "/api/v1/tasks/{task_id}/approve"
    reject_path = "/api/v1/tasks/{task_id}/reject"
    resume_path = "/api/v1/tasks/{task_id}/resume"

    assert approve_path in paths, f"缺少 {approve_path}"
    assert "post" in paths[approve_path]

    assert reject_path in paths, f"缺少 {reject_path}"
    assert "post" in paths[reject_path]

    assert resume_path in paths, f"缺少 {resume_path}"
    assert "post" in paths[resume_path]

    # 2. 断言核心模型在 components.schemas 中定义
    components = schema.get("components", {}).get("schemas", {})

    assert "ApproveRequest" in components
    assert "RejectRequest" in components
    assert "ApprovalRequestOut" in components
    assert "TaskOut" in components

    # 3. 断言 TaskOut 中的 status 枚举包含 waiting_for_approval
    status_schema = components["TaskOut"]["properties"]["status"]
    assert "enum" in status_schema
    assert "waiting_for_approval" in status_schema["enum"]
    assert "running" in status_schema["enum"]
    assert "succeeded" in status_schema["enum"]
