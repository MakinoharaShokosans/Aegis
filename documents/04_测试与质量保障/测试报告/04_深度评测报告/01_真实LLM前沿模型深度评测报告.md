# 01_真实 LLM 前沿模型深度评测报告

> **评测目标**：评估在真实前沿大模型驱动下，Aegis 规划准确性、Tool Calling 遵循率及复杂长程任务交付能力。
> **覆盖测试集**：`AegisAgent/tests/real_llm/` (Phase 9 至 Phase 15)

---

## 1. 评测矩阵与能力阶段划分

| 阶段编号 | 评测目标与测试项 | 考察重点 | 预期基线指标 |
| :--- | :--- | :--- | :--- |
| **Phase 9** | `test_phase9_structured_output.py` | 严格 JSON 规划输出与 Pydantic 兼容性 | 结构化解析成功率 ≥ 99% |
| **Phase 10** | `test_phase10_live_workflow.py` | 真实工程编写、多文件联动与单测自愈执行 | 端到端自主闭环通过率 ≥ 85% |
| **Phase 11** | `test_phase11_live_permissions.py` | 敏感高危动作识别与主动发起 HITL 审批 | 越级动作漏报率 0% |
| **Phase 12** | `test_phase12_live_injection.py` | 对抗复杂越狱 Prompt 与第三方恶意指令伪装 | 攻击抵御成功率 100% |
| **Phase 13** | `test_phase13_live_research.py` | 研究子智能体有界循环与外部信息去噪提炼 | 报告生成合格率 ≥ 90% |
| **Phase 14** | `test_phase14_live_fallback.py` | 速率限制 (429) 指数退避与跨模型自动降级 | 降级切换成功率 100% |
| **Phase 15** | `test_phase15_live_context.py` | 超长上下文滚动摘要与精炼压缩记忆 | 关键事实信息保留率 ≥ 95% |

---

## 2. 环境说明与运行保护

为防止自动化 CI 流程中产生意外的 API 计费开销，`tests/real_llm/conftest.py` 配置了自动探针：当未配置有效的真实生产密钥时，该套件自动进入 `deselected` 跳过状态（本次单测统计中 12 个用例安全跳过），保障本地开发与常规回归的零成本与高安全性。
