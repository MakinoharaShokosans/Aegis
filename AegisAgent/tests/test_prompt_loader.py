"""提示词加载器 (PromptLibrary) 单元测试。"""

from pathlib import Path
import pytest

from agent_runtime.prompt_loader import PromptLibrary


def test_prompt_loader_from_builtin_prompts():
    """测试从内置目录加载提示词。"""
    lib = PromptLibrary()

    # planner.md 在项目中存在
    planner_prompt = lib.load("planner")
    assert len(planner_prompt) > 0
    assert "planner" in planner_prompt.lower() or "角色" in planner_prompt or "任务" in planner_prompt

    # 再次读取走缓存
    cached = lib.load("planner")
    assert cached == planner_prompt


def test_prompt_loader_missing_with_default(tmp_path: Path):
    """测试提示词文件缺失时安全返回默认文本。"""
    lib = PromptLibrary(prompts_dir=tmp_path)

    fallback = "DEFAULT FALLBACK PROMPT"
    loaded = lib.load("non_existent_role", default=fallback)
    assert loaded == fallback


def test_prompt_loader_custom_dir(tmp_path: Path):
    """测试指定自定义目录加载并验证缓存机制。"""
    prompt_file = tmp_path / "custom_agent.md"
    prompt_file.write_text("You are a custom assistant.", encoding="utf-8")

    lib = PromptLibrary(prompts_dir=tmp_path)
    loaded = lib.load("custom_agent")
    assert loaded == "You are a custom assistant."

    # 修改文件后，再次 load 应命中内存缓存
    prompt_file.write_text("Modified text.", encoding="utf-8")
    assert lib.load("custom_agent") == "You are a custom assistant."
