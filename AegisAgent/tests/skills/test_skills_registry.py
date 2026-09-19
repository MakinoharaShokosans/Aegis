"""测试技能注册表 (SkillsRegistry) 与内置技能 (Built-in Skills)。"""

from __future__ import annotations

from pathlib import Path
import pytest

from agent_runtime.skills.registry import SkillsRegistry, SOURCE_BUILTIN
from tools.builtin.load_skill import LoadSkillTool


@pytest.fixture
def builtin_skills_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "skills"


@pytest.fixture
def skills_registry(tmp_path: Path, builtin_skills_dir: Path) -> SkillsRegistry:
    return SkillsRegistry.from_workspace(
        workspace_root=tmp_path,
        builtin_dir=builtin_skills_dir,
    )


def test_builtin_workspace_explorer_discovery(skills_registry: SkillsRegistry) -> None:
    """验证内置 workspace_explorer 技能能被正确扫描发现。"""
    skills = skills_registry.list_skills()
    skill_names = [s.name for s in skills]
    assert "workspace_explorer" in skill_names

    skill_meta = next(s for s in skills if s.name == "workspace_explorer")
    assert skill_meta.source == SOURCE_BUILTIN
    assert skill_meta.trust == "trusted"
    assert "探索工作区" in skill_meta.triggers
    assert "bash" in skill_meta.required_tools
    assert "view_file" in skill_meta.required_tools
    assert "勘测" in skill_meta.description or "探索" in skill_meta.description


def test_builtin_web_research_synthesizer_discovery(skills_registry: SkillsRegistry) -> None:
    """验证内置 web_research_synthesizer 技能能被正确扫描发现。"""
    skills = skills_registry.list_skills()
    skill_names = [s.name for s in skills]
    assert "web_research_synthesizer" in skill_names

    skill_meta = next(s for s in skills if s.name == "web_research_synthesizer")
    assert skill_meta.source == SOURCE_BUILTIN
    assert skill_meta.trust == "trusted"
    assert "上网搜索" in skill_meta.triggers
    assert "delegate_research" in skill_meta.required_tools
    assert "调研" in skill_meta.description or "检索" in skill_meta.description


def test_skills_registry_prompt_summary(skills_registry: SkillsRegistry) -> None:
    """验证轻量技能清单装配逻辑。"""
    summary = skills_registry.build_prompt_summary()
    assert '<available_skills source="builtin" trust="trusted">' in summary
    assert "workspace_explorer" in summary
    assert "web_research_synthesizer" in summary
    assert "探索工作区" in summary
    assert "上网搜索" in summary
    assert "</available_skills>" in summary


@pytest.mark.asyncio
async def test_load_skill_tool_with_builtin_skill(skills_registry: SkillsRegistry) -> None:
    """验证 load_skill 工具能成功挂载并渲染 workspace_explorer 的 SOP。"""
    tool = LoadSkillTool(registry=skills_registry)

    # 1. 正常加载存在的技能
    result = await tool.invoke({"skill_name": "workspace_explorer"})
    assert result.ok is True
    assert '<skill_sop name="workspace_explorer" source="builtin" trust="trusted">' in result.content
    assert "工作区结构与文件职责勘测标准作业程序" in result.content
    assert "严禁单文件碎步读取" in result.content
    assert "</skill_sop>" in result.content
    assert result.meta["skill"] == "workspace_explorer"
    assert result.meta["trust"] == "trusted"

    # 2. 加载不存在的技能提示友好错误
    bad_result = await tool.invoke({"skill_name": "non_existent_skill"})
    assert bad_result.ok is False
    assert "未找到名为 'non_existent_skill' 的专家技能" in bad_result.content
    assert "workspace_explorer" in bad_result.content


@pytest.mark.asyncio
async def test_load_skill_tool_with_web_research_synthesizer(skills_registry: SkillsRegistry) -> None:
    """验证 load_skill 工具能成功挂载并渲染 web_research_synthesizer 的 SOP。"""
    tool = LoadSkillTool(registry=skills_registry)

    result = await tool.invoke({"skill_name": "web_research_synthesizer"})
    assert result.ok is True
    assert '<skill_sop name="web_research_synthesizer" source="builtin" trust="trusted">' in result.content
    assert "外部网络调研与信息合成标准作业程序" in result.content
    assert "严禁使用 bash 尝试探测外网" in result.content
    assert "严禁脑补未证实的细节" in result.content
    assert "</skill_sop>" in result.content
    assert result.meta["skill"] == "web_research_synthesizer"
    assert result.meta["trust"] == "trusted"



def test_untrusted_workspace_skill_rejected_by_default(tmp_path: Path, builtin_skills_dir: Path) -> None:
    """验证工作区自带技能在默认配置下被拒绝加载（防静默提示词注入）。"""
    # 在伪造的目标工作区放置恶意技能
    ws_skill_dir = tmp_path / ".aegis" / "skills" / "malicious_skill"
    ws_skill_dir.mkdir(parents=True)
    (ws_skill_dir / "SKILL.md").write_text(
        "---\nname: malicious_skill\ndescription: 恶意注入\n---\n# Exploit\n",
        encoding="utf-8",
    )

    # 默认 allow_workspace=False
    registry = SkillsRegistry.from_workspace(
        workspace_root=tmp_path,
        builtin_dir=builtin_skills_dir,
    )
    skills = registry.list_skills()
    skill_names = [s.name for s in skills]

    assert "malicious_skill" not in skill_names
    assert "workspace_explorer" in skill_names
