"""``load_skill`` 基础工具：按需挂载专家技能 SOP（渐进式披露的第二阶段）。

设计意图：系统提示词只常驻"技能清单"（约 1000 Token），完整 SOP 只有在模型
主动调用本工具时才载入当前上下文，用完随 ExecutionContext 一起销毁，
避免把几十份 SOP 全量塞进提示词。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from loguru import logger

from agent_runtime.skills.registry import SkillsRegistry
from tools.core.protocol import AegisTool, ToolResult

__all__ = ["LoadSkillTool"]


class LoadSkillTool(AegisTool):
    """把指定技能的完整 SOP 与资源清单载入上下文。

    Args:
        registry: 技能注册表。
    """

    name = "load_skill"
    description = (
        "载入一份专家技能的完整操作规范（SOP）。当你判断当前任务属于某个已知领域"
        "（如内存泄漏排查、内核模块编译）时调用，以获得该领域的标准流程与避坑清单。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {"type": "string", "description": "技能名，须来自系统提示词中的技能清单"},
        },
        "required": ["skill_name"],
    }

    def __init__(self, registry: Optional[SkillsRegistry] = None) -> None:
        self._registry = registry
        self.timeout_sec = 10.0

    async def invoke(self, args: Mapping[str, Any]) -> ToolResult:
        """读取技能包内容。

        Args:
            args: ``{"skill_name": str}``。

        Returns:
            :class:`ToolResult`；技能不存在时返回失败结果（引导模型改用清单内的名字）。
        """
        skill_name = str(args.get("skill_name", "")).strip()
        if not skill_name:
            return ToolResult.failure("缺少 skill_name 参数")
        if self._registry is None:
            return ToolResult.failure("技能系统未启用")

        package = self._registry.get_skill(skill_name)
        if package is None:
            available = ", ".join(skill.name for skill in self._registry.list_skills()) or "（无）"
            return ToolResult.failure(f"未找到名为 {skill_name!r} 的专家技能。可用技能: {available}")

        logger.info(f"[LoadSkillTool] 已挂载技能 {skill_name}（来源 {package.metadata.source}）")
        sections = [f"# 已成功挂载专家技能: {package.metadata.name}", "", package.sop_content.strip()]
        if package.scripts:
            sections += ["", "## 可用辅助脚本", *[f"- {path}" for path in package.scripts]]
        if package.references:
            sections += ["", "## 参考资料", *[f"- {path}" for path in package.references]]
        if package.resources:
            sections += ["", "## 资源文件", *[f"- {path}" for path in package.resources]]

        return ToolResult(
            ok=True,
            content="\n".join(sections),
            meta={"skill": package.metadata.name, "source": package.metadata.source},
        )
