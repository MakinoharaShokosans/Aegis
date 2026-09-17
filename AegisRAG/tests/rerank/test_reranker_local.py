"""本地 Cross-Encoder 精排打分单元测试。

验证本地 TextCrossEncoder 批量打分、相关性判别与空输入处理。
"""

from __future__ import annotations

from rerank.reranker import Reranker


class TestRerankerLocal:
    """本地精排器测试套件。"""

    def test_local_reranker_scoring_and_relative_order(self, base_settings) -> None:
        cfg = base_settings.rerank.model_copy(
            update={
                "mode": "local",
                "cache_dir": str(base_settings.resolve_path(base_settings.rerank.cache_dir)),
            }
        )
        reranker = Reranker(cfg)
        try:
            query = "binary search tree implementation in C"
            relevant_doc = "struct Node { int val; struct Node* left; struct Node* right; };"
            irrelevant_doc = "SELECT name, age FROM users WHERE id = 100;"

            scores = reranker.score(query=query, documents=[relevant_doc, irrelevant_doc])

            assert len(scores) == 2
            assert all(isinstance(s, float) for s in scores)
            # 相关代码片段得分必须显著高于不相关 SQL 语句
            assert scores[0] > scores[1]
        finally:
            reranker.close()

    def test_empty_documents_returns_empty_list(self, base_settings) -> None:
        cfg = base_settings.rerank.model_copy(
            update={
                "mode": "local",
                "cache_dir": str(base_settings.resolve_path(base_settings.rerank.cache_dir)),
            }
        )
        reranker = Reranker(cfg)
        try:
            assert reranker.score(query="test", documents=[]) == []
        finally:
            reranker.close()
