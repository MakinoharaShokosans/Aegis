# 系统架构设计

这是架构概览介绍。

## 存储引擎选型

### Qdrant 向量数据库

Qdrant 支持 Dense 与 Sparse 双路混合检索与 RRF 原生融合。

### 本地缓存策略

使用 FastEmbed 进行本地 ONNX 推理与权重缓存。
