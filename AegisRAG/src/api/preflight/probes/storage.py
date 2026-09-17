"""存储系统与磁盘 I/O 权限探针。

验证 Qdrant 本地数据目录、模型缓存目录的读写权限、文件锁以及可用磁盘空间容量。
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, List

from api.preflight.models import CheckStatus, DiagnosticItem
from api.preflight.probes.base import BaseProbe

if TYPE_CHECKING:
    from api.settings import RagConfig

__all__ = ["StorageProbe"]

_MIN_DISK_WARN_BYTES = 2 * 1024 * 1024 * 1024       # 2 GB 警告阈值
_MIN_DISK_FAIL_BYTES = 200 * 1024 * 1024             # 200 MB 阻断阈值


class StorageProbe(BaseProbe):
    """存储系统与磁盘权限探针。"""

    @property
    def category_name(self) -> str:
        return "存储系统与磁盘 I/O 权限"

    def run_checks(self, settings: RagConfig) -> List[DiagnosticItem]:
        items: List[DiagnosticItem] = []

        # 1. Qdrant 数据存储目录读写权限探测（仅在 local 模式）
        if settings.qdrant.mode == "local":
            qdrant_dir = settings.resolve_path(settings.qdrant.storage_path)
            items.append(self._test_directory_io(qdrant_dir, "Qdrant 本地存储目录"))
        else:
            items.append(
                DiagnosticItem(
                    name="Qdrant 本地存储目录",
                    status=CheckStatus.SKIP,
                    message="qdrant.mode='server'，跳过本地存储目录读写检查",
                )
            )

        # 2. FastEmbed 模型缓存目录读写权限探测
        cache_dir = settings.resolve_path(settings.embedding.cache_dir)
        items.append(self._test_directory_io(cache_dir, "FastEmbed 模型缓存目录"))

        # 3. 磁盘可用空间容量检查
        target_path = cache_dir if cache_dir.exists() else Path.cwd()
        try:
            total, used, free = shutil.disk_usage(target_path)
            free_gb = free / (1024**3)
            total_gb = total / (1024**3)
            usage_pct = (used / total) * 100.0

            if free < _MIN_DISK_FAIL_BYTES:
                items.append(
                    DiagnosticItem(
                        name="磁盘可用存储空间",
                        status=CheckStatus.FAIL,
                        message=f"可用磁盘空间极低: {free_gb:.2f} GB (使用率 {usage_pct:.1f}%)，低于 200 MB 启动底线",
                        remediation="请清理磁盘空间后再尝试启动",
                    )
                )
            elif free < _MIN_DISK_WARN_BYTES:
                items.append(
                    DiagnosticItem(
                        name="磁盘可用存储空间",
                        status=CheckStatus.WARN,
                        message=f"可用磁盘空间较紧张: {free_gb:.2f} GB (使用率 {usage_pct:.1f}%)，建议预留 >= 2 GB 用于模型缓存",
                        remediation="建议释放更多磁盘空间以防模型下载或写入索引时空间耗尽",
                    )
                )
            else:
                items.append(
                    DiagnosticItem(
                        name="磁盘可用存储空间",
                        status=CheckStatus.PASS,
                        message=f"可用空间充足: {free_gb:.2f} GB / 总计 {total_gb:.2f} GB (使用率 {usage_pct:.1f}%)",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            items.append(
                DiagnosticItem(
                    name="磁盘可用存储空间",
                    status=CheckStatus.WARN,
                    message=f"探测磁盘空间失败: {exc}",
                )
            )

        return items

    def _test_directory_io(self, directory: Path, label: str) -> DiagnosticItem:
        """测试目录的创建、写入与删除权限（零副作用）。"""
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe_file = directory / f".preflight_probe_{uuid.uuid4().hex}.tmp"
            # 写入测试
            probe_file.write_text("aegis_rag_io_probe", encoding="utf-8")
            # 读取验证
            content = probe_file.read_text(encoding="utf-8")
            if content != "aegis_rag_io_probe":
                raise IOError("写入内容与读取内容不一致")
            # 清理
            probe_file.unlink(missing_ok=True)
            return DiagnosticItem(
                name=label,
                status=CheckStatus.PASS,
                message=f"{directory} (读写权限正常)",
            )
        except PermissionError as exc:
            return DiagnosticItem(
                name=label,
                status=CheckStatus.FAIL,
                message=f"{directory} 缺少写权限: {exc}",
                remediation=f"请赋予当前用户对目录 {directory} 的读写权限 (如 chmod 755)",
            )
        except Exception as exc:  # noqa: BLE001
            return DiagnosticItem(
                name=label,
                status=CheckStatus.FAIL,
                message=f"{directory} I/O 测试失败: {exc}",
                remediation=f"请检查路径 {directory} 是否可访问",
            )
