"""ObservationPruner 单元测试。"""

import json
import pytest
from pathlib import Path

from agent_runtime.guardrails.observation_pruner import (
    ObservationPruner,
    json_outline,
    _preview_scalar,
)


def test_json_outline_structure():
    """测试 json_outline 保留键名与结构，截断超长标量。"""
    raw = {
        "status": "ok",
        "nested": {
            "key1": "short",
            "long_text": "a" * 200,
            "items": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        }
    }
    outline = json_outline(raw, max_depth=3)
    assert outline["status"] == "ok"
    assert outline["nested"]["key1"] == "short"
    assert outline["nested"]["long_text"].endswith("…")
    assert len(outline["nested"]["items"]) <= 6  # 截取前若干项并加摘要


@pytest.mark.asyncio
async def test_observation_pruner_short_text(tmp_path: Path):
    """测试短文本不截断且不触发落盘。"""
    pruner = ObservationPruner(
        token_counter=lambda s: len(s.split()),
        max_tokens=50,
        head_lines=5,
        tail_lines=5,
        artifacts_dir=tmp_path,
    )

    short_text = "Line 1\nLine 2\nLine 3"
    result = await pruner.prune(
        raw=short_text,
        task_id="task_test_1",
        step_id=1,
    )

    assert not result.is_truncated
    assert result.summary == short_text
    assert result.artifact_path is None


@pytest.mark.asyncio
async def test_observation_pruner_long_plain_text(tmp_path: Path):
    """测试超长纯文本触发 Head/Tail 裁剪与物理落盘。"""
    pruner = ObservationPruner(
        token_counter=lambda s: len(s.split()),
        max_tokens=20,
        head_lines=2,
        tail_lines=2,
        artifacts_dir=tmp_path,
    )

    lines = [f"Line {i} some text content here" for i in range(50)]
    long_text = "\n".join(lines)

    result = await pruner.prune(
        raw=long_text,
        task_id="task_test_2",
        step_id=2,
    )

    assert result.is_truncated
    assert "Line 0" in result.summary
    assert "Line 1" in result.summary
    assert "Line 49" in result.summary
    assert "中间省略" in result.summary
    assert result.artifact_path is not None

    # 验证物理文件确实落盘且内容完整
    saved_file = Path(result.artifact_path)
    assert saved_file.is_file()
    assert saved_file.read_text(encoding="utf-8") == long_text


@pytest.mark.asyncio
async def test_observation_pruner_long_json(tmp_path: Path):
    """测试超长 JSON 优先生成合法结构轮廓。"""
    pruner = ObservationPruner(
        token_counter=lambda s: len(s.split()),
        max_tokens=10,
        head_lines=2,
        tail_lines=2,
        artifacts_dir=tmp_path,
    )

    huge_data = {"user": "alice", "logs": [{"id": i, "data": "x" * 50} for i in range(20)]}
    json_str = json.dumps(huge_data)

    result = await pruner.prune(
        raw=json_str,
        task_id="task_test_3",
        step_id=3,
    )

    assert result.is_truncated
    # 验证轮廓提取生效
    assert "结构化输出轮廓" in result.summary
    assert "alice" in result.summary
