# Chip ATE Analysis System

芯片ATE（自动测试设备）数据分析平台，支持 STS8200/STS8300/ETS364 等多种测试机台数据的上传、解析和可视化分析。适用于半导体CP/FT测试数据的快速查看、统计分析和多批次对比。

---

## 功能特性

- **数据上传**：支持 CSV / ZIP 格式，自动识别机台类型（STS8200 / STS8300 / ETS364 / T2K / TMT / LBS）
- **参数分析**：直方图、Scatter散点图、Wafer Map晶圆图、CPK统计、Top Fail分析
- **BIN分析**：Bin Map分布图、良率(Yield)分布图、复测Bin转移分析
- **多LOT对比**：支持多个LOT批次合并与横向对比（参数/Bin）
- **产品管理**：程序名自动匹配产品名，支持自定义映射规则
- **原数据下载**：选中任意LOT，一键打包下载原始CSV/ZIP数据
- **用户认证**：JWT Token 登录/注册，支持管理员模式

---

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端 | Vue 3 + TypeScript + Vite | Vue 3.5, TS 5.9 |
| UI 表格 | AG Grid Community + Vue3 适配 | 35.1 |
| 图表 | ECharts 6 + vue-echarts | — |
| 状态管理 | Pinia 3 | — |
| 后端 | FastAPI + SQLAlchemy 2.0 + Alembic | FastAPI 0.135 |
| 数据库 | PostgreSQL (pgvector 扩展) | — |
| 缓存 | Redis 7 | — |
| 数据处理 | pandas + numpy + scipy + pyarrow | pd 3.0 |
| 部署 | Docker Compose + Nginx | — |

---

## 项目结构

```
ATE_SYS/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # FastAPI 入口，注册所有路由
│   │   ├── core/
│   │   │   ├── config.py    # 环境变量配置（Pydantic Settings）
│   │   │   ├── database.py  # SQLAlchemy 引擎 / Session / Base
│   │   │   └── security.py  # JWT 生成/验证、密码哈希
│   │   ├── models/          # 数据库表结构（User / Lot / TestItem / BinSummary / ProductMapping）
│   │   ├── schemas/         # Pydantic 数据校验模型
│   │   ├── api/routes/      # API 路由
│   │   │   ├── auth.py      # 登录/注册
│   │   │   ├── lots.py      # 上传/列表/删除/合并/下载
│   │   │   ├── analysis.py  # 参数分析 / Bin分析 / WaferMap / 复测分析
│   │   │   └── products.py  # 产品名映射管理
│   │   └── services/
│   │       ├── stats.py     # 统计计算核心（CPK/均值/标准差/Bin汇总）
│   │       └── parsers/     # 数据解析模块（多机台自动识别）
│   ├── migrations/          # Alembic 数据库迁移
│   ├── Dockerfile           # 后端容器镜像
│   ├── entrypoint.sh        # 容器启动脚本（等DB就绪 → 迁移 → 初始化 → 启动）
│   ├── init_db.py           # 初始化默认管理员账户
│   └── requirements.txt     # Python 依赖
│
├── frontend/                # Vue3 前端
│   ├── src/
│   │   ├── api/             # Axios 封装（自动带Token）
│   │   ├── views/           # 页面视图
│   │   │   ├── HomeView.vue         # LOT列表 / 上传 / 下载 / 合并
│   │   │   ├── AnalysisView.vue     # 单LOT参数Top Fail + 统计表格
│   │   │   ├── ParamView.vue        # 单参数深度分析（直方图+Scatter+WaferMap）
│   │   │   ├── BinView.vue          # BIN分析（Bin Map + 复测分析 + Yield Plot）
│   │   │   ├── MultiAnalysisView.vue# 多LOT参数汇总对比
│   │   │   ├── MultiParamView.vue   # 多LOT单参数直方图对比
│   │   │   └── MultiBinView.vue     # 多LOT Bin汇总对比
│   │   ├── router/          # Vue Router
│   │   └── stores/          # Pinia 状态管理
│   ├── Dockerfile           # 前端容器镜像（Node构建 → Nginx托管）
│   └── nginx.conf           # Nginx 配置（反向代理 /api 到后端）
│
├── docker-compose.yml       # Docker Compose 一键部署配置
├── .env.example             # 环境变量模板
├── start_ate.bat            # Windows 本地启动脚本（开发用）
└── stop_ate.bat             # Windows 本地停止脚本（开发用）
```

---

## 数据架构

```
用户上传 CSV/ZIP
    → detector.py 自动识别机台类型
    → acco_parser.py / ets_parser.py 解析数据
    → stats.py 计算统计量（CPK / 均值 / 标准差 / Bin汇总）
    → PostgreSQL 存储统计摘要（lots / test_items / bin_summary）
    → 原始数据保存为 Parquet 文件（高性能按需读取）
```

**核心设计特点**：
- 原始测试数据以 **Parquet** 格式存储，数据库仅保存统计摘要，兼顾查询速度与存储效率
- 支持 `final`（去重保留最后+PASS优先）与 `original`（保留首次）双数据范围
- 坐标去重规则：`(X_COORD != 0) | (Y_COORD != 0)` 才视为有效坐标

---

## 快速开始：Docker 一键部署

### 前置要求

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/ATE_SYS.git
cd ATE_SYS
```

### 2. 启动（零配置一键启动）

```bash
docker-compose up -d
```

> 系统会自动完成：拉取镜像 → 启动数据库 → 执行数据库迁移（Alembic）→ 创建默认管理员账户 → 启动后端和前端。

首次构建可能需要 3~5 分钟，请耐心等待。

### 3. 访问系统

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost:5173 | 主界面，从LOT列表开始使用 |
| 后端 API | http://localhost:8000 | FastAPI 自动文档：http://localhost:8000/docs |
| PostgreSQL | localhost:5432 | 外部连接用（可选） |
| Redis | localhost:6379 | 外部连接用（可选） |

### 4. 默认管理员账户

| 字段 | 默认值 |
|------|--------|
| 用户名 | `admin` |
| 密码 | `admin123` |

> ⚠️ **首次登录后请务必修改默认密码！**

### 5. 停止服务

```bash
docker-compose down
```

如需同时删除数据卷（彻底清空数据库和上传文件）：

```bash
docker-compose down -v
```

---

## 环境变量配置（可选）

系统内置了默认值，开箱即用。如需自定义，请复制模板并修改：

```bash
cp .env.example .env
# 编辑 .env 后重新启动
docker-compose up -d
```

### 可用环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POSTGRES_DB` | `chip_data` | PostgreSQL 数据库名 |
| `POSTGRES_USER` | `admin` | PostgreSQL 用户名 |
| `POSTGRES_PASSWORD` | `chipdata123` | PostgreSQL 密码 |
| `DATABASE_URL` | `postgresql://admin:chipdata123@db:5432/chip_data` | 后端数据库连接串 |
| `REDIS_URL` | `redis://redis:6379` | Redis 连接串 |
| `SECRET_KEY` | `chip-ate-analysis-system-secret-key-2026` | JWT 签名密钥（生产环境务必修改） |
| `APP_ENV` | `production` | 运行环境 |
| `UPLOAD_DIR` | `/app/uploads` | 上传文件存储路径（容器内） |
| `MAX_USER_STORAGE_GB` | `10` | 用户存储配额（GB） |
| `ANTHROPIC_API_KEY` | （空） | Anthropic AI 集成（可选） |
| `DEFAULT_ADMIN_USERNAME` | `admin` | 默认管理员用户名 |
| `DEFAULT_ADMIN_PASSWORD` | `admin123` | 默认管理员密码 |
| `DEFAULT_ADMIN_EMAIL` | `admin@example.com` | 默认管理员邮箱 |

---

## 开发环境搭建（非 Docker）

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 配置环境变量（复制 .env.example 为 .env 并修改）
# 执行数据库迁移
alembic upgrade head
# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器将运行在 http://localhost:5173，通过 Vite 代理自动转发 `/api` 到后端 8000 端口。

---

## 数据存储说明

| 类型 | 存储位置 | 说明 |
|------|----------|------|
| **上传的原始文件** | `UPLOAD_DIR/原始文件名.csv` 或 `.zip` | `lot.storage_path` 记录 |
| **ZIP 解压后的 CSV** | `UPLOAD_DIR/zip文件夹名/xxx.csv` | 解析时自动查找 |
| **解析后的 Parquet** | `UPLOAD_DIR/parquet/lot_{id}.parquet` | `lot.parquet_path` 记录，分析时读取 |
| **数据库数据** | PostgreSQL 容器卷 | Docker Volume `postgres_data` |

> Docker 部署模式下，上传文件存储在容器内的 Volume 中。容器删除后数据不保留（符合本项目设计）。如需持久化，请自行备份 `uploads_data` 和 `postgres_data` 卷。

---

## 主要 API 路由

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| GET | `/api/auth/me` | 获取当前用户信息 |
| POST | `/api/lots/upload` | 上传 CSV/ZIP 文件 |
| GET | `/api/lots` | 查询 LOT 列表（分页/筛选） |
| DELETE | `/api/lots` | 批量删除 LOT |
| POST | `/api/lots/merge` | 合并多个 LOT |
| POST | `/api/lots/download` | 批量下载原始数据（ZIP） |
| GET | `/api/analysis/lot/{id}` | 获取单 LOT 参数统计 |
| GET | `/api/analysis/lot/{id}/bin` | 获取单 LOT Bin 统计 |
| GET | `/api/analysis/lot/{id}/wafer` | 获取单 LOT Wafer Map 数据 |
| GET | `/api/analysis/lot/{id}/param/{param}` | 获取单参数详细分布数据 |
| GET | `/api/analysis/lot/{id}/retest` | 获取复测分析数据 |
| POST | `/api/analysis/multi` | 多 LOT 参数对比 |
| GET | `/api/products/mapping` | 查询产品名映射 |
| POST | `/api/products/mapping` | 新增/更新产品名映射 |
| GET | `/api/products/suggest` | 根据程序名建议产品名 |

完整的交互式 API 文档请在启动后访问：http://localhost:8000/docs

---

## 容器架构

```
┌─────────────────────────────────────────────┐
│               Docker Compose                 │
│  ┌─────────────┐      ┌──────────────────┐  │
│  │  chip_db    │      │  chip_backend    │  │
│  │ PostgreSQL  │◄────►│ FastAPI + Uvicorn│  │
│  │  + pgvector │      │  (port 8000)     │  │
│  └─────────────┘      └──────────────────┘  │
│  ┌─────────────┐              ▲              │
│  │ chip_redis  │              │              │
│  │   Redis 7   │──────────────┘              │
│  └─────────────┘                             │
│  ┌──────────────────────────────────────┐   │
│  │         chip_frontend                │   │
│  │  Nginx (port 5173) + Vue3 构建产物  │   │
│  │  /api/* → proxy_pass → backend:8000 │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

---

## 许可证

MIT License

---

## 致谢

本项目基于 Python + Vue3 生态构建，感谢 FastAPI、SQLAlchemy、ECharts、AG Grid 等优秀开源项目。
