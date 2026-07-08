# AI QC Explain — 项目结构调研报告

## 1. 后端入口和路由结构

- **入口文件**：`backend/app/main.py`
  - `app = FastAPI(title=settings.app_name)`
  - 单层路由：`app.include_router(router)`
  - `router` 来自 `app.api.__init__` → 注册 `app.api.routes.qc.router`
  - 路由前缀统一为 `/api`（在 `qc.py` 的 router 中定义 `prefix='/api'`）

- **路由文件**：`backend/app/api/routes/qc.py`（~1800 行，所有接口集中在一个文件）
  - 包含：healthcheck, login/logout, accounts, task-types, dashboard, database, task-pool, manual-qc, settings, history, bug-reports, qc-tasks 等

## 2. L3 v2 指标数据来源与返回

- **计算引擎**：`backend/app/services/l3_v2/`
  - `engine.py`：L3V2Engine 入口
  - `feature_extractor.py`：特征提取（时间戳、NaN/Inf、维度健康等）
  - `metric_engine.py`：12 项指标计算
  - `quality_engine.py`：Q_motion 融合 + 证据组构建
  - `telemetry_parser.py`：telemetry.npz 解析 + arm_mode 过滤

- **数据结构**：`backend/app/schemas/qc.py`
  - `L3V2MetricResultSchema`：单项指标（metricId, name, score, level, description 等）
  - `L3V2ReportSchema`：完整报告（qualityDimensions, metricResults, timelineSegments 等）
  - `L3V2TimelineSegmentSchema`：异常时间段
  - `ManualQcContextSchema`：manual QC 上下文（含 l3V2: L3V2ReportSchema）

- **构建入口**：`backend/app/services/payloads.py`
  - `manual_qc_context_payload()`：从 episode → telemetry.npz → L3V2Engine → 前端展示
  - `GET /api/manual-qc/{episode_id}/context` → 返回 `ManualQcContextSchema`

## 3. 前端 manual QC 页面数据接口

- **数据获取**：`fetchManualQcContext(episodeId)` → `GET /api/manual-qc/{episode_id}/context`
- **返回结构**：`ManualQcContext` 含 `l3V2: L3V2Report`，其中包含：
  - `trainingQualityScore` / `trainingQualityLevel`
  - `metricResults[]`（12 个指标）
  - `timelineSegments[]`
  - `qualityDimensions[]`
- **前端页面**：`frontend/src/pages/manual-qc.vue`（~1300 行）
  - 评分面板：`l3V2Report` → 各维度展开
  - 异常段标签：`timelineSegments` → 时间线上色
  - 曲线图：`fetchTelemetryCurve` 独立接口

## 4. 最适合新增 AI Explain API 的位置

### 路由
- 在现有 `backend/app/api/routes/qc.py` 末尾新增 `POST /api/ai/explain`
- 或后续如模块增多，可考虑独立 `backend/app/api/routes/ai_qc.py` + register
- **当前选择**：直接在 qc.py 末尾添加，保持简单

### 模块
- 新增独立模块 `backend/app/ai_qc/`，与 `l3_v2/` 同级
- 不修改任何 `l3_v2/` 下的文件
- 通过 `AiExplainRequest` 接收前端传入的 metrics 数据
- 或通过 episodeId 后端自行查询指标（第一阶段用前端传 metrics 的方式）

### 前端
- 在 `manual-qc.vue` 右侧面板中，评分卡片下方新增"AI 解读"卡片
- 加载 episode 时异步请求 `/api/ai/explain`
- 失败不影响页面，卡片显示 fallback 文本

## 5. 集成风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| AI_EXPLAIN_ENABLED 默认 false | 无影响，默认不调用 LLM | 显式配置才启用 |
| Ollama 服务未启动 | API 仍返回 template 解释 | service 层内置 fallback |
| LLM 输出幻觉 | 可能误导质检员 | validator 校验 + 前端 disclaimer |
| AI 解读接口慢 | 页面加载变慢 | 异步请求 + 超时 10s |
| 与现有 QC 接口耦合 | 可能相互影响 | 独立模块，只在路由层添加一个 endpoint |

**结论：集成风险低，可安全推进。**
