"""专家技能注册表：三档扫描 + 渐进式披露。

对应 ``documents/agent_runtime/08_skills_management.md``。

**核心概念区分**：
* **Tool（工具）** 回答"能做什么"（bash / rag_search / web_search）；
* **Skill（技能）** 回答"如何专业地做"—— 是一份领域 SOP 目录包。

**三档扫描优先级**（高优先级严格覆盖同名技能）::

    1. <workspace.root_path>/.aegis/skills/   工作区自带的项目级技能
    2. AegisAgent/src/skills/                 随发行版交付的内置技能
    3. ~/.aegis/skills/                       用户全局技能库

**渐进式披露**：系统提示词只注入"清单"（名称 + 一句话描述，总量约 1000 Token），
命中场景后由 Agent 调用 ``load_skill`` 载入完整 SOP，任务结束随上下文销毁。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from loguru import logger
from pydantic import BaseModel, Field

__all__ = ["SkillMetadata", "SkillPackage", "SkillsRegistry"]

#: 技能清单中单个技能允许占用的描述字符上限（控制提示词总量）
_DESCRIPTION_LIMIT = 120

#: 技能来源标签
SOURCE_WORKSPACE = "workspace"
SOURCE_BUILTIN = "builtin"
SOURCE_GLOBAL = "global"


class SkillMetadata(BaseModel):
    """技能元数据（来自 ``SKILL.md`` 的 YAML frontmatter）。"""

    name: str = Field(description="技能唯一名")
    description: str = Field(default="", description="一句话描述（注入提示词清单）")
    triggers: List[str] = Field(default_factory=list, description="触发场景关键词")
    required_tools: List[str] = Field(default_factory=list, description="依赖的工具名")
    skill_dir: str = Field(default="", description="技能包目录绝对路径")
    source: str = Field(default=SOURCE_BUILTIN, description="来源层级：workspace/builtin/global")


class SkillPackage(BaseModel):
    """完整技能包（按需加载时才读取 SOP 正文）。"""

    metadata: SkillMetadata = Field(description="技能元数据")
    sop_content: str = Field(default="", description="``SKILL.md`` 正文（去除 frontmatter）")
    scripts: List[str] = Field(default_factory=list, description="scripts/ 下的脚本相对路径")
    references: List[str] = Field(default_factory=list, description="references/ 下的资料相对路径")
    resources: List[str] = Field(default_factory=list, description="resources/ 下的资源相对路径")


def _split_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    """切分 ``SKILL.md`` 的 YAML frontmatter 与正文。

    Args:
        text: 文件全文。

    Returns:
        ``(frontmatter 字典, 正文)``。frontmatter 缺失或非法时返回 ``({}, 原文)``。
    """
    if not text.lstrip().startswith("---"):
        return {}, text

    stripped = text.lstrip()
    # 以第二个 '---' 作为 frontmatter 结束标记
    end = stripped.find("\n---", 3)
    if end == -1:
        return {}, text

    block = stripped[3:end].strip()
    body = stripped[end + 4 :].lstrip("\n")
    try:
        import yaml  # 局部导入：技能解析是低频路径，不拖慢冷启动

        parsed = yaml.safe_load(block) or {}
    except Exception as exc:  # noqa: BLE001 - 单个技能文件损坏不应影响整表扫描
        logger.warning(f"[Skills] frontmatter 解析失败，将按无元数据处理: {exc}")
        return {}, text

    return (parsed if isinstance(parsed, dict) else {}), body


class SkillsRegistry:
    """技能注册表。

    Args:
        roots: ``(目录, 来源标签)`` 序列，**顺序即优先级（高到低）**。
    """

    __slots__ = ("_roots", "_skills", "_scanned")

    def __init__(self, roots: Sequence[Tuple[Path, str]]) -> None:
        self._roots: List[Tuple[Path, str]] = [(Path(directory), source) for directory, source in roots]
        self._skills: Dict[str, SkillMetadata] = {}
        self._scanned = False

    @classmethod
    def from_workspace(
        cls,
        workspace_root: str | Path,
        builtin_dir: str | Path,
        global_dir: Optional[str | Path] = None,
    ) -> "SkillsRegistry":
        """按标准三档优先级构造注册表。

        Args:
            workspace_root: 目标工程根目录（工作区 ``root_path``）。
            builtin_dir: 内置技能目录（``AegisAgent/src/skills``）。
            global_dir: 用户全局技能目录，缺省为 ``~/.aegis/skills``。

        Returns:
            注册表实例。
        """
        global_path = Path(global_dir) if global_dir else Path.home() / ".aegis" / "skills"
        return cls(
            roots=[
                (Path(workspace_root) / ".aegis" / "skills", SOURCE_WORKSPACE),
                (Path(builtin_dir), SOURCE_BUILTIN),
                (global_path, SOURCE_GLOBAL),
            ]
        )

    def scan(self, *, force: bool = False) -> Dict[str, SkillMetadata]:
        """扫描全部根目录并建立索引。

        Args:
            force: 为 ``True`` 时忽略缓存重新扫描。

        Returns:
            ``技能名 -> 元数据`` 映射。
        """
        if self._scanned and not force:
            return dict(self._skills)

        discovered: Dict[str, SkillMetadata] = {}
        # 逆序遍历：低优先级先写入，高优先级后覆盖，天然实现"高覆盖低"
        for directory, source in reversed(self._roots):
            if not directory.is_dir():
                continue
            for skill_file in sorted(directory.glob("*/SKILL.md")):
                metadata = self._parse_metadata(skill_file, source)
                if metadata is None:
                    continue
                discovered[metadata.name] = metadata
                logger.debug(f"[Skills] 发现技能 {metadata.name}（来源 {source}）")

        self._skills = discovered
        self._scanned = True
        logger.info(f"[Skills] 技能扫描完成，共 {len(discovered)} 个")
        return dict(self._skills)

    def _parse_metadata(self, skill_file: Path, source: str) -> Optional[SkillMetadata]:
        """解析单个 ``SKILL.md`` 的元数据。"""
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(f"[Skills] 读取技能文件失败 {skill_file}: {exc}")
            return None

        front, _ = _split_frontmatter(text)
        name = str(front.get("name") or skill_file.parent.name).strip()
        if not name:
            logger.warning(f"[Skills] 技能缺少 name，已跳过: {skill_file}")
            return None

        return SkillMetadata(
            name=name,
            description=str(front.get("description") or "").strip(),
            triggers=[str(item) for item in front.get("triggers") or []],
            required_tools=[str(item) for item in front.get("required_tools") or []],
            skill_dir=str(skill_file.parent.resolve()),
            source=source,
        )

    def list_skills(self) -> List[SkillMetadata]:
        """列出全部技能元数据（按名称排序）。"""
        self.scan()
        return [self._skills[name] for name in sorted(self._skills)]

    def get_skill(self, name: str) -> Optional[SkillPackage]:
        """按需加载完整技能包（懒读取 SOP 正文与脚本清单）。

        Args:
            name: 技能名。

        Returns:
            技能包；不存在时返回 ``None``。
        """
        self.scan()
        metadata = self._skills.get(name)
        if metadata is None:
            return None

        skill_dir = Path(metadata.skill_dir)
        skill_file = skill_dir / "SKILL.md"
        try:
            _, body = _split_frontmatter(skill_file.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.error(f"[Skills] 读取技能正文失败 {skill_file}: {exc}")
            body = ""

        def _relative_files(subdir: str) -> List[str]:
            target = skill_dir / subdir
            if not target.is_dir():
                return []
            return sorted(str(path.relative_to(skill_dir)) for path in target.rglob("*") if path.is_file())

        return SkillPackage(
            metadata=metadata,
            sop_content=body,
            scripts=_relative_files("scripts"),
            references=_relative_files("references"),
            resources=_relative_files("resources"),
        )

    def build_prompt_summary(self) -> str:
        """装配注入系统提示词的"可用技能清单"。

        Returns:
            Markdown 清单文本；无技能时返回空串（调用方应跳过该段）。
        """
        skills = self.list_skills()
        if not skills:
            return ""

        lines = ["## 可用专家技能清单", "", "命中以下场景时，请调用 `load_skill` 载入对应 SOP：", ""]
        for skill in skills:
            description = skill.description[:_DESCRIPTION_LIMIT]
            trigger_hint = f"（触发：{'/'.join(skill.triggers)}）" if skill.triggers else ""
            lines.append(f"- **{skill.name}**：{description}{trigger_hint}")
        return "\n".join(lines)

    def __len__(self) -> int:
        self.scan()
        return len(self._skills)

    def __contains__(self, name: object) -> bool:
        self.scan()
        return name in self._skills
