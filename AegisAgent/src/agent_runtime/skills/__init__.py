"""技能注册表（**代码侧**）。

注意与 ``AegisAgent/src/skills/``（**内容侧**，存放 ``SKILL.md`` 与脚本）区分：
本包只负责扫描、解析与清单装配，不存放任何技能内容。
"""

from agent_runtime.skills.registry import SkillMetadata, SkillPackage, SkillsRegistry

__all__ = ["SkillMetadata", "SkillPackage", "SkillsRegistry"]
