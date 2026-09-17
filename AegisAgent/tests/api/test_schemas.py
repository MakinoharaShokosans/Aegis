"""API DTO Schema 序列化与校验测试 (api/schemas.py)。"""

import pytest
from pydantic import ValidationError

from agent_runtime.api.schemas import (
    ApprovalRequestOut,
    ApproveRequest,
    RejectRequest,
    TaskOut,
    TaskSubmit,
    TimelineItem,
)


def test_approval_request_out_schema():
    """测试待审批请求 DTO 校验与字段赋值。"""
    req = ApprovalRequestOut(
        approval_id="appr_123456",
        required_level="full_permissions",
        current_level="workspace_write",
        action_type="network_egress",
        command="git push origin main",
        reason="操作超出工作区权限",
        escalation_count=1,
        related_actions=[],
    )
    data = req.model_dump()
    assert data["approval_id"] == "appr_123456"
    assert data["required_level"] == "full_permissions"
    assert data["action_type"] == "network_egress"

    # 非法权限级别触发校验失败
    with pytest.raises(ValidationError):
        ApprovalRequestOut(
            approval_id="appr_1",
            required_level="invalid_level",  # type: ignore[arg-type]
            current_level="workspace_write",
            action_type="network",
        )


def test_approve_request_schema():
    """测试批准请求 DTO 默认值与 decision 范围。"""
    # 1. 默认 decision 为 "once"
    req_default = ApproveRequest(approval_id="appr_1")
    assert req_default.decision == "once"

    # 2. 显式指定 "always"
    req_always = ApproveRequest(approval_id="appr_1", decision="always")
    assert req_always.decision == "always"

    # 3. 非法 decision
    with pytest.raises(ValidationError):
        ApproveRequest(decision="never")  # type: ignore[arg-type]


def test_reject_request_schema():
    """测试拒绝请求 DTO。"""
    req = RejectRequest(approval_id="appr_1", reason="禁止推送远端代码")
    assert req.reason == "禁止推送远端代码"
    assert req.approval_id == "appr_1"


def test_task_submit_schema():
    """测试任务提交请求 DTO。"""
    # 1. 默认不携带 permission_level
    sub1 = TaskSubmit(task_goal="定位 bug")
    assert sub1.permission_level is None

    # 2. 携带合法 permission_level
    sub2 = TaskSubmit(task_goal="查看代码", permission_level="read_only")
    assert sub2.permission_level == "read_only"

    # 3. 非法 permission_level
    with pytest.raises(ValidationError):
        TaskSubmit(task_goal="测试", permission_level="root_admin")  # type: ignore[arg-type]


def test_task_out_schema_with_waiting_for_approval():
    """测试 TaskOut 包含 waiting_for_approval 状态与 approval_request。"""
    approval_dto = ApprovalRequestOut(
        approval_id="appr_abc",
        required_level="full_permissions",
        current_level="workspace_write",
        action_type="network_egress",
        command="curl https://api.com",
    )
    task_out = TaskOut(
        task_id="task_999",
        session_id="sess_1",
        workspace_id="ws_1",
        task_goal="外联测试",
        status="waiting_for_approval",
        permission_level="workspace_write",
        approval_request=approval_dto,
        step_count=3,
        total_tokens=1500,
    )
    dumped = task_out.model_dump()
    assert dumped["status"] == "waiting_for_approval"
    assert dumped["approval_request"]["approval_id"] == "appr_abc"
    assert dumped["permission_level"] == "workspace_write"


def test_timeline_item_schema():
    """测试时间线条目支持 approval_request 类型。"""
    item = TimelineItem(
        seq=5,
        type="approval_request",
        role="assistant",
        summary="越级请求审批: git push",
        timestamp=1700000000.0,
    )
    assert item.type == "approval_request"
