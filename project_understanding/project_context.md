# Project Context

> 状态标签: `[Current]`(实码校验) | `[Unverified]`(历史推断待印证) | `[Unknown]`(尚无证据) | `[Stale]`(待修正)

## 1. 全局定位与用途
- `[Current]` **项目名称**: Aegis (Engineering Research Agent / 本地自主工程研发智能体与多模态 RAG 系统)
- `[Current]` **核心目标**: 对标 Claude Code / Devin 的本地自主研发智能体系统，提供双层规划自愈状态机、文档与代码双域混合 RAG、三层上下文治理、受控沙箱与实时流式工作台。

## 2. 主技术栈与运行环境
- `[Current]` **语言与环境**: Python >= 3.11, Node.js (TypeScript), Linux (PGID 隔离沙箱)
- `[Current]` **Agent 调度**: LangGraph (>=1.2.11), langgraph-checkpoint-sqlite, OpenAI SDK, Pydantic v2
- `[Current]` **RAG 基础设施**: Qdrant-client, FastEmbed (ONNX, 纯 CPU 稠密+稀疏双路), Tree-Sitter (C/C++/Go AST 解析), LangChain Text Splitters
- `[Current]` **服务与通信**: FastAPI, Uvicorn, HTTPX, Server-Sent Events (SSE), MCP (Model Context Protocol >=2.2.0)
- `[Current]` **前端工作台**: React 19, TypeScript, Vite 6, Zustand 5, Monaco Editor, TailwindCSS, React Resizable Panels
- `[Current]` **存储与持久化**: SQLite (aiosqlite WAL), Qdrant 向量库, 本地 Artifacts 文件存储

## 3. 核心执行入口
- `[Current]` **全局统管启动**: `./start` / `./start.sh` (支持 `agent`, `rag`, `frontend`, `all`)
- `[Current]` **Agent 服务入口**: `AegisAgent/start` (或 `AegisAgent/src/agent_runtime/api/__main__.py`, 监听端口 `8000`)
- `[Current]` **RAG 服务入口**: `AegisRAG/start` (或 `AegisRAG/src/api/__main__.py`, 监听端口 `8001`)
- `[Current]` **前端 UI 入口**: `AegisFrontend/start` (Vite 开发服务器, 监听端口 `5173`)

## 4. 主目录规划
- `[Current]` `AegisAgent/`: Agent 调度宿主、状态机、Nodes、Edges、沙箱与工具服务
- `[Current]` `AegisRAG/`: 独立代码与文档检索微服务、AST 解析、双路向量化与精排
- `[Current]` `AegisFrontend/`: Web 前端工作台界面
- `[Current]` `documents/`: 完备的架构设计蓝图、技术规范与测试路线
- `[Current]` `storage/`: 运行时持久化存储与产物

## 5. 当前已知硬性限制与未知项
- `[Current]` 沙箱环境绑定 Linux PGID 进程组管理与资源配额 (内存 2GB / 输出 50MB)
- `[Unknown]` 外部真实 LLM API Key 配置状态及联调环境可用性
