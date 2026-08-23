# 掌柜智库 · 设备手册知识库管理平台

本项目是一个面向设备手册文档的知识库管理平台，采用「Django 主任务编排 + FastAPI RAG 引擎 + Celery/RabbitMQ 异步任务队列 + Vue3 前端」的分层架构。系统集成了文档智能解析、多路向量检索、假设性文档生成（HyDE）、联网搜索（MCP）、多路召回融合与重排序（RRF + Reranker）机制，专为企业级设备手册知识问答与文档管理场景设计。

---

## 🛠 技术栈

| 层级 | 技术                                                |
|------|---------------------------------------------------|
| **后端框架** | Django 5.2 + DRF 3.18（管理平台）、FastAPI（RAG 引擎）       |
| **异步任务** | Celery 5.6 + RabbitMQ（消息队列）                       |
| **认证** | djangorestframework-simplejwt（JWT）+ Redis 缓存认证    |
| **数据库** | MySQL 8（元数据/权限）、MongoDB（对话历史）                     |
| **向量检索** | Milvus v2.5.x + BGE-M3（Embedding）+ Reranker             |
| **缓存/状态** | Redis（业务缓存 db0 / 会话 db1 / 任务状态 db2）               |
| **文档解析** | MinerU（PDF → Markdown）                            |
| **对象存储** | MinIO                                             |
| **前端** | Vue3 + Vite + Element Plus + Vue Router + Axios   |
| **测试** | pytest + pytest-django                            |
| **运行环境** | Python 3.11（conda 环境 `shopkeeper-ai`）、Node.js 18+ |

---

## 🌟 核心特性

### 1. 自动化文档解析与向量化（Import Processor）
* **PDF 深度解析**：集成 **MinerU** 解析引擎，支持将复杂的 PDF 文档精准转换为标准 Markdown 结构。
* **图片自动管理**：提取 Markdown 中的图片并自动上传至 **MinIO** 对象存储服务，实现图文一体化管理。
* **智能切片与实体识别**：根据语义进行文本 Chunk 切片，并通过大语言模型进行品名/核心实体抽取（Item Name Recognition）。
* **向量存储**：使用 **BGE (如 BGE-M3)** 深度文本嵌入模型生成向量，入库至 **Milvus** 高性能向量数据库；兼容 Milvus v2.5.x 枚举格式的加载状态返回，自动适配多版本状态判断。

### 2. 多路召回与重排问答架构（Query Processor）
* **混合检索策略**：向量检索（Milvus）、HyDE 假设性文档检索、MCP 联网搜索三路并行召回。
* **RRF 融合与 Reranker 重排序**：RRF 算法合并多路召回，Reranker 交叉编码器精准二次排序。
* **上下文确认与生成**：结合实体确认（Item Name Confirm）与高相关性上下文生成精准回答。

### 3. 服务化分层架构
* **Django（8000）**：主任务编排 —— 用户认证与权限、文档/分类/品牌元数据管理、RAG 任务投递与状态查询。
* **FastAPI（8080）**：RAG 引擎 —— 文档解析、向量化入库、语义检索与 RAG 问答。
* **Celery + RabbitMQ**：异步任务队列 —— Django 生产任务，FastAPI worker 消费执行，结果回投队列回传。
* **Redis**：任务状态持久化、业务缓存、会话管理。
* **Vue3 前端（5173）**：前后端分离的独立工程，登录/注册/首页/个人中心等模块化页面。

### 4. 全链路性能优化
* **JWT 缓存认证**：用户认证信息 Redis 缓存复用，避免每次请求查询 MySQL 用户表，大幅降低数据库连接压力。
* **批量任务状态查询**：支持单次请求查询多个任务状态，配合前端批量轮询，HTTP 请求量下降 90% 以上。
* **Redis Pipeline 批量读取**：任务状态批量查询采用 Pipeline 单次网络往返，Redis IO 次数从 N 次降为 1 次。
* **数据库长连接复用**：MySQL 持久连接 10 分钟，减少频繁建连销毁开销。
* **Milvus 集合加载线程安全**：双重检查锁机制保证并发场景下集合仅触发一次加载，避免重复请求；加载失败自动降级，幂等清理操作跳过不阻塞主入库流程，保证任务成功率。

---

## 📁 项目目录结构

```text
knowledge_base/
├── config/                   # 系统全局配置
│   ├── bailian_mcp_config.py # 阿里百炼 MCP 联网搜索配置
│   ├── embedding_config.py   # Embedding 模型配置
│   ├── lm_config.py          # 大语言模型 (LLM) 配置
│   ├── milvus_config.py      # Milvus 向量库配置
│   ├── mineru_config.py      # MinerU PDF 解析工具配置
│   ├── minio_config.py       # MinIO 对象存储配置
│   ├── rabbitmq_config.py    # RabbitMQ / Celery 配置
│   └── reranker_config.py    # Reranker 重排模型配置
│
├── processor/                # 核心业务图处理节点
│   ├── import_processor/     # 文档导入工作流 (Import Graph)
│   │   ├── main_graph.py     # 导入图构建主程序
│   │   ├── state.py          # 导入图状态定义
│   │   └── nodes/            # 导入图节点 (PDF解析/切片/Embedding/Milvus入库)
│   └── query_processor/      # 问答检索工作流 (Query Graph)
│       ├── main_graph.py     # 查询图构建主程序
│       ├── state.py          # 查询图状态定义
│       ├── prompt/           # 各节点所需的 Prompt 模板
│       └── nodes/            # 查询节点 (向量检索/HyDE/MCP搜索/RRF/Reranker/回答生成)
│
├── tasks/                    # Celery 任务定义
│   ├── celery_app.py         # Celery 应用实例（RabbitMQ broker + Redis backend）
│   └── rag_tasks.py          # import_document / query_rag 任务 + 结果回投队列
│
├── utils/                    # 基础设施工具库
│   ├── embedding_utils.py    # Embedding 模型调用封装
│   ├── llm_utils.py          # LLM 统一接口
│   ├── mcp_utils.py          # MCP 工具通信
│   ├── milvus_utils.py       # Milvus 数据库增删改查封装
│   ├── minio_utils.py        # MinIO 文件/图片上传管理
│   ├── mongo_history_utils.py# MongoDB 对话历史读写
│   ├── redis_utils.py        # Redis 客户端统一获取
│   ├── reranker_http_utils.py# Reranker HTTP 交互封装
│   ├── sse_utils.py          # SSE 流式数据打包与推流
│   └── task_utils.py         # 任务状态追踪（Redis 持久化 + 批量查询）
│
├── web/                      # 后端服务
│   ├── fastapi/              # FastAPI RAG 服务（合并入库+检索，8080）
│   │   └── rag_service.py    # 单一 RAG 服务入口
│   └── django/               # Django 管理平台（8000，主任务编排）
│       ├── accounts/         # 用户/角色/权限 + JWT 认证
│       ├── catalog/          # 品牌/设备类型/分类
│       ├── documents/        # 文档/版本/内容/收藏
│       ├── search/           # 搜索日志/操作日志
│       ├── rag/              # RAG 任务代理（投递/查状态/批量查状态/查结果）  
│       ├── common/           # 统一响应/异常/分页/缓存认证封装
│       └── kb_platform/      # Django 项目配置
│
├── frontend/                 # Vue3 前端（前后端分离，独立工程）
│   ├── src/                  # 源码（api/router/store/layouts/views）
│   ├── index.html            # Vite 入口
│   ├── package.json
│   └── vite.config.js        # /api 代理到 Django 8000
│
├── tool/                     # 辅助脚本（模型下载、日志记录等）
│
├── eval/                     # 评测框架（质量评测 + 性能压测）
│   ├── run.py                # 评测主入口（函数调用式 main(mode=...)）
│   ├── run_test.py           # 评测数据集生成入口
│   ├── eva_config.py         # 评测配置
│   ├── metrics.py            # ROUGE/BLEU/语义相似度/命中率/延迟 + NDCG/MRR/P@K + 性能指标
│   ├── evals/                # 各质量评测环节（item_confirm/eva/rrf/rerank/mcp/retrieval/...）
│   └── perf/                 # 性能压测（并发压测/延迟测量/基线判定）
│
├── test/                     # 集成冒烟脚本（test/integration_import.py）
├── docs/                     # 文档
└── data/                     # 数据根目录
```

---

## 🔄 工作流运行机制

### 1. 文档导入处理流（Import Flow）
```text
node_entry
  └──> node_pdf_to_md (MinerU 解析)
         └──> node_md_img (图片提取与上传 MinIO)
                └──> node_document_split (文本分块)
                       └──> node_item_name_recognition (实体识别)
                              └──> node_bge_embedding (向量化)
                                     └──> node_import_milvus (存储至 Milvus)
```

### 2. 检索问答处理流（Query Flow）
```text
                            ┌──> node_search_embedding (向量检索) ──────────┐
                            │                                                │
User Query ──> [多路并行] ──┼──> node_search_embedding_hyde (HyDE 检索) ──────┼──> node_rrf ──> node_rerank ──> node_answer_output
                            │                                                │
                            └──> node_web_search_mcp (MCP 联网搜索) ─────────┘
```

### 3. 系统组件关系
```text
Vue3 前端(5173) ──> Django(8000) ──生产任务──> RabbitMQ Broker ──消费──> FastAPI Celery Worker
                                                                              │
                                                                              ├── 执行 KBImportWorkflow / KBQueryWorkflow
                                                                              ├── 投递结果 ──> 结果队列 kb_rag_result ──> Django 消费
                                                                              └── 状态写入 Redis（跨进程共享）
```

---

## ⚙️ 快速开始

### 1. 配置环境变量
复制根目录下的环境变量示例文件：
```bash
cp .env.example .env
```
根据实际环境编辑 `.env` 中的组件地址与密钥信息：
* `MILVUS_*`：Milvus 向量数据库连接参数
* `MINIO_*`：MinIO 对象存储配置
* `MONGO_*`：MongoDB 数据库配置
* `MYSQL_*`：MySQL 元数据数据库配置
* `REDIS_*`：Redis 缓存/任务状态配置
* `RABBITMQ_*` / `CELERY_*`：RabbitMQ 消息队列与 Celery 配置
* `LLM_*`：大语言模型 API 密钥与 Endpoint

### 2. 初始化数据库（首次运行）
```bash
cd web/django

# 生成并应用数据库迁移（建表）
python manage.py migrate

# 创建超级管理员（交互式，按提示输入用户名/邮箱/密码）
python manage.py createsuperuser
```

### 3. 启动服务
确保依赖组件（Milvus, MinIO, MongoDB, MySQL, Redis, RabbitMQ）已启动后，依次启动：

```bash
# 1. Celery Worker（消费 RAG 任务，threads 多线程并发，Windows 兼容）
cd knowledge_base
python -m celery -A tasks.celery_app:celery_app worker --loglevel=info --pool=threads --concurrency=2

# 2. FastAPI RAG 服务（8080）
python -m web.fastapi.rag_service

# 3. Django 管理平台（8000）
cd web/django
python manage.py runserver 127.0.0.1:8000
```

> **并发说明**：采用 `--pool=threads` 多线程并发（Windows 兼容）。
> - Windows 无 `fork()`，`prefork` 会报 `not enough values to unpack`；
> - `gevent` 会与 Redis/asyncio 冲突（socket monkey-patch），曾导致 Redis socket 超时与查询卡死；
> - `threads` 是 Windows 上可用的多线程并发，redis-py 连接池线程安全，无上述问题。
>
> 并发数通过环境变量 `CELERY_CONCURRENCY` 配置（默认按 CPU 核数，上限 8）。
> **2 核 4GB 内存 + 本地 GPU 场景建议设为 2**。
> 若需 50+ 并发，需更高配置的服务器（多核 CPU + 大内存 + 多 GPU）。

### 4. 前端（Vue3）
```bash
cd frontend
npm install
npm run dev
```
浏览器访问 `http://localhost:5173`。

### 5. 运行测试

测试直连外部数据库（MySQL / Redis / MongoDB），需先确保这些组件已启动。
使用 conda 环境 `shopkeeper-ai`：

```bash
conda activate shopkeeper-ai
cd web/django

# 日常测试：mock LLM（不调用真实 API，覆盖核心逻辑，控制成本）
python -m pytest rag/tests/ -m "not llm" -v

# 真实 LLM 冒烟：显式运行（问答 ≤5 条 + 1 个指定 PDF 入库）
python -m pytest rag/tests/ -m llm -v
```

> **LLM 成本控制**：涉及 LLM 的测试用 `@pytest.mark.llm` 标记，默认跳过。
> 真实 LLM 测试仅包含问答样本（≤5 条）与 1 个指定 PDF 入库冒烟，其余 LLM 调用点全部 mock。
> 完整入库冒烟脚本见 `test/integration_import.py`（`python test/integration_import.py`）。

> **默认账号**：开发环境已预置管理员账号 `admin / admin123456`（如使用 `createsuperuser` 创建则按你输入为准）。

---

## 🔑 服务端口一览

| 服务 | 端口 | 说明 |
|------|------|------|
| Django 管理平台 | 8000 | 主任务编排、API、Admin 后台 |
| FastAPI RAG 引擎 | 8080 | 文档解析、语义检索、问答 |
| Vue3 前端 | 5173 | 前后端分离的 Web 界面（开发模式） |
| MySQL | 3306 | 元数据/权限 |
| Redis | 6379 | 缓存/会话/任务状态 |
| RabbitMQ | 5672 | 消息队列（管理界面 15672） |
| Milvus | 19530 | 向量检索 |
| MongoDB | 27017 | 对话历史 |
| MinIO | 9000 | 对象存储（控制台 9001） |

---

## 🔌 API 概览

### Django（8000）
| 模块 | 前缀 | 说明 |
|------|------|------|
| 认证 | `/api/auth/` | `login`（登录）、`register`（注册）、`refresh`（刷新 token）、`me`（当前用户信息） |
| 账号 | `/api/accounts/` | `users`、`roles`、`permissions`、`role-permissions`、`user-roles` |
| 目录 | `/api/catalog/` | `brands`、`device-types`、`categories`（含 `/tree/`） |
| 文档 | `/api/documents/` | `documents`（含 `hot`/`view`/`download`）、`versions`、`contents`、`favorites` |
| 日志 | `/api/search/` | `logs`（搜索日志）、`document-logs`（操作日志） |
| RAG 代理 | /api/rag/ | submit（投递任务）、upload（上传入库）、status/{id}（查状态）、status/batch（批量查状态）、result/{id}（查结果） |

> 所有接口统一返回 `{code, message, data}` 格式；列表返回 `{count, page, page_size, results}`；写操作需管理员（`is_staff`）权限。

### FastAPI（8080）
| 接口 | 说明 |
|------|------|
| `POST /api/rag/` | 统一 RAG 入口（`op=import/query` 分发） |
| `POST /upload` | 文档上传（投递入库任务） |
| `POST /query` | 语义检索（投递检索任务） |
| `GET /status/{task_id}` | 任务状态查询 |
| `GET /stream/{session_id}` | SSE 流式输出 |
| `GET /history/{session_id}` | 查询对话历史 |
| `DELETE /history/{session_id}` | 清空对话历史 |
| `GET /health` | 健康检查 |

---

## 🧩 前端功能模块

前端采用 Element Plus 图书管理系统风格，左侧侧边栏 + 主内容区表格布局：

| 页面 | 路由           | 功能 |
|------|--------------|------|
| 登录 | `/login`     | JWT 登录 |
| 注册 | `/register`  | 用户注册 |
| 文档管理 | `/`          | 文档列表、搜索筛选、新增/编辑/删除 |
| 分类管理 | `/categories` | 分类树管理、CRUD |
| 用户管理 | `/users`     | 用户 CRUD、管理员开关 |
| 智能问答 | `/chat`      | RAG 语义问答（轮询结果） |
| 文档上传 | `/upload`       | PDF 批量上传入库（批量轮询进度展示） |
| 个人中心 | `/profile`   | 查看/修改个人信息 |
| 404 | `*`          | 页面不存在提示 |

---

## 🧪 评测与性能压测（eval）

`eval/` 目录提供针对本 RAG 系统的**质量评测**与**性能压测**框架，覆盖七个质量层次与并发/延迟/吞吐性能指标。

### 评测层次（质量评测）

| 模式 | 测什么 | 依赖 |
|------|--------|------|
| `item_confirm` | 商品名确认（`NodeItemNameConfirm`） | Milvus + LLM + MongoDB |
| `eva` | 端到端问答（`/query`） | query_service 已启动 + dataset |
| `embedding` | 向量检索召回（`NodeSearchEmbedding`） | Milvus 有数据 + BGE-M3 |
| `hyde` | HyDE 检索召回（`NodeSearchEmbeddingHyde`） | Milvus + BGE-M3 + LLM |
| `rrf` | 倒排融合（`NodeRrf._rrf_merge`） | 无（离线） |
| `rerank` | 交叉编码器重排（`rerank_documents`） | rerank 服务 |
| `mcp` | 联网搜索（`NodeWebSearchMcp`） | MCP 服务 |
| `all` | item_confirm→eva→embedding→hyde→rrf→rerank→mcp | 全部 |

评测链路紧扣核心：**商品确认 → 三路检索（向量/HyDE/MCP）→ RRF 融合 → Rerank 重排 → 答案生成**。

### 运行方式

必须使用项目 conda 环境 **`shopkeeper-ai`**，Windows 下推荐环境 python 绝对路径 + UTF-8 编码运行：

```bash
set PYTHONIOENCODING=utf-8
# 质量评测（函数调用式，在 eval/run.py 底部 main(...) 指定模式）
D:\ProgramData\anaconda3\envs\shopkeeper-ai\python.exe -m eval.run
# 生成评测数据集（eval/run_test.py）
D:\ProgramData\anaconda3\envs\shopkeeper-ai\python.exe -m eval.run_test
```

**函数调用示例**（在 `eval/run.py` 或 `eval/run_test.py` 底部）：

```python
main(mode="rrf", output_root=r"E:\data_test")                 # RRF 离线评测（默认1条）
main(mode="embedding", limit=10)                               # 向量检索召回10条
main(mode="eva", limit=20)                                     # 端到端前20条
main(mode="all", output_root=r"E:\data_test", limit=5, fresh=False)  # 全部各5条
# 数据集生成
main(size=10, output_root=r"E:\data_test")                     # 采样10条+LLM生成
```

> **条数控制**：`limit` 统一控制评测条数，默认 1 条。
> **熔断机制**：连续失败达 `eva_config.max_consecutive_failures`（默认 3）次自动中断，避免反复调用云服务扣费。
> **断点续跑**：默认启用，逐条落盘快照；`fresh=True` 强制从头重跑。
> 所有评测产物统一保存到 **`E:\data_test`**（`dataset.json`、`*_report.json`、`*_snapshot.json`）。

### 评测指标汇总

| 层次 | 指标 | 说明 |
|------|------|------|
| 商品确认 | `item_hit_rate` / `branch_acc` | 商品名命中率 + 分支准确率 |
| 端到端 | `rouge_l` / `bleu` / `semantic_sim` | 答案与参考答案匹配度 |
| 端到端 | `retrieval_hit_rate` / `item_name_hit_rate` | 检索命中（代理指标） |
| 端到端 | `latency` | avg / p50 / p95 / max |
| 向量检索 | `self_recall@5` / `item_recall@5` / `mrr@5` | 召回质量（embedding/hyde） |
| RRF | `ndcg@3` / `mrr@3` / 跨路优先通过率 | 融合排序质量 |
| Rerank | `ndcg@3` / `mrr@3` / `p@3` | 重排排序质量 |
| MCP | `success_rate` / `field_completeness_rate` / `avg_result_count` | 联网搜索可用性与质量 |

### 性能压测（eval/perf）

`eval/perf/` 提供并发压测与性能基线判定，覆盖接口压测场景、延迟测量与量化标准：

```bash
# CLI 运行性能压测（阶梯加压模式，需 RAG 服务已启动）
python -m eval.perf.run_perf --mode staged --query "如何调节转印温度？" --report perf_report.json
```

- **压测模式**：`staged`（阶梯加压）/ `fixed`（固定并发）/ `duration`（持续时长）
- **性能指标**：吞吐 req/s、P50/P95/P99/P999、avg、max、错误率、抖动（APDE）
- **基线判定**：容量/稳定性/峰值三类基线，输出 PASS / WARN / FAIL，支持与历史报告对比相对提升
- **报告闭环**：性能指标与质量评测（`report.json`）合并输出，形成「性能 + 质量」闭环
