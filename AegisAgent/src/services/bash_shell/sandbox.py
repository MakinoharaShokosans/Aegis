"""受控执行器：os.setsid 独立进程组 + setrlimit 配额 + SIGTERM/SIGKILL 两段式硬杀 + 输出蒸馏。

执行链路（ADR §2.1–2.4、§4 裁决项⑦）：
1. ``run_command`` 先做 **CommandAudit** 黑名单审计与写入目标越界校验，再申请内存池配额；
2. 以 ``asyncio.create_subprocess_shell`` 派发命令，``preexec_fn`` 中依次调用
   ``os.setsid()``（独立进程组，便于整组清退孤儿进程）与 ``resource.setrlimit``
   （RLIMIT_AS / RLIMIT_FSIZE / RLIMIT_CPU 物理硬配额）；
3. ``cwd`` 绑定**目标工程根目录** ``workspace_root``（不是临时目录），
   而 stdout/stderr 全量日志流式落盘到 ``{artifacts_dir}/{task_id}/step_{step_id}_bash.log``；
4. 超时后**两段式硬杀**：先 ``os.killpg(pgid, SIGTERM)``，等待 ``sigterm_grace_sec``
   仍未退出则升级 ``SIGKILL``，彻底清退进程组；
5. **结构化感知蒸馏**：完整且可解析为 JSON/YAML 的输出原样返回；否则成功态取
   Head/Tail，失败态按关键字行过滤并附退出码。全量日志只落盘，不驻留内存。

规范：documents/技术选型/bash_shell.md；documents/agent_runtime/10_directory_structure.md 裁决项⑦
"""

from __future__ import annotations

import asyncio
import codecs
import json
import os
import re
import resource
import signal
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Callable, Deque, Dict, List, Literal, Optional, Sequence

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from .audit import CommandAudit, PathEscapeError, ensure_within_root
from .memory_pool import GlobalMemoryBudget
from .settings import BashShellSettings, get_settings

try:  # PyYAML 为结构化嗅探的可选增强，缺失时降级为 JSON-only + 文本蒸馏
    import yaml
except ImportError:  # pragma: no cover - 依赖缺失时的明确降级分支
    yaml = None  # type: ignore[assignment]

__all__ = [
    "ShellStatus",
    "ShellExecutionResult",
    "WorkspaceInvalidError",
    "DistilledText",
    "distill_stream",
    "run_command",
]

#: 执行状态枚举：成功 / 普通失败 / 超时硬杀 / 被信号终止 / 配额排队未执行
ShellStatus = Literal["SUCCESS", "FAILED", "TIMEOUT", "KILLED", "QUEUED"]

#: 失败态关键字过滤规则（ADR §2.4：引导模型精准错误自愈）
_ERROR_KEYWORD = re.compile(
    r"error:|fatal:|warning:|undefined reference|Segmentation fault|Traceback",
    re.IGNORECASE,
)

#: 任务标识白名单：仅允许单层安全目录名，杜绝 task_id 携带路径分隔符逃逸落盘根
_TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class WorkspaceInvalidError(ValueError):
    """工作区根目录非法（不存在或不是目录）。

    Attributes:
        workspace_root: 非法的工作区根路径。
    """

    def __init__(self, workspace_root: str | Path) -> None:
        """初始化异常。

        Args:
            workspace_root: 非法的工作区根路径。
        """
        self.workspace_root = str(workspace_root)
        super().__init__(f"工作区根目录非法（不存在或不是目录）：{self.workspace_root}")

    def to_dict(self) -> Dict[str, Any]:
        """转换为结构化错误字典（HTTP 422 响应体载荷）。

        Returns:
            含 ``workspace_root`` 的字典。
        """
        return {"workspace_root": self.workspace_root}


class ShellExecutionResult(BaseModel):
    """命令执行结果（强类型响应契约，ADR §2.5）。

    Attributes:
        exit_code: 子进程退出码；被信号终止时为负值（如 ``-9``）；未执行（QUEUED）时为 ``None``。
        distilled_stdout: 蒸馏后的标准输出。
        distilled_stderr: 蒸馏后的标准错误。
        is_truncated: 任一输出流是否发生截断（完整日志始终在 ``artifact_path``）。
        artifact_path: 全量日志落盘绝对路径。
        execution_time_ms: 从派发到回收的实际耗时（毫秒）。
        status: 执行状态。
        timed_out: 是否因超时被两段式硬杀。
        queue_wait_sec: 本次为获取内存池配额实际等待的秒数。
        estimated_wait_sec: 内存池给出的后续排队预估秒数（QUEUED 时用于退避）。
    """

    model_config = ConfigDict(extra="forbid")

    exit_code: Optional[int] = Field(default=None, description="退出码；信号终止为负值")
    distilled_stdout: str = Field(description="蒸馏后的标准输出")
    distilled_stderr: str = Field(description="蒸馏后的标准错误")
    is_truncated: bool = Field(description="输出是否被截断（完整日志见 artifact_path）")
    artifact_path: str = Field(description="全量日志落盘绝对路径")
    execution_time_ms: int = Field(ge=0, description="实际执行耗时（毫秒）")
    status: ShellStatus = Field(description="执行状态")
    timed_out: bool = Field(default=False, description="是否因超时被硬杀")
    queue_wait_sec: float = Field(default=0.0, description="等待内存池配额的实际秒数")
    estimated_wait_sec: float = Field(default=0.0, description="内存池预估排队秒数")


# ==============================================================================
# 1. 流式捕获与蒸馏
# ==============================================================================


@dataclass(slots=True)
class _CaptureOutcome:
    """单条输出流的捕获结果（只保留蒸馏所需的最小切片）。

    Attributes:
        head_lines: 头部行。
        tail_lines: 尾部行。
        keyword_lines: 命中错误关键字的行。
        sniff_text: 结构化嗅探缓冲（流超出上限时被丢弃）。
        sniff_complete: 嗅探缓冲是否完整覆盖整条流。
        total_lines: 该流的总行数。
        total_chars: 该流的总字符数。
        keyword_overflow: 是否有关键字命中行因超出上限被丢弃。
    """

    head_lines: List[str]
    tail_lines: List[str]
    keyword_lines: List[str]
    sniff_text: str
    sniff_complete: bool
    total_lines: int
    total_chars: int
    keyword_overflow: bool


class _StreamCapture:
    """流式捕获器：分块喂入，只保留 Head/Tail/关键字/结构化嗅探切片。

    由于日志全量落盘而非驻留内存，本类在内存中只维持有界缓冲
    （head 行数 + tail 行数 + 关键字行上限 + 嗅探字节上限）。
    """

    def __init__(
        self,
        *,
        head_lines: int,
        tail_lines: int,
        keyword_max_lines: int,
        sniff_max_bytes: int,
    ) -> None:
        """初始化捕获器。

        Args:
            head_lines: 头部保留行数。
            tail_lines: 尾部保留行数。
            keyword_max_lines: 关键字命中行保留上限。
            sniff_max_bytes: 结构化嗅探缓冲上限（字节，按字符数近似计）。
        """
        self._head_limit = head_lines
        self._tail: Deque[str] = deque(maxlen=tail_lines)
        self._head: List[str] = []
        self._keywords: List[str] = []
        self._keyword_max = keyword_max_lines
        self._sniff_max = sniff_max_bytes
        self._sniff_parts: List[str] = []
        self._sniff_chars = 0
        self._sniff_complete = True
        self._residual = ""
        self._keyword_overflow = False
        self._total_lines = 0
        self._total_chars = 0
        self._finalized = False

    def feed(self, text: str) -> None:
        """喂入一段已解码文本。

        Args:
            text: 解码后的文本片段（可能不以换行结尾）。

        Raises:
            RuntimeError: 捕获器已 finalize 后再次喂入时抛出。
        """
        if self._finalized:
            raise RuntimeError("流捕获器已结束，禁止继续写入")
        if not text:
            return

        if self._sniff_complete:
            if self._sniff_chars + len(text) <= self._sniff_max:
                self._sniff_parts.append(text)
                self._sniff_chars += len(text)
            else:
                # 超出嗅探上限：丢弃缓冲，避免大输出驻留内存（结构化解析不再可行）
                self._sniff_complete = False
                self._sniff_parts.clear()
                self._sniff_chars = 0

        self._total_chars += len(text)
        buffer = self._residual + text
        *lines, self._residual = buffer.split("\n")
        for line in lines:
            self._consume(line)

    def _consume(self, line: str) -> None:
        """处理一整行。

        Args:
            line: 单行文本（不含换行符）。
        """
        self._total_lines += 1
        if len(self._head) < self._head_limit:
            self._head.append(line)
        else:
            self._tail.append(line)
        if _ERROR_KEYWORD.search(line):
            if len(self._keywords) < self._keyword_max:
                self._keywords.append(line)
            else:
                self._keyword_overflow = True

    def finalize(self) -> _CaptureOutcome:
        """收束捕获器并输出结果切片。

        Returns:
            捕获结果（尾部残行按整行计入）。
        """
        if not self._finalized:
            if self._residual:
                self._consume(self._residual)
                self._residual = ""
            self._finalized = True
        return _CaptureOutcome(
            head_lines=list(self._head),
            tail_lines=list(self._tail),
            keyword_lines=list(self._keywords),
            sniff_text="".join(self._sniff_parts),
            sniff_complete=self._sniff_complete,
            total_lines=self._total_lines,
            total_chars=self._total_chars,
            keyword_overflow=self._keyword_overflow,
        )


@dataclass(slots=True)
class DistilledText:
    """蒸馏结果。

    Attributes:
        text: 蒸馏后的文本。
        is_truncated: 是否发生截断。
        strategy: 采用的蒸馏策略（``empty`` / ``structured`` / ``head_tail`` / ``keyword`` / ``tail_fallback``）。
    """

    text: str
    is_truncated: bool
    strategy: str = field(default="empty")


def _try_parse_structured(text: str) -> bool:
    """判断文本是否为完整且可解析的结构化数据（JSON 优先，YAML 兜底）。

    YAML 解析要求结果为映射或序列——否则近乎任意纯文本都能被 YAML 解析成字符串标量，
    会把普通日志误判为结构化输出从而绕过蒸馏。

    Args:
        text: 待判定文本（应为完整流内容）。

    Returns:
        ``True`` 表示是完整结构化数据，可原样返回。
    """
    stripped = text.strip()
    if not stripped:
        return False
    try:
        json.loads(stripped)
        return True
    except (json.JSONDecodeError, ValueError):
        pass
    if yaml is None:
        return False
    try:
        parsed = yaml.safe_load(stripped)
    except yaml.YAMLError:
        return False
    return isinstance(parsed, (dict, list))


def distill_stream(
    outcome: _CaptureOutcome,
    *,
    exit_code: int,
    settings: BashShellSettings,
    artifact_path: str,
    stream_name: str = "stdout",
) -> DistilledText:
    """对单条输出流执行结构化感知蒸馏。

    策略优先级（ADR §2.4）：
    1. 完整且可解析为 JSON/YAML ⇒ 原样返回（避免截断破坏语法结构）；
    2. 失败态（exit_code != 0）⇒ 关键字行过滤，无命中则退回尾部；
    3. 成功态 ⇒ Head ``distill_head_lines`` 行 + Tail ``distill_tail_lines`` 行。

    Args:
        outcome: 该流的捕获结果。
        exit_code: 子进程退出码。
        settings: 子系统配置（提供 Head/Tail 行数）。
        artifact_path: 全量日志路径（写入省略提示，作为证据句柄）。
        stream_name: 流名称（仅用于提示文案与日志）。

    Returns:
        蒸馏结果对象。
    """
    # ---- 1) 结构化优先：完整即原样返回 ----
    if outcome.sniff_complete and _try_parse_structured(outcome.sniff_text):
        return DistilledText(
            text=outcome.sniff_text.rstrip("\n"), is_truncated=False, strategy="structured"
        )

    if outcome.total_lines == 0 and not outcome.sniff_text.strip():
        return DistilledText(text="", is_truncated=False, strategy="empty")

    # ---- 2) 失败态：关键字行过滤 ----
    if exit_code != 0:
        hits = outcome.keyword_lines
        if hits:
            body = "\n".join(hits)
            omitted = outcome.total_lines - len(hits)
            truncated = omitted > 0
            if truncated:
                body += (
                    f"\n... [{omitted} 行未命中错误关键字，已省略；完整日志见 {artifact_path}] ..."
                )
            if outcome.keyword_overflow:
                body += (
                    f"\n... [关键字命中行超过 {settings.distill_max_keyword_lines} 行上限，"
                    f"其余已省略；完整日志见 {artifact_path}] ..."
                )
            return DistilledText(text=body, is_truncated=truncated or outcome.keyword_overflow, strategy="keyword")

        tail = outcome.tail_lines
        if tail:
            body = "\n".join(
                [
                    f"... [{stream_name} 未匹配到错误关键字，以下为输出尾部] ...",
                    *tail,
                ]
            )
            return DistilledText(
                text=body,
                is_truncated=outcome.total_lines > len(tail),
                strategy="tail_fallback",
            )
        return DistilledText(text="", is_truncated=False, strategy="empty")

    # ---- 3) 成功态：Head + Tail ----
    head = outcome.head_lines
    tail = outcome.tail_lines
    if outcome.total_lines <= len(head) + len(tail):
        return DistilledText(text="\n".join(head + tail), is_truncated=False, strategy="head_tail")
    omitted = outcome.total_lines - len(head) - len(tail)
    body = "\n".join(
        [
            *head,
            f"... [{omitted} 行已省略；完整日志见 {artifact_path}] ...",
            *tail,
        ]
    )
    return DistilledText(text=body, is_truncated=True, strategy="head_tail")


# ==============================================================================
# 2. 子进程执行原语
# ==============================================================================


def _build_preexec(settings: BashShellSettings) -> Callable[[], None]:
    """构造 ``preexec_fn``：fork 后、exec 前建立独立进程组并施加物理配额。

    Args:
        settings: 子系统配置（提供 rlimit 上限）。

    Returns:
        无参回调；子进程内依次调用 ``os.setsid()`` 与 ``resource.setrlimit``。
    """
    as_bytes = settings.rlimit_as_mb * 1024 * 1024
    fsize_bytes = settings.rlimit_fsize_mb * 1024 * 1024
    cpu_sec = settings.rlimit_cpu_sec

    def _apply() -> None:
        """子进程内执行：独立会话 + 物理资源硬上限。"""
        os.setsid()
        resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_bytes, fsize_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_sec, cpu_sec))

    return _apply


def _signal_process_group(pgid: int, sig: int) -> bool:
    """向进程组发送信号。

    Args:
        pgid: 进程组 ID（等于 shell 子进程 PID）。
        sig: 信号编号。

    Returns:
        ``True`` 表示信号已投递；``False`` 表示进程组已不存在或无权操作。
    """
    try:
        os.killpg(pgid, sig)
        return True
    except ProcessLookupError:
        # 进程组已消亡：属正常竞态，无需告警
        return False
    except PermissionError:
        logger.error("向进程组 {} 发送信号 {} 被拒绝（权限不足）", pgid, sig)
        return False


async def _terminate_process_group(proc: asyncio.subprocess.Process, grace_sec: float) -> None:
    """两段式硬杀进程组：SIGTERM →（宽限期）→ SIGKILL。

    Args:
        proc: 目标子进程（其 PID 即进程组 ID）。
        grace_sec: SIGTERM 与 SIGKILL 之间的宽限期（秒）。
    """
    pgid = proc.pid
    if _signal_process_group(pgid, signal.SIGTERM):
        try:
            await asyncio.wait_for(proc.wait(), timeout=grace_sec)
            return
        except asyncio.TimeoutError:
            logger.warning("进程组 {} 在 {}s 宽限期内未退出，升级 SIGKILL", pgid, grace_sec)
    _signal_process_group(pgid, signal.SIGKILL)
    await proc.wait()


async def _pump_stream(
    reader: asyncio.StreamReader,
    capture: _StreamCapture,
    handle: BinaryIO,
    write_lock: asyncio.Lock,
    chunk_bytes: int,
) -> None:
    """流式读取单条管道：原始字节落盘 + 文本切片喂入捕获器。

    Args:
        reader: 子进程管道读取端。
        capture: 该流的捕获器。
        handle: 全量日志文件句柄（stdout/stderr 共用）。
        write_lock: 文件写入互斥锁（保证双流落盘不交错损坏）。
        chunk_bytes: 每次读取的字节数。

    Raises:
        OSError: 日志落盘失败时抛出（不吞异常）。
    """
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    while True:
        chunk = await reader.read(chunk_bytes)
        if not chunk:
            break
        async with write_lock:
            # 原始字节无损落盘；写入放到线程池，避免阻塞事件循环
            await asyncio.to_thread(handle.write, chunk)
        capture.feed(decoder.decode(chunk))
    tail_text = decoder.decode(b"", final=True)
    if tail_text:
        capture.feed(tail_text)


async def _settle_pumps(tasks: Sequence["asyncio.Task[None]"], *, grace_sec: float) -> None:
    """等待管道读取任务收束，超时则取消（并优先抛出真实异常）。

    Args:
        tasks: 管道读取任务列表。
        grace_sec: 等待收束的宽限期（秒）。

    Raises:
        BaseException: 任一已结束任务携带的异常（不吞异常）。
    """
    if not tasks:
        return
    done, pending = await asyncio.wait(set(tasks), timeout=grace_sec)
    for task in pending:
        logger.warning("管道读取任务 {} 未在宽限期内收束，强制取消", task.get_name())
        task.cancel()
    if pending:
        # 已主动取消的任务：显式回收其 CancelledError，避免"任务未取回异常"告警
        await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        error = task.exception()
        if error is not None:
            raise error


def _append_exit_marker(text: str, exit_code: int) -> str:
    """为失败输出追加退出码标记。

    Args:
        text: 蒸馏文本。
        exit_code: 子进程退出码。

    Returns:
        追加 ``[exit_code=N]`` 后的文本。
    """
    marker = f"[exit_code={exit_code}]"
    return f"{text}\n{marker}" if text else marker


async def _execute(
    *,
    command: str,
    workspace_root: Path,
    log_path: Path,
    timeout_sec: float,
    settings: BashShellSettings,
) -> ShellExecutionResult:
    """在沙箱内执行命令并完成落盘与蒸馏（不含审计与配额申请）。

    Args:
        command: 待执行命令（已通过审计）。
        workspace_root: 执行工作目录（目标工程根，``cwd``）。
        log_path: 全量日志落盘路径。
        timeout_sec: 本次执行的硬超时（秒）。
        settings: 子系统配置。

    Returns:
        命令执行结果。

    Raises:
        OSError: 日志文件无法创建或写入时抛出。
    """
    started = time.monotonic()
    handle = await asyncio.to_thread(log_path.open, "wb")
    write_lock = asyncio.Lock()
    capture_kwargs: Dict[str, Any] = {
        "head_lines": settings.distill_head_lines,
        "tail_lines": settings.distill_tail_lines,
        "keyword_max_lines": settings.distill_max_keyword_lines,
        "sniff_max_bytes": settings.structured_sniff_max_bytes,
    }
    stdout_capture = _StreamCapture(**capture_kwargs)
    stderr_capture = _StreamCapture(**capture_kwargs)

    proc: Optional[asyncio.subprocess.Process] = None
    pump_tasks: List["asyncio.Task[None]"] = []
    timed_out = False
    exit_code = -1

    try:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(workspace_root),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=_build_preexec(settings),
            )
            pump_tasks = [
                asyncio.create_task(
                    _pump_stream(
                        proc.stdout, stdout_capture, handle, write_lock, settings.stream_chunk_bytes
                    ),
                    name="bash_shell:stdout",
                ),
                asyncio.create_task(
                    _pump_stream(
                        proc.stderr, stderr_capture, handle, write_lock, settings.stream_chunk_bytes
                    ),
                    name="bash_shell:stderr",
                ),
            ]

            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
                exit_code = proc.returncode if proc.returncode is not None else -1
            except asyncio.TimeoutError:
                timed_out = True
                logger.warning(
                    "命令执行超时 {}s，启动两段式硬杀（pgid={}）", timeout_sec, proc.pid
                )
                await _terminate_process_group(proc, settings.sigterm_grace_sec)
                exit_code = proc.returncode if proc.returncode is not None else -1

            await _settle_pumps(pump_tasks, grace_sec=settings.sigterm_grace_sec)
            pump_tasks = []
        except BaseException:
            # 取消/异常路径：必须清退进程组并回收管道任务，避免孤儿进程与任务泄漏
            if proc is not None and proc.returncode is None:
                await _terminate_process_group(proc, settings.sigterm_grace_sec)
            for task in pump_tasks:
                task.cancel()
            if pump_tasks:
                await asyncio.gather(*pump_tasks, return_exceptions=True)
            raise
    finally:
        await asyncio.to_thread(handle.close)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    artifact = str(log_path)
    stdout_distilled = distill_stream(
        stdout_capture.finalize(),
        exit_code=exit_code,
        settings=settings,
        artifact_path=artifact,
        stream_name="stdout",
    )
    stderr_distilled = distill_stream(
        stderr_capture.finalize(),
        exit_code=exit_code,
        settings=settings,
        artifact_path=artifact,
        stream_name="stderr",
    )

    stdout_text = stdout_distilled.text
    stderr_text = stderr_distilled.text
    if exit_code != 0:
        stdout_text = _append_exit_marker(stdout_text, exit_code) if stdout_text else stdout_text
        stderr_text = _append_exit_marker(stderr_text, exit_code)
    if timed_out:
        # 显式告知模型"超时而非普通失败"，引导其缩短任务或拆分步骤
        note = (
            f"[timeout: 命令超过 {timeout_sec}s 未结束，"
            "已按 SIGTERM→SIGKILL 清退整个进程组]"
        )
        stderr_text = f"{stderr_text}\n{note}" if stderr_text else note

    if timed_out:
        status: ShellStatus = "TIMEOUT"
    elif exit_code == 0:
        status = "SUCCESS"
    elif exit_code < 0:
        status = "KILLED"
    else:
        status = "FAILED"

    logger.bind(
        status=status,
        exit_code=exit_code,
        elapsed_ms=elapsed_ms,
        stdout_strategy=stdout_distilled.strategy,
        stderr_strategy=stderr_distilled.strategy,
    ).info("bash_shell 执行完成")

    return ShellExecutionResult(
        exit_code=exit_code,
        distilled_stdout=stdout_text,
        distilled_stderr=stderr_text,
        is_truncated=stdout_distilled.is_truncated or stderr_distilled.is_truncated,
        artifact_path=artifact,
        execution_time_ms=elapsed_ms,
        status=status,
        timed_out=timed_out,
    )


# ==============================================================================
# 3. 编排入口
# ==============================================================================


def _validate_workspace_root(workspace_root: str | Path) -> Path:
    """校验并规范化工作区根目录。

    Args:
        workspace_root: 调用方下发的工作区根目录。

    Returns:
        规范化后的绝对路径。

    Raises:
        WorkspaceInvalidError: 路径为空、不存在或不是目录时抛出。
    """
    raw = str(workspace_root).strip()
    if not raw:
        raise WorkspaceInvalidError(workspace_root)
    resolved = Path(raw).expanduser().resolve()
    if not resolved.is_dir():
        raise WorkspaceInvalidError(resolved)
    return resolved


def _resolve_artifact_dir(settings: BashShellSettings, task_id: str) -> Path:
    """解析产物落盘目录并做双重越界防护。

    ``task_id`` 由调用方下发，直接拼进文件路径存在目录穿越风险，
    因此先做字符白名单校验，再用 ``ensure_within_root`` 以落盘根为边界复核。

    Args:
        settings: 子系统配置（提供 ``artifacts_root``）。
        task_id: 任务标识。

    Returns:
        规范化后的产物目录绝对路径（``{artifacts_root}/{task_id}``）。

    Raises:
        PathEscapeError: ``task_id`` 含非法字符或解析后逃逸出落盘根时抛出。
    """
    if not _TASK_ID_PATTERN.match(task_id):
        raise PathEscapeError(task_id, settings.artifacts_root)
    return ensure_within_root(settings.artifacts_root / task_id, settings.artifacts_root)


async def run_command(
    command: str,
    *,
    workspace_root: str | Path,
    task_id: str,
    step_id: int,
    timeout_sec: Optional[float] = None,
    queue_wait_sec: float = 0.0,
    estimated_mb: Optional[int] = None,
    write_paths: Sequence[str | Path] = (),
    settings: Optional[BashShellSettings] = None,
    audit: Optional[CommandAudit] = None,
    pool: Optional[GlobalMemoryBudget] = None,
) -> ShellExecutionResult:
    """编排入口：审计 → 越界校验 → 配额申请 → 沙箱执行 → 落盘蒸馏。

    Args:
        command: 待执行命令原文。
        workspace_root: 目标工程根目录（子进程 cwd，也是路径越界边界）。
        task_id: 任务标识，决定产物落盘目录 ``{artifacts_dir}/{task_id}/``。
        step_id: 步骤序号，决定日志文件名 ``step_{step_id}_bash.log``。
        timeout_sec: 本次执行硬超时（秒）；``None`` 时取配置默认值。
        queue_wait_sec: 允许等待内存池配额的秒数；``<= 0`` 时池满立即返回 QUEUED。
        estimated_mb: 预估内存占用（MB）；``None`` 时取 RLIMIT_AS 上限。
        write_paths: 调用方显式声明的写入/删除目标（额外越界校验）。
        settings: 子系统配置；``None`` 时使用进程单例。
        audit: 命令审计器；``None`` 时使用内置规则集。
        pool: 全局内存池；``None`` 时跳过配额排队（仅供离线调用与单测）。

    Returns:
        命令执行结果；配额不足且超出等待预算时 ``status == "QUEUED"``。

    Raises:
        AuditRejected: 命令命中高危黑名单时抛出（HTTP 层转 403）。
        PathEscapeError: 写入目标越界时抛出（HTTP 层转 422）。
        WorkspaceInvalidError: 工作区根目录非法时抛出（HTTP 层转 422）。
    """
    cfg = settings if settings is not None else get_settings()
    auditor = audit if audit is not None else CommandAudit()

    # 1) 前置审计：黑名单 + 显式/推断出的写入目标越界校验
    auditor.audit(command)
    root = _validate_workspace_root(workspace_root)
    targets: List[str | Path] = list(write_paths) + list(auditor.extract_write_targets(command))
    for target in targets:
        ensure_within_root(target, root, base=root)

    # 2) 物理配额：不足时按等待预算排队，超预算返回 QUEUED 让调用方退避
    need_mb = estimated_mb if estimated_mb is not None else cfg.rlimit_as_mb
    acquired = False
    waited_sec = 0.0
    started = time.monotonic()
    if pool is not None:
        acquired, waited_sec = await pool.acquire_or_queue(need_mb, queue_wait_sec)
        if not acquired:
            logger.bind(task_id=task_id, step_id=step_id).warning(
                "内存池配额不足，任务进入排队（预估等待 {}s）", pool.estimate_wait_sec(need_mb)
            )
            return ShellExecutionResult(
                exit_code=None,
                distilled_stdout="",
                distilled_stderr="",
                is_truncated=False,
                artifact_path="",
                execution_time_ms=0,
                status="QUEUED",
                queue_wait_sec=round(waited_sec, 3),
                estimated_wait_sec=pool.estimate_wait_sec(need_mb),
            )

    try:
        artifact_dir = _resolve_artifact_dir(cfg, str(task_id))
        await asyncio.to_thread(artifact_dir.mkdir, parents=True, exist_ok=True)
        log_path = artifact_dir / f"step_{step_id}_bash.log"
        effective_timeout = timeout_sec if timeout_sec is not None else cfg.timeout_sec
        logger.bind(task_id=task_id, step_id=step_id, cwd=str(root)).info(
            "bash_shell 派发命令（timeout={}s）", effective_timeout
        )
        return await _execute(
            command=command,
            workspace_root=root,
            log_path=log_path,
            timeout_sec=effective_timeout,
            settings=cfg,
        )
    finally:
        if acquired and pool is not None:
            await pool.release(need_mb, duration_sec=time.monotonic() - started)
