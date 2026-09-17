"""AegisRAG 评测服务客户端驱动器。

规范：documents/测试路线/AegisRAG/评测执行规范.md 与 documents/rag_retrieval/06_evaluation_and_benchmarking.md

驱动流程：
1. 读取 EvalCase 标注数据集；
2. 针对每条用例，分别以 4 种消融模式请求 AegisRAG (/api/v1/retrieve)；
3. 将返回的有序 chunk_id 与时延规整为 RetrievalResult；
4. 调用 evaluate_retrieval.evaluate 产出全量消融指标报告并落盘。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

import httpx

from .dataset import EvalCase, load_dataset
from .evaluate_retrieval import (
    DEFAULT_REPORT_PATH,
    RetrievalResult,
    evaluate,
    render_report,
)

__all__ = ["RAGServiceClient", "main"]

#: 4 组消融模式映射：评测分组名 -> AegisRAG API 请求 mode 参数
_ABLATION_MODE_MAP = {
    "dense_only": "dense_only",
    "sparse_only": "sparse_only",
    "hybrid_rrf": "hybrid_no_rerank",
    "hybrid_rerank": "hybrid",
}


class RAGServiceClient:
    """AegisRAG 评测驱动客户端。

    Args:
        base_url: AegisRAG 服务的 HTTP 基址（默认 http://127.0.0.1:8001）。
        timeout_sec: 单次请求超时时间。
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8001", timeout_sec: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    def benchmark_cases(
        self,
        cases: Sequence[EvalCase],
        repo_name: str,
        top_k: int = 10,
    ) -> Dict[str, List[RetrievalResult]]:
        """对全部用例执行 4 组消融检索并收集结果。

        Args:
            cases: 标注评测用例列表。
            repo_name: 目标仓库名称。
            top_k: 单次检索候选数量上限。

        Returns:
            ``{消融分组名: [RetrievalResult, ...]}`` 字典。
        """
        results_by_group: Dict[str, List[RetrievalResult]] = {
            group: [] for group in _ABLATION_MODE_MAP
        }

        with httpx.Client(base_url=self.base_url, timeout=self.timeout_sec) as client:
            total_queries = len(cases) * len(_ABLATION_MODE_MAP)
            completed = 0

            for case in cases:
                for group_name, api_mode in _ABLATION_MODE_MAP.items():
                    payload = {
                        "query": case.query,
                        "repo_name": repo_name,
                        "top_k": top_k,
                        "mode": api_mode,
                    }

                    start = time.perf_counter()
                    try:
                        resp = client.post("/api/v1/retrieve", json=payload)
                        latency_ms = (time.perf_counter() - start) * 1000.0
                        resp.raise_for_status()
                        data = resp.json()
                        ranked_ids = [str(item["chunk_id"]) for item in data.get("results", [])]
                    except Exception as exc:  # noqa: BLE001
                        latency_ms = (time.perf_counter() - start) * 1000.0
                        print(f"[WARN] 用例 {case.case_id} 在模式 {group_name} 下请求失败: {exc}", file=sys.stderr)
                        ranked_ids = []

                    results_by_group[group_name].append(
                        RetrievalResult(
                            case_id=case.case_id,
                            ranked_ids=ranked_ids,
                            group=group_name,
                            latency_ms=latency_ms,
                        )
                    )
                    completed += 1

        return results_by_group


def main(argv: Sequence[str] | None = None) -> int:
    """评测驱动命令行入口。"""
    parser = argparse.ArgumentParser(
        prog="rag_service_client",
        description="AegisRAG 全景消融自动化基准评测驱动工具",
    )
    parser.add_argument("--dataset", required=True, help="标注数据集路径 (.json / .jsonl)")
    parser.add_argument("--service-url", default="http://127.0.0.1:8001", help="AegisRAG 服务基址")
    parser.add_argument("--repo-name", default="Aegis", help="目标仓库标识")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_REPORT_PATH),
        help=f"Markdown 报告输出路径 (默认: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument("--k", default="1,3,5,10", help="统计评估的 K 值列表")
    args = parser.parse_args(argv)

    k_values = [int(x.strip()) for x in args.k.split(",") if x.strip()]
    cases = load_dataset(args.dataset)
    print(f"[rag_bench] 成功加载 {len(cases)} 条评测用例")

    client = RAGServiceClient(base_url=args.service_url)
    print(f"[rag_bench] 开始向 {args.service_url} 发起 4 组消融检索请求...")

    results = client.benchmark_cases(cases=cases, repo_name=args.repo_name, top_k=max(k_values))
    print("[rag_bench] 检索采集完成，正在离线计算 IR 指标...")

    report = evaluate(results, cases, k_values)
    report_md = render_report(report)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")

    print("\n" + report_md)
    print(f"\n[✔ 评测完成] 结构化基线报告已落盘至: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
