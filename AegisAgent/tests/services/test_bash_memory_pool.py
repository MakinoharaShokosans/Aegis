"""Bash Shell 并发与全局内存池 GlobalMemoryBudget 单元测试。"""

import asyncio
import pytest

from services.bash_shell.memory_pool import GlobalMemoryBudget


@pytest.mark.asyncio
async def test_memory_pool_basic_acquire_and_release():
    """测试配额与槽位的正常借用与归还。"""
    pool = GlobalMemoryBudget(
        total_mb=1000,
        max_concurrent=2,
        default_task_mb=200,
        default_task_sec=1.0,
    )

    assert pool.total_mb == 1000
    assert pool.max_concurrent == 2
    assert pool.available_mb == 1000
    assert pool.used_mb == 0

    # 1. 尝试非阻塞获取 400MB
    success = await pool.try_acquire(400)
    assert success is True
    assert pool.used_mb == 400
    assert pool.available_mb == 600

    # 2. 获取第 2 个槽位 500MB
    success = await pool.try_acquire(500)
    assert success is True
    assert pool.used_mb == 900
    assert pool.available_mb == 100

    # 3. 并发槽位已满 (max_concurrent=2)，第 3 次获取即便内存够也应该失败
    success = await pool.try_acquire(50)
    assert success is False

    # 4. 释放 400MB
    await pool.release(400, duration_sec=0.5)
    assert pool.used_mb == 500
    assert pool.available_mb == 500

    # 5. 槽位空出，可继续获取
    success = await pool.try_acquire(300)
    assert success is True
    assert pool.used_mb == 800

    # 全部归还
    await pool.release(500)
    await pool.release(300)
    assert pool.used_mb == 0
    assert pool.available_mb == 1000


@pytest.mark.asyncio
async def test_memory_pool_queue_and_wait():
    """测试内存超额时排队等待并在释放后被唤醒。"""
    pool = GlobalMemoryBudget(
        total_mb=500,
        max_concurrent=3,
        default_task_mb=100,
        default_task_sec=1.0,
    )

    # 占用 400MB
    await pool.acquire(400)
    assert pool.used_mb == 400

    # 此时想占用 200MB 超过 500MB，需等待
    acquired = False

    async def wait_task():
        nonlocal acquired
        await pool.acquire(200)
        acquired = True

    task = asyncio.create_task(wait_task())
    await asyncio.sleep(0.05)
    # 仍未获取到
    assert acquired is False
    assert pool.waiting == 1

    # 释放 300MB，应唤醒 task
    await pool.release(300)
    await asyncio.sleep(0.05)
    assert acquired is True
    assert pool.used_mb == 300  # 原 400 - 300 + 200 = 300

    await pool.release(100)
    await pool.release(200)
    assert pool.used_mb == 0
    await task


def test_memory_pool_invalid_inputs():
    """测试非法参数防御。"""
    with pytest.raises(ValueError, match="内存池总量必须为正"):
        GlobalMemoryBudget(total_mb=0, max_concurrent=1, default_task_mb=10, default_task_sec=1.0)

    with pytest.raises(ValueError, match="并发上限必须为正"):
        GlobalMemoryBudget(total_mb=100, max_concurrent=0, default_task_mb=10, default_task_sec=1.0)

    pool = GlobalMemoryBudget(total_mb=100, max_concurrent=1, default_task_mb=10, default_task_sec=1.0)
    with pytest.raises(ValueError, match="预估配额必须为正"):
        pool.normalize(0)
