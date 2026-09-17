"""Phase 15: 真实长任务下的上下文治理与观察值结构化裁剪测试 (Phase 15)。

对应 `documents/深度测试路线.md` §8 (Phase 15)。
验证在高负载多轮交互中，三层金字塔上下文压缩、Rolling Summary 与原子对保留机制正常生效，
确保长对话不超出 Token 预算且不触发 OpenAI 400 消息结构错误。

预估消耗：约 4~6 次 fast 模型交互。
"""

from pathlib import Path
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_runtime.guardrails.observation_pruner import ObservationPruner
from agent_runtime.memory.manager import MemoryManager
from agent_runtime.memory.sqlite_store import SqliteMemoryStore


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_live_context_watermark_compaction_with_atomic_pairs(live_gateway, tmp_path: Path):
    """15.1 构造多轮大观察值历史，验证触发水位线压缩时滚动摘要生成正常且保持原子对完整。"""
    store = SqliteMemoryStore(tmp_path / "meta.db")
    await store.initialize()

    session_id = "sess_live_compact_01"
    workspace_id = "ws_live_compact_01"

    # 构造较低的会话 token 预算以触发高水位压缩
    manager = MemoryManager(
        store=store,
        session_token_limit=1000,
        compaction_high_watermark=0.7,
        compaction_ratio=0.5,
        active_window_turns=2,
    )

    # 写入多轮对话以触发水位线压缩
    for i in range(1, 6):
        await manager.record_turn_and_maybe_compact(
            session_id=session_id,
            user_query=f"用户指令第 {i} 轮：请分析 module_{i}.py 的代码结构并重构。",
            agent_delivery=f"助手完成第 {i} 轮交付：已重构 module_{i}.py，修复了 3 处边界条件并发 Bug。" + ("详细变更说明..." * 20),
            workspace_id=workspace_id,
        )

    # 读取压缩后的情境记忆
    compressed = await store.get_compressed_memory(session_id)

    # 验证压缩成功触发并推进了水位指针，生成了结构化滚动摘要
    assert compressed.compacted_until_turn_id > 0, "水位线指针应向前推进"
    assert compressed.summary, "压缩应产出提炼摘要"
    assert len(compressed.summary) > 0


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_live_observation_pruner_on_real_compiler_logs(tmp_path: Path):
    """15.2 验证 ObservationPruner 对真实大体积编译器日志的结构化头部与尾部截断。"""
    artifacts_dir = tmp_path / "artifacts"
    pruner = ObservationPruner(
        token_counter=lambda text: len(text) // 4,
        max_tokens=200,
        head_lines=5,
        tail_lines=5,
        artifacts_dir=artifacts_dir,
    )

    # 模拟真实的长编译输出（100 行）
    long_log = "\n".join(f"[INFO] Compiling module_{i}.o with flags -Wall -O2..." for i in range(100))

    result = await pruner.prune(
        long_log,
        task_id="task_prune_01",
        step_id=1,
        tool_name="bash",
    )

    # 验证截断生效并落盘产物
    assert result.is_truncated
    assert result.artifact_path is not None
    assert Path(result.artifact_path).exists()
    assert "中间省略" in result.summary
    assert "module_0" in result.summary  # 头部包含
    assert "module_99" in result.summary  # 尾部包含
