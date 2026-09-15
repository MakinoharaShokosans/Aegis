"""LoopDetector 纯函数单元测试。"""

import pytest
from agent_runtime.guardrails.loop_detector import (
    compute_fingerprint,
    register_fingerprints,
    is_fingerprint_loop,
    is_failure_observation,
    update_consecutive_errors,
    build_replan_notice,
)


def test_compute_fingerprint_consistency():
    """测试不同键顺序的相同入参生成一致的确定性 MD5 指纹。"""
    fp1 = compute_fingerprint("bash", {"command": "ls -l", "timeout": 10})
    fp2 = compute_fingerprint("bash", {"timeout": 10, "command": "ls -l"})
    assert fp1 == fp2
    assert len(fp1) == 32

    # 不同入参生成不同指纹
    fp3 = compute_fingerprint("bash", {"command": "ls -a", "timeout": 10})
    assert fp1 != fp3


def test_register_fingerprints_sliding_window():
    """测试指纹队列追加与窗口保留。"""
    history = []
    calls1 = [("bash", {"command": "make"})]
    history = register_fingerprints(history, calls1, keep_last=3)
    assert len(history) == 1

    calls2 = [("bash", {"command": "make test"})]
    calls3 = [("bash", {"command": "make clean"})]
    calls4 = [("bash", {"command": "make all"})]
    history = register_fingerprints(history, calls2, keep_last=3)
    history = register_fingerprints(history, calls3, keep_last=3)
    history = register_fingerprints(history, calls4, keep_last=3)

    # 保留最近 3 条
    assert len(history) == 3
    assert history[-1] == compute_fingerprint("bash", {"command": "make all"})


def test_is_fingerprint_loop():
    """测试参数指纹死循环判定。"""
    same_fp = compute_fingerprint("bash", {"command": "cat /tmp/test"})
    diff_fp = compute_fingerprint("bash", {"command": "cat /tmp/other"})

    # 连续 3 次相同
    history_loop = [diff_fp, same_fp, same_fp, same_fp]
    assert is_fingerprint_loop(history_loop, limit=3) is True
    assert is_fingerprint_loop(history_loop, limit=4) is False

    # 未达到连续相同
    history_no_loop = [same_fp, diff_fp, same_fp]
    assert is_fingerprint_loop(history_no_loop, limit=3) is False

    # 历史长度小于阈值
    assert is_fingerprint_loop([same_fp, same_fp], limit=3) is False


def test_is_failure_observation():
    """测试观察值失败特征识别。"""
    assert is_failure_observation("fatal: cannot open file") is True
    assert is_failure_observation("Compilation error: undefined reference to main") is True
    assert is_failure_observation("segmentation fault (core dumped)") is True
    assert is_failure_observation("Build succeeded in 0.45s") is False
    assert is_failure_observation("OK, all 12 tests passed.") is False


def test_update_consecutive_errors():
    """测试连续错误计数器更新与清零。"""
    count = 0
    # 失败时累加
    count = update_consecutive_errors(count, failure_count=1)
    assert count == 1
    count = update_consecutive_errors(count, failure_count=1)
    assert count == 2

    # 成功 (failure_count=0) 时直接清零
    count = update_consecutive_errors(count, failure_count=0)
    assert count == 0


def test_build_replan_notice():
    """测试重规划通知文本生成。"""
    notice_loop = build_replan_notice(
        consecutive_errors=1,
        loop_detected=True,
        limit=3,
    )
    assert "完全相同" in notice_loop

    notice_err = build_replan_notice(
        consecutive_errors=3,
        loop_detected=False,
        limit=3,
    )
    assert "连续 3 次返回失败" in notice_err
