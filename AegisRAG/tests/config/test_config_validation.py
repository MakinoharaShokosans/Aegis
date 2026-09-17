"""配置模型强类型校验与安全红线测试。

验证回环地址安全守卫、本地模式单 Worker 互斥约束与路径解析。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.settings import RagConfig, ServerConfig, get_settings


class TestConfigValidation:
    """配置校验测试套件。"""

    def test_server_host_guard_rejects_non_loopback(self) -> None:
        with pytest.raises(ValidationError, match="必须为回环地址"):
            ServerConfig(
                host="0.0.0.0",
                port=8001,
                workers=1,
                timeout_sec=60.0,
            )

    def test_local_mode_rejects_multi_workers(self, base_settings: RagConfig) -> None:
        server_multi = base_settings.server.model_copy(update={"workers": 4})
        with pytest.raises(ValidationError, match="server.workers 必须为 1"):
            RagConfig(
                server=server_multi,
                qdrant=base_settings.qdrant,
                embedding=base_settings.embedding,
                indexer=base_settings.indexer,
                retrieval=base_settings.retrieval,
                rerank=base_settings.rerank,
            )

    def test_resolve_path_resolution(self, base_settings: RagConfig) -> None:
        abs_path = base_settings.resolve_path("storage/qdrant_data")
        assert abs_path.is_absolute()
        assert str(abs_path).endswith("storage/qdrant_data")
