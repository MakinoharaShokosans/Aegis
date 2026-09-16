# AegisAgent MCP（模型上下文协议）系统功能与设计里程碑

> **对应设计规范**：`documents/agent_runtime/09_mcp_integration_and_governance.md`  
> **核心原则**：数据面与控制面分离、静态接入审查、逐名显式授权、stdio 进程物理配额限制。  
> 
> **图例规范**：`[代码实现] [测试通过]`

---

## 一、MCP 协议接入与工具适配

- [x] [ ] **标准 MCP 协议通信支持**
  - [x] [ ] stdio 传输协议客户端适配（子进程输入输出流标准通信）
  - [x] [ ] SSE / HTTP 传输协议客户端适配扩展支持
- [x] [ ] **动态 Tool 契约双向转译**
  - [x] [ ] 将 MCP Server 暴露的工具动态映射为 `AegisTool` 规范
  - [x] [ ] 自动转译 JSON Schema 为 OpenAI Tools Function Calling 结构
  - [x] [ ] 结构化封装 MCP 工具调用执行结果为 `ToolResult`

---

## 二、静态接入审查与安全治理 (`mcps/vetting.py`)

- [x] [ ] **服务级静态接入审查（Pre-flight Vetting）**
  - [x] [ ] 启动阶段对配置中的 MCP Server 执行安全性预检
  - [x] [ ] 校验 stdio 启动命令与执行路径安全性
- [x] [ ] **工具描述与元数据消毒（Description Sanitization）**
  - [x] [ ] 检测工具名称与描述中是否存在 Prompt 注入伪造特征
  - [x] [ ] 拦截并硬拒绝包含恶意系统指令伪造的 MCP 工具描述
- [x] [ ] **控制面与数据面信任分离**
  - [x] [ ] 所有 MCP 工具默认标记为 `trust="untrusted"`
  - [x] [ ] 外部不可信 MCP 工具必须经过白名单逐名授权方可进入特权工具表

---

## 三、stdio 子进程物理隔离与资源配额

- [x] [ ] **操作系统级资源硬限制（`setrlimit`）**
  - [x] [ ] 为 stdio 子进程施加虚拟内存上限（RLIMIT_AS），防范内存耗尽攻击
  - [x] [ ] 为子进程施加最大 CPU 时间限制（RLIMIT_CPU），防止死循环占用
- [x] [ ] **进程生命周期与超时治理**
  - [x] [ ] 工具调用级超时控制，防范挂起与死锁
  - [x] [ ] 任务结束后自动清理并终止孤儿子进程

---

## 四、运行时管理与自省服务

- [x] [ ] **统一 MCP 管理器（`MCPManager`）**
  - [x] [ ] 支持多 MCP Server 声明式配置加载与生命周期管理
  - [x] [ ] 异常服务连接失败时的优雅降级（不影响主系统启动）
- [x] [ ] **HTTP 自省 API 端点**
  - [x] [ ] 提供 `GET /api/v1/mcps` 查询已挂载 MCP 服务状态、已发现工具清单及安全审查报告
