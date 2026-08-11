# 基于 Graph 工作流的高级 RAG 智能知识库系统

本项目是一个基于图工作流架构（Graph-based Workflow）的高级检索增强生成（RAG）系统。系统集成了文档智能解析、多路向量检索、假设性文档生成（HyDE）、联网搜索（MCP）以及多路召回融合与重排序机制，专为企业级复杂知识问答与文档管理场景设计。

---

## 🌟 核心特性

### 1. 自动化文档解析与向量化 (`Import Processor`)
* **PDF 深度解析**：集成 **MinerU** 解析引擎，支持将复杂的 PDF 文档精准转换为标准 Markdown 结构。
* **图片自动管理**：提取 Markdown 中的图片并自动上传至 **MinIO** 对象存储服务，实现图文一体化管理。
* **智能切片与实体识别**：根据语义进行文本 Chunk 切片，并通过大语言模型进行品名/核心实体抽取（Item Name Recognition）。
* **向量存储**：使用 **BGE (如 BGE-M3)** 深度文本嵌入模型生成向量，入库至 **Milvus** 高性能向量数据库。

### 2. 多路召回与重排问答架构 (`Query Processor`)
* **混合检索策略**：
  * **向量检索**：基于 Milvus 的稠密向量近似最近邻搜索。
  * **HyDE (Hypothetical Document Embeddings)**：根据用户提问生成假设性回答，再基于假设回答进行语义检索，提升复杂提问的召回率。
  * **MCP 联网搜索**：整合阿里百炼 MCP 协议，支持补充实时网络搜索结果。
* **RRF 融合与 Reranker 重排序**：
  * 使用 **RRF (Reciprocal Rank Fusion)** 算法合并多路召回的候选文档块。
  * 接入 HTTP **Reranker** 交叉编码器模型对候选结果进行精准二次排序。
* **上下文确认与生成**：结合实体确认（Item Name Confirm）与高相关性上下文，构建 Prompt 生成精准回答。

### 3. 全链路服务与交互
* **流式响应 (SSE)**：后端 API 提供 Server-Sent Events 流式输出，支持问答打字机实时展示效果。
* **对话历史持久化**：使用 **MongoDB** 记录完整的问答会话历史与图上下文数据。
* **前端测试界面**：内置简易而完备的 `import.html`（文档导入测试）与 `chat.html`（知识库对话）页面。

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
├── utils/                    # 基础设施工具库
│   ├── embedding_utils.py    # Embedding 模型调用封装
│   ├── llm_utils.py          # LLM 统一接口
│   ├── mcp_utils.py          # MCP 工具通信
│   ├── milvus_utils.py       # Milvus 数据库增删改查封装
│   ├── minio_utils.py        # MinIO 文件/图片上传管理
│   ├── mongo_history_utils.py# MongoDB 对话历史读写
│   ├── reranker_http_utils.py# Reranker HTTP 交互封装
│   └── sse_utils.py          # SSE 流式数据打包与推流
│
├── web/                      # 服务与前端交互
│   ├── api/                  # 服务接口定义
│   │   ├── import_service.py # 文档导入 API 服务
│   │   └── query_service.py  # 问答检索 API 服务
│   └── page/                 # Web 前端页面
│       ├── chat.html         # 问答对话界面
│       └── import.html       # 文档上传管理界面
│
├── tool/                     # 辅助脚本（模型下载、日志记录等）
└── test/                     # 单元测试与组件测试脚本
```

---

## 🔄 工作流运行机制

### 1. 文档导入处理流 (Import Flow)
```text
node_entry
  └──> node_pdf_to_md (MinerU 解析)
         └──> node_md_img (图片提取与上传 MinIO)
                └──> node_document_split (文本分块)
                       └──> node_item_name_recognition (实体识别)
                              └──> node_bge_embedding (向量化)
                                     └──> node_import_milvus (存储至 Milvus)
```

### 2. 检索问答处理流 (Query Flow)
```text
                            ┌──> node_search_embedding (向量检索) ──────────┐
                            │                                                │
User Query ──> [多路并行] ──┼──> node_search_embedding_hyde (HyDE 检索) ──────┼──> node_rrf ──> node_rerank ──> node_answer_output
                            │                                                │
                            └──> node_web_search_mcp (MCP 联网搜索) ─────────┘
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
* `LLM_*`：大语言模型 API 密钥与 Endpoint

### 2. 启动服务
确保依赖组件（Milvus, MinIO, MongoDB, BGE/Reranker 服务）已成功启动后，运行 API 服务：
```bash
# 启动问答服务与文档导入服务
python -m web.api.query_service
python -m web.api.import_service
```

### 3. Web 交互测试
* 在浏览器中打开 `web/page/import.html` 即可上传并解析导入 PDF / Markdown 文档。
* 打开 `web/page/chat.html` 即可开始基于知识库的流式问答对话。