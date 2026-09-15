"""
Aegis 认知记忆滚动压缩与事实提炼器 (compactor.py)

功能描述：
1. 负责在会话历史轮次溢出活跃滑窗后，调用轻量快速模型 (models.fast) 进行增量压缩；
2. 提炼并合并全局背景摘要、已确认为真的客观事实与负向踩坑禁区；
3. 实现对话完整性对齐切片算法 (Turn-Aligned Slicing)：严格按完整人机对话对切分待压缩轮次，杜绝半句或断头截断；
4. 遵循非阻塞与优雅降级原则：LLM 网络超时或解析失败时绝不阻断主流程，安全回退至上一次记忆。
"""

import json
from pathlib import Path
from typing import Any, Callable, Coroutine, List, Optional, Tuple
from loguru import logger
from openai import AsyncOpenAI

from agent_runtime.config import get_config
from agent_runtime.memory.models import CompressedMemory, FailedAttempt, TurnRecord


def select_turns_for_compaction(
    active_turns: List[TurnRecord],
    target_compact_tokens: int,
) -> Tuple[List[TurnRecord], List[TurnRecord]]:
    """
    对话完整性对齐切片算法 (Turn-Aligned Slicing)
    
    业务原则：
        绝对不能在句子或单条消息中间截断，必须严格对齐到“完整的人机交互单元 (User 问 + Assistant 答)”边界。
        从最古老的轮次开始向前累加 Token，直到达到或超过 target_compact_tokens，
        并在其后的第一个完整的 assistant 节点对齐截断。
        
    Args:
        active_turns: 当前处于活跃状态的未压缩对话流水 (正序: 最早 -> 最新)
        target_compact_tokens: 目标需要被切出压缩的 Token 数量 (约占 40%)
        
    Returns:
        Tuple[List[TurnRecord], List[TurnRecord]]:
            - 第一个元素为切出的待压缩溢出轮次 (overflow_turns)
            - 第二个元素为保留在活跃窗口内的轮次 (remaining_turns)
    """
    if not active_turns:
        return [], []

    accumulated = 0
    cut_index = -1

    # 遍历对话流水，寻找最贴近 target 的完整 assistant 结束节点
    for i, turn in enumerate(active_turns):
        accumulated += max(turn.token_count, 1)

        # 当累积 Token 达到或超过目标，且当前是完整的 assistant 响应节点时对齐截断
        if turn.role == "assistant" and accumulated >= target_compact_tokens:
            cut_index = i
            break

    # 若未找到（例如所有 assistant 都在 target 之后，或者只有一轮）
    if cut_index == -1:
        # 寻找列表中最后一个完整的 assistant 节点（但至少留出一轮）
        for i in range(len(active_turns) - 1, -1, -1):
            if active_turns[i].role == "assistant" and i < len(active_turns) - 1:
                cut_index = i
                break

    # 如果依然找不到（例如总共只有 1 条消息），则不执行截断
    if cut_index == -1:
        return [], active_turns

    overflow_turns = active_turns[: cut_index + 1]
    remaining_turns = active_turns[cut_index + 1 :]

    logger.debug(
        f"对话完整性对齐切片完成: 待压缩轮数={len(overflow_turns)} (累积约 {accumulated} Token), "
        f"保留活跃轮数={len(remaining_turns)}"
    )
    return overflow_turns, remaining_turns


class MemoryCompactor:
    """
    认知记忆滚动压缩引擎
    """

    def __init__(
        self,
        llm_invoker: Optional[Callable[[str, str], Coroutine[Any, Any, str]]] = None,
        prompt_path: Optional[Path] = None,
    ):
        """
        初始化压缩器
        
        Args:
            llm_invoker: 可选的自定义异步推理调用器 (入参为 system_prompt, user_content，返回文本)
                        若为 None 则默认由 config.toml 中的 models.fast 端点驱动
            prompt_path: 压缩器系统提示词 Markdown 路径 (默认加载 prompts/compactor.md)
        """
        self._custom_invoker = llm_invoker
        self.prompt_path = prompt_path or self._resolve_default_prompt_path()
        self._system_prompt_cache: Optional[str] = None

    def _resolve_default_prompt_path(self) -> Path:
        """动态解析 compactor.md 提示词文件物理路径"""
        possible_paths = [
            Path(__file__).resolve().parent.parent / "prompts" / "compactor.md",
            Path("prompts/compactor.md"),
            Path("AegisAgent/src/agent_runtime/prompts/compactor.md"),
        ]
        found = next((p for p in possible_paths if p.is_file()), None)
        if not found:
            logger.warning("未找到 compactor.md 提示词文件，将使用内置保底提示词")
            return Path("prompts/compactor.md")
        return found

    def _load_system_prompt(self) -> str:
        """读取并缓存系统提示词"""
        if self._system_prompt_cache is not None:
            return self._system_prompt_cache

        if self.prompt_path.is_file():
            try:
                self._system_prompt_cache = self.prompt_path.read_text(encoding="utf-8")
                return self._system_prompt_cache
            except Exception as e:
                logger.error(f"读取提示词文件 {self.prompt_path} 失败: {e}")

        # 保底内置提示词
        self._system_prompt_cache = (
            "你是一个会话认知记忆压缩专家。请根据输入的已有记忆与新增对话轮次，"
            "合并提炼全局摘要、已确认事实与踩坑禁区，输出严格符合要求的 JSON 字符串。"
        )
        return self._system_prompt_cache

    async def _default_llm_invoke(self, system_prompt: str, user_content: str) -> str:
        """基于 config.toml 中的 models.fast 默认首选端点执行推理"""
        cfg = get_config()
        fast_tier = cfg.models.fast
        if not fast_tier.endpoints:
            raise RuntimeError("未配置任何 models.fast 模型端点，无法执行记忆压缩")

        endpoint = fast_tier.endpoints[0]
        api_key = endpoint.resolve_api_key()

        client = AsyncOpenAI(
            base_url=endpoint.base_url,
            api_key=api_key or "EMPTY",
            timeout=endpoint.timeout_sec,
        )

        response = await client.chat.completions.create(
            model=endpoint.model,
            temperature=fast_tier.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "{}"

    def _format_compaction_input(
        self,
        prior_memory: CompressedMemory,
        overflow_turns: List[TurnRecord],
    ) -> str:
        """将待压缩的已有记忆与新增轮次组装为结构化 Prompt 输入"""
        # 1. 组装已有历史记忆
        prior_section = []
        if prior_memory.summary:
            prior_section.append(f"- 既有历史背景: {prior_memory.summary}")
        if prior_memory.confirmed_facts:
            facts_str = "; ".join(prior_memory.confirmed_facts)
            prior_section.append(f"- 既有已确认事实: {facts_str}")
        if prior_memory.failed_attempts:
            fails_str = "; ".join([f"{f.action} (原因: {f.failure_reason})" for f in prior_memory.failed_attempts])
            prior_section.append(f"- 既有踩坑禁区: {fails_str}")

        prior_text = "\n".join(prior_section) if prior_section else "（无既有历史记忆，为首次建立）"

        # 2. 组装溢出的新对话
        turns_section = []
        for t in overflow_turns:
            turns_section.append(f"[{t.role.upper()}]: {t.content}")
        turns_text = "\n\n".join(turns_section)

        return f"""
## 已有历史记忆 (Prior Memory)
{prior_text}

## 新增待压缩对话轮次 (New Overflow Turns)
{turns_text}
"""

    async def compact(
        self,
        prior_memory: CompressedMemory,
        overflow_turns: List[TurnRecord],
    ) -> CompressedMemory:
        """
        执行记忆压缩提炼
        
        Args:
            prior_memory: 压缩前的旧记忆体
            overflow_turns: 溢出滑窗的未压缩对话列表
            
        Returns:
            CompressedMemory: 更新后的新认知记忆对象 (若遇异常则安全返回旧记忆)
        """
        if not overflow_turns:
            return prior_memory

        system_prompt = self._load_system_prompt()
        user_input = self._format_compaction_input(prior_memory, overflow_turns)

        logger.info(f"触发记忆滚动压缩: 待处理溢出轮数={len(overflow_turns)}, 原有事实数={len(prior_memory.confirmed_facts)}")

        try:
            # 执行推理 (支持自定义或默认驱动)
            if self._custom_invoker:
                raw_output = await self._custom_invoker(system_prompt, user_input)
            else:
                raw_output = await self._default_llm_invoke(system_prompt, user_input)

            # 解析 JSON 响应
            clean_output = raw_output.strip()
            if clean_output.startswith("```json"):
                clean_output = clean_output[7:]
            if clean_output.startswith("```"):
                clean_output = clean_output[3:]
            if clean_output.endswith("```"):
                clean_output = clean_output[:-3]
            clean_output = clean_output.strip()

            parsed = json.loads(clean_output)

            new_summary = parsed.get("summary", prior_memory.summary)

            # 合并与去重事实
            merged_facts = list(prior_memory.confirmed_facts)
            for f in parsed.get("confirmed_facts", []):
                if isinstance(f, str) and f.strip():
                    merged_facts.append(f.strip())

            # 合并踩坑禁区
            merged_attempts = list(prior_memory.failed_attempts)
            for item in parsed.get("failed_attempts", []):
                if isinstance(item, dict):
                    try:
                        merged_attempts.append(FailedAttempt(**item))
                    except Exception as e:
                        logger.warning(f"解析 FailedAttempt 条目异常: {e}，已跳过")

            updated_memory = CompressedMemory(
                compacted_until_turn_id=overflow_turns[-1].id or prior_memory.compacted_until_turn_id,
                summary=new_summary,
                confirmed_facts=merged_facts,
                failed_attempts=merged_attempts,
                last_action_target=prior_memory.last_action_target,
            )
            updated_memory.deduplicate_facts()

            logger.info(
                f"记忆滚动压缩成功: 新水位线 turn_id={updated_memory.compacted_until_turn_id}, "
                f"提炼后事实数={len(updated_memory.confirmed_facts)}, 踩坑数={len(updated_memory.failed_attempts)}"
            )
            return updated_memory

        except Exception as e:
            # 优雅降级防护：压缩失败绝不抛出异常破坏主会话
            logger.warning(f"记忆滚动压缩遭遇异常: {e}，已自动降级保留原记忆")
            return prior_memory
