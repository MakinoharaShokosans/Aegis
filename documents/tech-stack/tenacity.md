---
aliases:
  - Tenacity
  - 弹性重试控制器
  - 指数退避重试
tags:
  - tech-stack
  - python
  - resilience
  - retry
  - network
package: "tenacity"
version: ">=9.1.4,<10.0.0"
project_role: "异步弹性重试控制器，为 LLM 网关访问与跨服务网络请求提供指数退避、特定异常过滤与防雪崩重试保护"
entrypoints:
  - "AegisAgent/src/agent_runtime/llm/fallback.py"
  - "AegisAgent/config/config.toml"
---

# Tenacity 辅助检索与理解指南

> [!info] 什么是 Tenacity
> **生活化比喻**：在复杂的网络世界里，大模型服务器经常会因为瞬间人多而报出“429 请求过多”或者偶发网络闪断。遇到这种情况，如果程序像个“毫无耐心的急性子”，遇到一次失败就立刻放弃并全线报错退出，系统可用性会极低；而如果毫无节制地原地疯打重试，又会像“DDOS 攻击一样把对方服务器彻底打趴”。Tenacity 就像是一个**“懂得分寸与礼貌的专业谈判专家”**：遇到偶发网络故障时，他会先安静等待 2 秒、再等待 4 秒、再等待 8 秒（指数退避），给对方喘息恢复的机会，连续尝试 3 次确实不行才向指挥部报告。

---

## 1. 小白心智模型（1分钟看懂）

- **解决的核心痛点**：如果不使用 Tenacity，开发者需要针对每一个异步网络请求手写多层嵌套的 `while retry_count < 3: try: ... except: await asyncio.sleep(2 ** retry_count)` 逻辑，不仅极其冗长容易引入死循环 Bug，而且难以统一管理重试间隔与异常类型白名单。
- **一句话本质**：Tenacity 是 Python 生态中**功能最强大、对原生 `async/await` 协程完美支持的通用重试库**。
- **三大核心物理机制**：
  1. **Stop Condition（终止条件，如 `stop_after_attempt`）**：决定最多重试多少次，或重试持续多长时间后坚决放弃。
  2. **Wait Strategy（等待退避策略，如 `wait_exponential`）**：以指数级递增等待时间（如 2s $\to$ 4s $\to$ 8s），防止网络拥塞时的“惊群效应/重试风暴”。
  3. **Retry Filter（异常判定条件，如 `retry_if_exception_type`）**：精准甄别哪些错误是可以重试的（如网络超时、HTTP 429、HTTP 503），哪些是绝对不能重试的（如 API Key 错误、参数不合规 400）。

---

## 2. 本项目中的角色与调用链路

- **在本项目的位置**：LLM 通信层与网络弹性防御层（LLM Gateway & Resilience Layer）。
- **核心入口文件**：
  - 端点重试与降级链：[`AegisAgent/src/agent_runtime/llm/fallback.py`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/llm/fallback.py)
  - 弹性重试配置项：[`AegisAgent/config/config.toml`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/config/config.toml#L22-L25)
- **典型执行流转链路**：
  ```text
  Executor / Planner 发起 LLM 推理请求
                       │
                       ▼
  AsyncRetrying 拦截器启动
                       │
                       ▼
  调用 OpenAI 兼容端点 (api.openlux.ai)
                       │
        ┌──────────────┴──────────────────────────┐
        ▼                                         ▼
   [返回成功 200]                             [遭遇 429 限流 / 502 网关错误]
  正常交出结果，重试计数清零                     命中 retry_if_exception_type 白名单
                                                  │
                                                  ▼
                                            执行指数退避 (wait_exponential)
                                                  │
                                                  ▼
                                            再次发起请求 (最多重试 max_retries 次)
  ```

---

## 3. 核心 Symbol 速查字典（类 / 函数 / 属性 / 装饰器）

### `AsyncRetrying`（异步重试控制器类）

- **通俗职责**：允许以 `async for attempt in AsyncRetrying(...): with attempt:` 块语法手动包裹异步调用代码，比起直接使用装饰器，它在需要动态注入上下文或精细记录每次重试日志时极其灵活。
- **参数说明**：
  - `stop`: 终止策略（如 `stop_after_attempt(3)`）。
  - `wait`: 等待策略（如 `wait_exponential(multiplier=2)`）。
  - `retry`: 重试过滤断言（如 `retry_if_exception_type(...)`）。
  - `reraise`: 最终耗尽重试次数后，是否原样抛出最后一次捕获的异常（通常设为 `True`）。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/llm/fallback.py:L20`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/llm/fallback.py#L20)
- **最小实战代码**：
  ```python
  from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

  async for attempt in AsyncRetrying(
      stop=stop_after_attempt(3),
      wait=wait_exponential(multiplier=2, min=1, max=10),
      reraise=True
  ):
      with attempt:
          response = await async_client.chat.completions.create(...)
  ```

---

### `stop_after_attempt`（尝试次数限制策略）

- **通俗职责**：限制最多尝试多少次（包含第 1 次初始尝试）。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/llm/fallback.py:L20`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/llm/fallback.py#L20)

---

### `wait_exponential`（指数退避策略）

- **通俗职责**：每次重试的等待秒数按指数形式上升（如 $min \times (multiplier^{\text{attempt}-1})$），直到达到设置的 $max$ 上限。
- **参数说明**：
  - `multiplier`: 底数乘数因子（本项目默认为 2.0 秒）。
  - `min`: 最小等待秒数。
  - `max`: 最大封顶等待秒数（防止无限拉长等待）。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/llm/fallback.py:L20`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/llm/fallback.py#L20)

---

### `retry_if_exception_type`（异常类型过滤断言）

- **通俗职责**：只有当捕获的异常属于指定的白名单类型时才触发重试；若遭遇白名单之外的错误（如密码错误、语法错误），立刻就地抛出，坚决不盲目重试。
- **本项目调用点**：[`AegisAgent/src/agent_runtime/llm/fallback.py:L20`](file:///home/Skualeilu/Projects/Aegis/AegisAgent/src/agent_runtime/llm/fallback.py#L20)

---

## 4. 本项目典型用法与实操范式

### 范式 1：LLM 网关端点级单点弹性重试
```python
# 路径：AegisAgent/src/agent_runtime/llm/fallback.py
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from openai import APIConnectionError, RateLimitError, APITimeoutError

RETRYABLE_EXCEPTIONS = (
    APIConnectionError,
    RateLimitError,
    APITimeoutError,
)

async def call_with_retry(client, kwargs, max_retries: int = 3, backoff_factor: float = 2.0):
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=backoff_factor, min=1.0, max=10.0),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        reraise=True,
    ):
        with attempt:
            # 遭遇 429 或断网时自动退避，最多重试 3 次
            return await client.chat.completions.create(**kwargs)
```

---

## 5. 新手易错陷阱与排坑指南

> [!warning] 陷阱 1：在异步代码中使用了同步的 `@retry` 导致死锁或协程阻塞
> **现象**：使用 `@retry(wait=wait_fixed(2))` 装饰 `async def` 函数，结果等待期间不是挂起协程，而是直接调用了同步的 `time.sleep()` 冻结了整个 Python 主事件循环。
> **正解**：在异步函数中，推荐使用 `AsyncRetrying` 迭代器块，或者确保导入使用 `tenacity.retry` 并配合异步友好的策略。

> [!warning] 陷阱 2：未配置 reraise=True 导致异常被吃掉变成 RetryError
> **现象**：重试耗尽后，抛出的是生硬的 `tenacity.RetryError`，上层完全看不到最原始的真实报错堆栈（如到底是哪个 IP 连接超时）。
> **正解**：始终配置 `reraise=True`，让 Tenacity 在放弃时原封不动抛出最后一次遭遇的真实领域异常。
