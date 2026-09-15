"""
Aegis 记忆子系统端到端自动化单元与集成测试 (test_memory.py)

覆盖范畴：
1. 数据模型与去重校验 (CompressedMemory / WorkspaceMemory / Workspace)；
2. SQLite 存储引擎底层工作区 CRUD、路径反查与外键约束；
3. 多工作区管理与一工作区多会话 (1:N 级联从属与会话列表筛选)；
4. 跨工作区强隔离与工作区级联物理清理 (ON DELETE CASCADE)；
5. 对话完整性对齐切片算法 (Turn-Aligned Slicing)；
6. 认知记忆增量合并与 LLM 故障优雅降级；
7. 基于 80% 高水位触发线与 40% 目标切片的动态记忆压缩；
8. 跨会话 Workspace 长期共享记忆与避坑禁区传递。
"""

import pytest
from pathlib import Path

from agent_runtime.memory.models import (
    TurnRecord,
    FailedAttempt,
    CompressedMemory,
    Workspace,
    WorkspaceMemory,
    SessionMetadata,
)
from agent_runtime.memory.sqlite_store import SqliteMemoryStore
from agent_runtime.memory.compactor import MemoryCompactor, select_turns_for_compaction
from agent_runtime.memory.manager import MemoryManager


@pytest.mark.asyncio
async def test_models_and_deduplication():
    """测试数据模型及事实去重功能"""
    # 1. 测试 CompressedMemory 去重
    mem = CompressedMemory(
        summary="初始背景摘要",
        confirmed_facts=["GCC 版本 11.2", "  GCC 版本 11.2  ", "glibc 2.31"],
        failed_attempts=[
            FailedAttempt(
                action="添加 -O3 编译标志",
                failure_reason="未定义符号引用",
                conclusion="该模块不可使用 O3 优化",
            )
        ],
        last_action_target={"files": ["src/main.c"]},
    )
    mem.deduplicate_facts()
    assert len(mem.confirmed_facts) == 2
    assert "GCC 版本 11.2" in mem.confirmed_facts
    assert "glibc 2.31" in mem.confirmed_facts

    json_str = mem.model_dump_json()
    loaded = CompressedMemory.model_validate_json(json_str)
    assert loaded.summary == "初始背景摘要"
    assert loaded.failed_attempts[0].conclusion == "该模块不可使用 O3 优化"

    # 2. 测试 WorkspaceMemory 去重
    ws_mem = WorkspaceMemory(
        workspace_id="ws_test",
        project_conventions=["使用 PEP8 规范", " 使用 PEP8 规范 ", "禁止硬编码路径"],
        confirmed_architecture=["SQLite WAL 模式", "SQLite WAL 模式"],
        global_failed_attempts=[],
    )
    ws_mem.deduplicate()
    assert len(ws_mem.project_conventions) == 2
    assert len(ws_mem.confirmed_architecture) == 1
    assert "禁止硬编码路径" in ws_mem.project_conventions

    # 3. 测试 Workspace 实体模型
    ws = Workspace(
        workspace_id="ws_main",
        name="Aegis Engine",
        root_path="/home/user/aegis",
        description="Core Agent System",
    )
    assert ws.workspace_id == "ws_main"
    assert ws.root_path == "/home/user/aegis"


@pytest.mark.asyncio
async def test_sqlite_store_crud(tmp_path: Path):
    """测试 SQLite 存储引擎的表初始化与增删查改"""
    db_file = tmp_path / "test_meta.db"
    store = SqliteMemoryStore(db_file)
    await store.initialize()

    # 1. 工作区创建与获取
    ws = await store.create_or_get_workspace("ws_001", "测试工作区", str(tmp_path / "proj_001"), "描述")
    assert ws.workspace_id == "ws_001"
    assert ws.name == "测试工作区"

    # 2. 会话创建与获取
    session = await store.create_or_get_session("sess_001", workspace_id="ws_001", title="测试会话")
    assert session.session_id == "sess_001"
    assert session.workspace_id == "ws_001"
    assert session.title == "测试会话"

    # 3. 追加对话轮次 (含 token 计数)
    t1 = await store.add_turn("sess_001", "user", "请排查内存泄露", token_count=100)
    t2 = await store.add_turn("sess_001", "assistant", "已定位到 connection.c 第 45 行", token_count=150)
    t3 = await store.add_turn("sess_001", "user", "请帮我写单测", token_count=80)
    t4 = await store.add_turn("sess_001", "assistant", "单测已生成至 test_conn.c", token_count=120)

    # 4. 统计活跃 Token 总和
    active_tokens = await store.get_active_turns_token_sum("sess_001")
    assert active_tokens == 450

    # 5. 滑窗查询 (取最近 2 轮，验证时间正序)
    recent = await store.get_recent_turns("sess_001", limit=2)
    assert len(recent) == 2
    assert recent[0].content == "请帮我写单测"
    assert recent[1].content == "单测已生成至 test_conn.c"

    # 6. 总数统计
    total = await store.get_total_turns_count("sess_001")
    assert total == 4

    # 7. 会话压缩记忆存取与水位指针推进
    mem = CompressedMemory(
        compacted_until_turn_id=t2.id or 2,
        summary="已修复 connection.c 泄漏",
        confirmed_facts=["系统使用 C99 编译"],
    )
    await store.save_compressed_memory("sess_001", mem)
    loaded_mem = await store.get_compressed_memory("sess_001")
    assert loaded_mem.compacted_until_turn_id == (t2.id or 2)
    assert loaded_mem.summary == "已修复 connection.c 泄漏"
    assert "系统使用 C99 编译" in loaded_mem.confirmed_facts

    # 8. 水位线推进后验证 get_active_turns
    active_turns_after = await store.get_active_turns("sess_001")
    assert len(active_turns_after) == 2
    assert active_turns_after[0].content == "请帮我写单测"
    assert active_turns_after[1].content == "单测已生成至 test_conn.c"

    # 9. 工作区共享记忆持久化与读取
    ws_init = await store.get_workspace_memory("ws_001")
    assert ws_init.workspace_id == "ws_001"
    ws_init.project_conventions.append("所有 SQL 必须参数化")
    await store.save_workspace_memory(ws_init)

    ws_loaded = await store.get_workspace_memory("ws_001")
    assert "所有 SQL 必须参数化" in ws_loaded.project_conventions


@pytest.mark.asyncio
async def test_multi_workspace_and_sessions_filtering(tmp_path: Path):
    """测试多工作区管理与一个工作区挂载多个会话的隔离与筛选"""
    db_file = tmp_path / "multi_ws.db"
    store = SqliteMemoryStore(db_file)
    manager = MemoryManager(store=store)
    await manager.initialize()

    # 1. 创建两个独立工作区
    path_a = str((tmp_path / "project_alpha").resolve())
    path_b = str((tmp_path / "project_beta").resolve())
    ws_a = await manager.create_workspace("Alpha项目", path_a, "Alpha 微服务")
    ws_b = await manager.create_workspace("Beta项目", path_b, "Beta 前端")

    assert ws_a.workspace_id != ws_b.workspace_id

    # 2. 路径反查
    found_a = await manager.get_workspace_by_path(path_a)
    assert found_a is not None
    assert found_a.workspace_id == ws_a.workspace_id
    assert found_a.name == "Alpha项目"

    # 3. 枚举工作区列表
    all_ws = await manager.list_workspaces()
    assert len(all_ws) == 2

    # 4. 在工作区 A 下开辟 3 个会话，在工作区 B 下开辟 2 个会话
    s_a1 = await manager.create_session(workspace_id=ws_a.workspace_id, title="Alpha重构网络库")
    s_a2 = await manager.create_session(workspace_id=ws_a.workspace_id, title="Alpha编写单测")
    s_a3 = await manager.create_session(workspace_id=ws_a.workspace_id, title="Alpha修复内存泄漏")

    s_b1 = await manager.create_session(workspace_id=ws_b.workspace_id, title="Beta页面适配")
    s_b2 = await manager.create_session(workspace_id=ws_b.workspace_id, title="Beta性能优化")

    # 5. 按工作区筛选会话 (1:N 验证)
    sessions_a = await manager.list_sessions(ws_a.workspace_id)
    assert len(sessions_a) == 3
    titles_a = [s.title for s in sessions_a]
    assert "Alpha重构网络库" in titles_a
    assert "Alpha编写单测" in titles_a
    assert "Alpha修复内存泄漏" in titles_a

    sessions_b = await manager.list_sessions(ws_b.workspace_id)
    assert len(sessions_b) == 2
    titles_b = [s.title for s in sessions_b]
    assert "Beta页面适配" in titles_b
    assert "Beta性能优化" in titles_b

    # 6. 单会话删除验证 (仅删除指定会话，不影响同工作区其他会话)
    del_ok = await manager.delete_session(s_a1.session_id)
    assert del_ok is True
    sessions_a_after = await manager.list_sessions(ws_a.workspace_id)
    assert len(sessions_a_after) == 2
    assert s_a1.session_id not in [s.session_id for s in sessions_a_after]


@pytest.mark.asyncio
async def test_workspace_cascade_deletion(tmp_path: Path):
    """测试工作区级联删除功能 (删除工作区自动级联清理下属会话、流水与记忆)"""
    db_file = tmp_path / "cascade_del.db"
    store = SqliteMemoryStore(db_file)
    manager = MemoryManager(store=store)
    await manager.initialize()

    # 创建工作区并填充会话与数据
    ws = await manager.create_workspace("待删除项目", str(tmp_path / "to_delete"), "临时仓库")
    s1 = await manager.create_session(ws.workspace_id, title="会话1")
    await store.add_turn(s1.session_id, "user", "问题A", 50)
    await store.add_turn(s1.session_id, "assistant", "回答A", 60)

    # 写入工作区记忆与会话记忆
    await manager.promote_fact_to_workspace(ws.workspace_id, "待删除事实", "architecture")
    await store.save_compressed_memory(s1.session_id, CompressedMemory(summary="临时摘要"))

    # 确认数据已入库
    assert len(await manager.list_sessions(ws.workspace_id)) == 1
    assert len((await manager.get_workspace_memory(ws.workspace_id)).confirmed_architecture) == 1
    assert await store.get_total_turns_count(s1.session_id) == 2

    # 执行工作区级联删除
    deleted = await manager.delete_workspace(ws.workspace_id)
    assert deleted is True

    # 验证级联清理效果
    assert await manager.get_workspace(ws.workspace_id) is None
    assert len(await manager.list_sessions(ws.workspace_id)) == 0
    assert await store.get_total_turns_count(s1.session_id) == 0
    mem_after = await store.get_compressed_memory(s1.session_id)
    assert mem_after.summary == ""


def test_select_turns_for_compaction_alignment():
    """测试对话完整性对齐切片算法 (Turn-Aligned Slicing)"""
    turns = [
        TurnRecord(id=1, session_id="s1", role="user", content="问1", token_count=50),
        TurnRecord(id=2, session_id="s1", role="assistant", content="答1", token_count=50),
        TurnRecord(id=3, session_id="s1", role="user", content="问2", token_count=60),
        TurnRecord(id=4, session_id="s1", role="assistant", content="答2", token_count=60),
        TurnRecord(id=5, session_id="s1", role="user", content="问3", token_count=70),
        TurnRecord(id=6, session_id="s1", role="assistant", content="答3", token_count=70),
    ]

    # 场景 1: target_compact_tokens = 90
    overflow, remaining = select_turns_for_compaction(turns, target_compact_tokens=90)
    assert len(overflow) == 2
    assert [t.id for t in overflow] == [1, 2]
    assert [t.id for t in remaining] == [3, 4, 5, 6]
    assert overflow[-1].role == "assistant"
    assert remaining[0].role == "user"

    # 场景 2: target_compact_tokens = 150
    overflow2, remaining2 = select_turns_for_compaction(turns, target_compact_tokens=150)
    assert len(overflow2) == 4
    assert [t.id for t in overflow2] == [1, 2, 3, 4]
    assert [t.id for t in remaining2] == [5, 6]
    assert overflow2[-1].role == "assistant"
    assert remaining2[0].role == "user"

    # 场景 3: 空输入保底
    o_empty, r_empty = select_turns_for_compaction([], target_compact_tokens=100)
    assert o_empty == []
    assert r_empty == []


@pytest.mark.asyncio
async def test_compactor_merge_and_degradation():
    """测试滚动压缩器的提炼合并与优雅降级"""
    async def mock_success_llm(sys_prompt: str, user_content: str) -> str:
        return """
        {
            "summary": "更新后的全量技术摘要",
            "confirmed_facts": ["Linux 6.1 内核", "CMake 3.22"],
            "failed_attempts": [
                {
                    "action": "使用 tcmalloc 链接",
                    "failure_reason": "段错误",
                    "conclusion": "当前系统环境 tcmalloc 不兼容"
                }
            ]
        }
        """

    compactor = MemoryCompactor(llm_invoker=mock_success_llm)
    prior = CompressedMemory(
        summary="旧摘要",
        confirmed_facts=["Linux 6.1 内核"],
    )
    overflow = [
        TurnRecord(id=1, session_id="s1", role="user", content="测试", token_count=20),
        TurnRecord(id=2, session_id="s1", role="assistant", content="回答", token_count=30),
    ]

    new_mem = await compactor.compact(prior, overflow)
    assert new_mem.summary == "更新后的全量技术摘要"
    assert len(new_mem.confirmed_facts) == 2
    assert len(new_mem.failed_attempts) == 1

    # 模拟 LLM 超时或抛出异常，验证降级
    async def mock_failing_llm(sys_prompt: str, user_content: str) -> str:
        raise TimeoutError("LLM API 连接超时")

    failing_compactor = MemoryCompactor(llm_invoker=mock_failing_llm)
    safe_mem = await failing_compactor.compact(prior, overflow)
    assert safe_mem.summary == "旧摘要"
    assert len(safe_mem.confirmed_facts) == 1


@pytest.mark.asyncio
async def test_memory_manager_watermark_compaction(tmp_path: Path):
    """测试 MemoryManager 基于 80% 高水位触发线和 40% 目标切片的端到端动态压缩"""
    db_file = tmp_path / "watermark_test.db"
    store = SqliteMemoryStore(db_file)

    compaction_called_count = 0

    async def mock_compactor_llm(sys_prompt: str, user_content: str) -> str:
        nonlocal compaction_called_count
        compaction_called_count += 1
        return """
        {
            "summary": "这是触达80%高水位后自动压缩提炼的全景认知",
            "confirmed_facts": ["系统主模块运行正常"],
            "failed_attempts": []
        }
        """

    compactor = MemoryCompactor(llm_invoker=mock_compactor_llm)

    # 设定：单会话上限 1000 Token，80% 高水位触发 (800 Token)，目标切除 40% (400 Token)
    manager = MemoryManager(
        store=store,
        compactor=compactor,
        session_token_limit=1000,
        compaction_high_watermark=0.80,
        compaction_ratio=0.40,
        active_window_turns=2,
    )
    await manager.initialize()

    sid = "sess_watermark_01"

    # 第 1 轮对话：生成约 300 Token (未达 800 水位，不触发压缩)
    q1 = "排查问题 " * 35
    a1 = "排查结论 " * 40
    await manager.record_turn_and_maybe_compact(
        session_id=sid,
        user_query=q1,
        agent_delivery=a1,
    )
    assert compaction_called_count == 0
    _, _, mem1, active1 = await manager.load_session_context(sid)
    assert mem1.summary == ""
    assert len(active1) == 2

    # 第 2 轮对话：再累积约 300 Token (总计约 600 Token，仍未达 800，不触发压缩)
    q2 = "继续分析 " * 35
    a2 = "分析反馈 " * 40
    await manager.record_turn_and_maybe_compact(
        session_id=sid,
        user_query=q2,
        agent_delivery=a2,
    )
    assert compaction_called_count == 0

    # 第 3 轮对话：再累积约 300 Token (总计将突破 900 Token >= 800 阈值，触发压缩！)
    q3 = "执行重构 " * 35
    a3 = "重构完成 " * 40
    await manager.record_turn_and_maybe_compact(
        session_id=sid,
        user_query=q3,
        agent_delivery=a3,
        last_action_target={"files": ["module_a.py"]},
    )

    # 验证压缩被且仅被触发 1 次
    assert compaction_called_count == 1

    # 验证压缩后的会话状态与低水位恢复
    _, _, mem3, active3 = await manager.load_session_context(sid)
    assert mem3.summary == "这是触达80%高水位后自动压缩提炼的全景认知"
    assert "系统主模块运行正常" in mem3.confirmed_facts
    assert mem3.last_action_target == {"files": ["module_a.py"]}
    assert mem3.compacted_until_turn_id > 0

    # 验证活跃轮数被安全切分并减少，剩余活跃轮次正序排列
    assert len(active3) < 6
    assert active3[-1].content.startswith("重构完成")


@pytest.mark.asyncio
async def test_workspace_cross_session_sharing_and_isolation(tmp_path: Path):
    """测试同工作区跨会话即时共享，以及不同工作区之间的严格认知隔离"""
    db_file = tmp_path / "workspace_share.db"
    store = SqliteMemoryStore(db_file)
    manager = MemoryManager(store=store)
    await manager.initialize()

    ws_alpha = "ws_team_alpha"
    ws_beta = "ws_team_beta"

    # 工作区 Alpha: 沉淀规范、架构定论与踩坑禁区
    await manager.promote_fact_to_workspace(
        workspace_id=ws_alpha,
        fact="系统统一采用 uv 进行 Python 依赖管理",
        category="convention",
    )
    await manager.promote_fact_to_workspace(
        workspace_id=ws_alpha,
        fact="Agent 与 RAG 处于物理独立微服务架构",
        category="architecture",
    )
    await manager.record_global_failure(
        workspace_id=ws_alpha,
        failed_attempt=FailedAttempt(
            action="在 Agent 进程直接 import tree-sitter",
            failure_reason="动态库符号冲突与跨模块内存暴涨",
            conclusion="语法解析严禁直接进入 Agent，必须委托 RAG 微服务调用",
        ),
    )

    # 会话 Alpha-2 (同在工作区 Alpha 的新会话): 读取上下文
    _, ws_mem_a2, session_mem_a2, active_a2 = await manager.load_session_context(
        session_id="session_alpha_02",
        workspace_id=ws_alpha,
    )

    # 验证同工作区无缝继承资产
    assert "系统统一采用 uv 进行 Python 依赖管理" in ws_mem_a2.project_conventions
    assert "Agent 与 RAG 处于物理独立微服务架构" in ws_mem_a2.confirmed_architecture
    assert len(ws_mem_a2.global_failed_attempts) == 1
    assert "语法解析严禁直接进入 Agent" in ws_mem_a2.global_failed_attempts[0].conclusion
    assert session_mem_a2.summary == ""
    assert len(active_a2) == 0

    # 会话 Beta-1 (处于工作区 Beta 的会话): 读取上下文
    _, ws_mem_b1, session_mem_b1, active_b1 = await manager.load_session_context(
        session_id="session_beta_01",
        workspace_id=ws_beta,
    )

    # 验证跨工作区严格隔离 (Beta 绝对感知不到 Alpha 的规范与事实)
    assert "系统统一采用 uv 进行 Python 依赖管理" not in ws_mem_b1.project_conventions
    assert "Agent 与 RAG 处于物理独立微服务架构" not in ws_mem_b1.confirmed_architecture
    assert len(ws_mem_b1.global_failed_attempts) == 0
