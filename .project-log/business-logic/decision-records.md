### 2026-07-18 — 数据标注模块 V1 业务逻辑固化（历史初稿，已由最终收口覆盖冲突项）

- Decision: 数据标注模块正式纳入平台 pipeline，按 TaskType 聚合数据（不引入标注批次），VLM 自动标注 + 人工标注双路径共享同一份标注结果模型，标注资格只读 `Episode.final_dataset_status = 'QUALIFIED'`，不与质检耦合。
- Context: 平台已完成采集 → 扫描入库 → 质检 → 导出的 pipeline，缺失数据标注环节。已调研 LeRobot、Label Studio、RoboInter 三个开源方案（2026-07-14，`.project-log/标注工具调研.md`），决定自研标注模块（复用 Vue 3 + FastAPI 架构），由 VLM（Qwen3-VL-32B，已部署 Ollama）生成预标注，人工检查修改。
- Alternatives considered:
  - 集成 Label Studio：多用户标注平台成熟，但需写导入导出适配器，无法深度集成到现有 Vue 3 前端
  - 直接使用 LeRobot `lerobot-annotate`：License 不明确、字段体系不一致、前提要求 LeRobot 格式
  - 自研标注模块：与现有架构完全一致，复用 MinIO 媒体访问、AI 模块、角色权限体系，成本可控
- Reason: 自研方案（IV）最符合当前架构。V1 范围最小可用——不做 SAM2 分割、双人审核、像素级标注。内部模型 → 导出转换器 → LeRobot 格式，数据库不绑定外部格式。标注与质检通过 `final_dataset_status` 单向依赖，标注不能反向改变质检状态。
- Implementation detail:
  - 正式数据对象：
    - `annotation_tasks`：标注工作流状态（work_status / generation_status）
    - `episode_annotations`：每个 Episode 唯一标注结果（UNIQUE episode_id）
    - `annotation_segments`：子任务段标注
    - `annotation_ai_runs`：VLM 生成记录
  - 资格判据：`Episode.final_dataset_status = 'QUALIFIED'`（单一字段，不复算质检逻辑）
  - 三状态计算：未标注（无任务）/ 待标注（work_status=pending）/ 完成标注（work_status=completed）
  - VLM 双路径：initial_source=vlm（VLM 生成草稿） / manual（人工从零标注），human_modified 区分是否人工修改
  - 角色：新增 annotator 角色，纳入现有权限体系
  - 导出：Robot QC JSON（内部格式）+ LeRobot 通过转换器适配
  - 训练集导出条件：`final_dataset_status = 'QUALIFIED' AND work_status = 'completed'`
- Full spec: `.project-log/business-logic/annotation-v1.md`

### 2026-07-18 — 数据标注模块 V1 补充决策（6 项）

- Decision: 对标注 V1 设计中的 6 个待定问题作出最终决策：
  1. **删除 `is_finalized`**：以 `annotation_tasks.work_status = 'completed'` 为唯一完成判据，避免双重事实源
  2. **Revision 机制**：草稿阶段直接 UPDATE `episode_annotations`，每次确认完成生成 `annotation_revisions` 不可变快照
  3. **JSONB Schema 固定**：`instruction_variants_en` 为 `string[]`，`objects` 含 `name_en/name_zh/role(枚举)/attributes`，三段校验（Pydantic → 业务 → DB），记录 `annotation_schema_version`
  4. **不复用 AI 聊天面板**：V1 提供结构化 AI 操作按钮（重新生成/检查），不采用自由对话式面板
  5. **编辑锁 + 乐观锁**：`lock_owner` + 心跳续期（30s）防止多人同时编辑，`row_version` CAS 防止覆盖
  6. **VLM 三阶段抽帧**：均匀采样 + telemetry 事件检测（motion_score 局部峰值）+ 子任务边界局部密集抽帧细化，三路视频拼接为组合图
- Full spec: `.project-log/business-logic/annotation-v1.md`

### 2026-07-18 — 数据标注模块 V1 最终收口（稳定实施版本）

- Decision: 标注 V1 不再保留未决实现边界。可用池固定为 `final_dataset_status = QUALIFIED` 加既有 `active_list_active_batch_indexed_episodes`；Episode 分组固定以 `Batch.task_type_id` 为准；VLM 采用独立持久化队列和单 GPU worker；标注统计采用持久化 TaskType rollup；训练集导出冻结 revision 快照。
- Reason: 这些规则与项目已经冻结的 active scope、持久化 worker、资产 rollup、导出审计模式一致。它们避免了失效数据进入标注、单角色权限模型冲突、FastAPI 内存任务丢失、人工草稿被 AI 静默覆盖，以及重新编辑后训练集无法追溯的问题。
- Implementation detail:
  - `annotation_tasks` 保存 work_status、资格失效前状态、锁、任务归属和完成者；generation 生命周期从 task 移到 `annotation_generation_jobs`。
  - 草稿 `episode_annotations` 允许内容不完整；完成时才执行严格校验并创建不可变 `annotation_revisions`。
  - V1 不新增 `annotator` 单角色，既有 reviewer 具有本人标注编辑/完成权限，manager/admin 管理任务和导出。
  - 新增 `task_annotation_rollups` / `annotation_recompute_jobs` 和 `dataset_export_items`，分别承载首页统计与导出 revision 快照。
  - 初始 VLM 标注可自动写入空白草稿；所有重生成结果必须先展示候选差异，再由用户显式应用。
- Full spec: `.project-log/business-logic/annotation-v1-final-decisions.md`

### 2026-07-20 — 统一质检合格数据导出与标注增强字段

- Decision: 训练数据集管理页面与 API 保持一套“质检合格数据导出”能力。导出范围固定为 active scope 中全部 `final_dataset_status = QUALIFIED` Episode；标注完成不是第二道导出门禁，而是每条 Episode 随同导出的可选增强信息。
- Context: 旧文档把“普通数据导出”和“带标注训练集导出”描述为两类产品能力，但现有页面、接口和用户操作均只有一套导出入口。直接把既有导出接口收紧为“必须完成标注”会破坏数据盘点、迁移和非语言训练的既有用途；拆成两个入口则会使同一 QC 合格资产出现不必要的双重产品概念。
- Reason: 以 QC 合格 Episode 作为唯一资产集合，标注作为可追溯增强字段，既保留统一资产视图，也允许下游训练按标注状态、outcome 与 Schema 精确过滤。未完成标注的数据不会被误丢弃，已完成标注的数据也不会与基础资产分离。
- Implementation detail:
  - 页面核心卡片显示“质检合格 / 完成标注”及标注覆盖率；表格增加是否完成标注和可诊断状态。
  - 统一导出包含全部 QC 合格 Episode。未完成项输出基础 QC/资产信息以及 `annotation_completed=false`；完成项输出 immutable revision、Schema、payload、`task_outcome` 和 `training_default_included`。
  - `failed` 默认进入训练子集；`uncertain` 视为完成标注但默认不进入训练子集，需下游显式选择。
  - 导出使用 `DatasetExportJob` + `dataset_export_items` 固化所有 Episode 的当时快照；完成标注项绑定 revision 与 Schema，未完成项保存状态及空标注引用。`filters_json` 仅保存筛选条件。
  - 训练主产物为 JSONL 数据包及 manifest/Schema 快照；CSV 作为人工审计格式；LeRobot 通过转换器适配。
- Alternatives considered:
  - 将既有导出直接收紧为仅已完成标注：拒绝，会破坏普通 QC 合格数据用途。
  - 将普通导出和带标注导出拆成两个用户入口：拒绝，当前产品采用统一资产集合和单入口导出。
- Impacted nodes: D2、G、E
- Status: active; implementation pending

### 2026-07-18 — VLM 初始标注改为后台流水线默认触发

- Decision: 新合格 Episode 不再等待 reviewer 逐条点击“自动标注”。后台按固定周期扫描满足资格且尚无初始 generation job 的 Episode，默认在北京时间午夜后的低峰窗口按 TaskType 批量创建初始 VLM job。`admin` / `qc_manager` 可按 TaskType、Batch 或筛选范围手动批量启动、补漏、失败重试和重跑；reviewer 仅可对本人工作池批量补漏，不承担逐条启动职责。
- Reason: 自动标注的价值是把人工工作从“等待模型生成”转为“审核和微调”。逐 Episode 手动触发会把流水线责任转嫁给标注员，增加等待成本并降低 GPU 利用效率。
- Constraints: 后台扫描必须幂等；同一 Episode 已存在 annotation task 或 active/succeeded 初始 job 时不得重复创建。夜间调度、手动批量触发和 reviewer 补漏都必须进入同一个持久化 generation queue，不能绕过 worker 直接调用 VLM。初始成功结果可写入空白草稿，已有草稿或完成任务的重生成只能产生候选，须人工显式应用。
- Full spec: `.project-log/business-logic/annotation-v1-final-decisions.md` §5.2

### 2026-07-18 — 标注任务派发、人工接管和异常协作收口

- Decision: 管理员批量派发是 V1 的标准人工工作入口；reviewer 仅能从管理人员显式开放、初始 VLM 已成功的公共池原子领取。无预标注任务必须在单独的从零标注池派发，并显示原因和二次确认。任务归属与编辑锁严格分离；退回、强制改派、从零标注原因和 reviewer 异常上报均需持久化审计。
- Reason: 标准派发保证 reviewer 默认面对可审核的 VLM 草稿，公共池补充避免管理端成为瓶颈；独立的无预标注路径避免高人工成本任务被无提示混派。保留 VLM 失败来源和协作异常历史，才能追溯自动化质量、人工成本和数据问题。
- Implementation detail:
  - `annotation_tasks` 增加派发、退回和 `manual_from_scratch_reason` 字段；分配/领取/改派使用不可变审计事件。
  - `initial_source` 永不回写。VLM 失败转人工保留 `vlm`，原因写为 `vlm_failed`。
  - 新增 `annotation_task_escalations`，承接 data/task type/VLM/blocked 等正式上报，不能仅用自由备注。
  - `editing`、`returned`、`exported` 是读模型标签，分别由有效锁、退回审计和 export item 推导，不污染 `work_status`。
- Full spec: `.project-log/business-logic/annotation-v1-final-decisions.md` §5.3–§5.7

### 2026-07-18 — Sub Goal Schema 主语义与失败样本收口

- Decision: 废除 Episode 自由 Segment 作为 V1 训练主语义。TaskType 通过版本化 `sub_goal_schemas` / 固定 `sub_goal_definitions` 定义标签空间；annotation task 冻结 Schema，Episode 只保存固定 Definition 的多次 occurrence、状态、时间范围、代表帧与失败信息。`task_outcome` 取代 `execution_observation`，并与 `final_dataset_status` 分离。
- Reason: 自由标签无法保证同 TaskType 的训练语义稳定，也使 VLM 和人工产生不可统计的命名漂移。固定 Schema 可让 VLM 专注时间对齐、让 reviewer 专注边界修正，并保留抓取重试等多次 occurrence。数据质量合格但任务失败的数据应被保留为失败训练样本，而不是被质量状态隐式丢弃。
- Migration boundary: 当前 `MANUAL_FAIL → UNQUALIFIED` 混合了质量与任务失败。新规则只适用于实现拆分 QC 判据后产生或经明确质量复核的数据；既有 UNQUALIFIED 不自动迁移或进入标注/导出。
- Full spec: `.project-log/business-logic/annotation-sub-goals-v1.md`

### 2026-07-16 — 任务级数据资产画像长期路线：Route T2（收敛实现）

- Decision: 在已落地的 Route C' 之上，数据总库正式新增 **任务级资产画像**。长期路线采用 **Route T2：新增 `task_asset_rollups` 任务级派生投影 + `task_asset_recompute_jobs` 持久化 dirty/recompute 队列**；任务投影只从 `batch_asset_rollups` 汇总，不回扫 `episodes`，也不让前端按批次临时求和。
- Context: 数据总库当前已有 Episode 明细视角与 Batch 资产画像视角；产品需要第三个 Task 视角，直接回答“某个任务下有多少 batch/episode、多少可用/不可用、多少未完成、合格率多少、总时长/总帧数多少”。现有 `task_types.total_batches/total_episodes` 与 `/api/dataset/tasks/*` 的 task summary 都不足以承担长期资产画像职责：前者只是粗计数且刷新不可靠，后者偏训练消费语义且走 Python 实时聚合。
- Alternatives considered:
  - 方案 T0：请求时对 `episodes` 做 `GROUP BY task_type`
  - 方案 T1：请求时对 `batch_asset_rollups` 实时聚合，不建任务投影表
  - 方案 T2：新增 `task_asset_rollups` + 任务级 dirty/recompute
  - 方案 T3：把更多统计字段继续堆进 `task_types`
  - 方案 T4：直接上 Kafka / ClickHouse / 外部 OLAP
- Reason:
  - T0 会重复 Route C' 已否决的实时扫明细主路径，后续规模增长后必然退化
  - T1 短期可用，但 task 视图后续必然需要按可用率/时长/帧数排序筛选，并独立表达 freshness；继续只靠读时 group by 会重新把压力推回查询层
  - T3 会把业务主数据与分析状态混在 `task_types`，与 Route C' 已拒绝“把统计堆进业务表”的原则冲突
  - T4 对当前规模过重
  - T2 最符合现有 Route C' 结构：batch 投影继续做权威聚合基座，task 投影只做其上的二级读模型
- Implementation detail:
  - 正式数据对象：
    - `task_asset_rollups`：任务级可重建统计投影，`task_type_id` 作为主键/唯一键
    - `task_asset_recompute_jobs`：按 `task_type_id` 粒度持久化 dirty/recompute 请求；同一 task 的 pending/running 请求合并，不无限堆积
  - 正式聚合链路固定为：
    ```text
    episodes
      -> batch_asset_rollups
      -> task_asset_rollups
      -> GET /api/data-assets/tasks
    ```
  - 全局 summary 继续由 `batch_asset_rollups` 求和生成，不改成从 task rollup 汇总，避免多一层 stale 传播
  - 统一统计作用域继续固定为 `active_list_active_batch_indexed_episodes`；task / batch / global 三层不得使用不同 active scope
  - 最终可用性主口径固定为 `final_dataset_status`：
    - available = `QUALIFIED`
    - unavailable = `UNQUALIFIED`
    - pending = `PENDING`
  - 人工质检辅口径固定为 `manual_qc_status`：
    - reviewed = `MANUAL_PASS + MANUAL_FAIL`
    - not_reviewed = `NOT_REVIEWED`
    - manual_pass / manual_fail 分开计数
  - 比率口径：
    - `final_qualified_rate = QUALIFIED / (QUALIFIED + UNQUALIFIED)`；分母为 0 时返回 `null`
    - `manual_pass_rate = MANUAL_PASS / (MANUAL_PASS + MANUAL_FAIL)`；分母为 0 时返回 `null`
    - 比率不物理存储，由 API 读取计数字段后计算
  - `not_reviewed_count` 与 `pending_dataset_count` 必须拆开，不得合并成模糊字段
  - 时长/帧数严格从子 batch rollup 求和，并继续暴露 covered/missing episode count；纯 raw 无 processed manifest 的 0 值是合法缺失，不得伪造
  - 投影层可存：batch_count、episode_count、reviewed/not_reviewed、manual pass/fail、qualified/unqualified/pending、duration/frame 及其 covered/missing、sampled_episode_count、accepted/rejected/pending batch count、source watermark、calculation_version、refreshed_at
  - 投影层不存：task name/description/arm_mode/is_active 等主数据；这些仍从 `task_types` join
  - dirty 触发：
    - episode/batch 事实变化先走既有 batch recompute
    - batch rollup 成功后 mark 父 task dirty
    - batch 改挂 task 时，必须同时 dirty 旧 task 与新 task
    - list active/inactive、batch active 变化、手动 rebuild 也触发相关 task dirty
  - 任务重算以“整任务重算”为默认策略；若目标 task 下仍有 pending/running 的 batch job，应延迟/重试，避免汇总半更新状态
  - 正式 API 边界：
    - `GET /api/data-assets/tasks`
    - `GET /api/data-assets/tasks/{task_type_id}`
    - 扩展既有 `POST /api/data-assets/rebuild` 支持 batch/task/all 范围
  - 前端 `数据总库` 正式三视角：
    1. Episode 明细
    2. Batch 资产
    3. Task 资产
  - 钻取链路固定为：Task → Batch（带 taskTypeId 过滤）→ Episode
  - `task_type:unclassified` / `待分类` 必须始终可展示；默认列表优先 active task，但待分类不得被隐藏
  - `task_types.total_batches` / `total_episodes` 进入废弃流程：停止新增依赖 → 资产接口切换到 task rollup → 兼容观察 → 再删列
  - 实现风格对齐现有 Route C'：优先 `task_type_id` 主键、字符串 calculation_version、job 表承载 dirty/recompute，不另起更重的工作流引擎
  - 任务层 calculation_version 独立为 `task-asset-rollup-v1`，不与 batch 层共用同一常量
- Impacted nodes: D, D2
- Status: implemented (unit-tested; live migration/rebuild pending)

### 2026-07-15 — 数据总库长期架构升级路线：Route C'

- Decision: 数据总库的“总体资产统计 + 批次级资产画像”正式采用 **Route C'：显式 Batch–List 关系 + 批次级派生投影 + PostgreSQL 持久化重算队列 + 周期性对账**。这条路线作为后续代码改造的正式业务逻辑边界，不再继续把资产画像能力塞进现有 Episode 明细接口，也不把越来越多的统计字段直接堆进 `batches`。
- Context: 当前平台已经形成三层稳定结构：1）MinIO 控制面事实层（`lists / episode_inventory / episode_objects`）；2）业务实体层（`batches / episodes`）；3）QC 与训练消费层（`qc_tasks / qc_review_revisions / batch_decision_log`）。在这个基础上，数据总库新增的总量卡片和批次画像本质上属于读模型/统计投影，不再适合继续依赖实时 Episode 聚合或继续扩张 `batches` 表语义。
- Alternatives considered:
  - 方案 A：继续基于 `episodes` 实时 `GROUP BY` 聚合，按请求即时计算 summary 和 batch 画像
  - 方案 B：把总时长、总帧数、覆盖率等画像字段直接冗余到 `batches`
  - 方案 C：事实表 + 显式关系 + 独立统计投影 + dirty 重算机制
- Reason:
  - 方案 A 在当前数千 Episode 规模下也许可用，但随着后续增加时长/帧数/模态覆盖/标注覆盖/L3 分布等维度，会反复扫描大量明细，且 summary 与 batch 列表容易出现统计口径漂移
  - 方案 B 虽然查询便宜，但会把 `batches` 变成混合了业务状态与分析状态的膨胀实体，不利于后续扩展和对账修复
  - 方案 C' 最符合当前代码形态：保留现有控制面/业务面/消费面事实源，新增可重建的派生投影层，既保证页面读性能，又不破坏原始业务事实
- Implementation detail:
  - `batches.list_id` 作为正式的 Batch–List 显式关系字段落到业务模型中，但第一阶段采用 **可空字段 + 历史回填验证 + 兼容观察 + 再决定是否收紧为非空**，不直接假设历史数据全部可唯一映射
  - 批次级派生统计投影的正式实体固定为 `batch_asset_rollups`，仅保存可确定性重建的聚合结果，例如：`episode_count`、`total_duration_sec`、`duration_covered_episode_count`、`duration_missing_episode_count`、`total_frame_count`、`frame_covered_episode_count`、`frame_missing_episode_count`、`sampled_episode_count`、`reviewed_count`、`manual_pass_count`、`manual_fail_count`、`qualified_count`、`unqualified_count`、`pending_dataset_count`、`last_episode_updated_at`、`source_watermark`、`calculation_version`、`refreshed_at`
  - 第一版**不复制**这些业务状态字段进投影表：`task_type_id`、`batch_name`、`qc_status`、`batch_decision`、`reject_threshold`、`failure_rate`；这些字段仍以 `batches` 或关联维表为准，投影层不生成新的权威口径
  - 顶部总览不单独建全局总表；第一版直接对 `batch_asset_rollups` 求和，确保 summary 与 batch 列表使用完全一致的作用域
  - 统计作用域正式固定为：**active list + active batch + indexed business episodes**，内部统一标识为 `active_list_active_batch_indexed_episodes`。不允许顶部卡片与 batch 列表采用不同过滤口径
  - `duration_sec` 与 `frame_count` 的权威来源固定为扫描阶段持久化到 PostgreSQL 的 manifest 派生字段；其中 `frame_count` 定义为 manifest 声明的 episode 级帧数，不做多相机视频帧总和。覆盖规则固定为：`duration_sec > 0` 视为有效时长，`frame_count > 0` 视为有效帧数
  - PostgreSQL 持久化 dirty/recompute 队列的正式实体固定为 `batch_asset_recompute_jobs`；同一 batch 的重算请求按 `batch_id` 合并，worker 以 batch 粒度执行**整批重算**，而不是做分散的 `+1/-1` 增量计数
  - dirty 触发的核心事实变化包括：Episode 新增/移出作用域、`duration_sec`/`frame_count` 修改、`batch_id` 变更、人工 QC 结果变更、最终数据集状态变更、Batch–List 关系变更、List active/inactive 状态变更、管理员手动重建
  - 周期性对账任务作为低频兜底链路，负责发现漏标记、漏重算和统计漂移；投影层可以重建，但不能反向替代业务事实源
  - 数据资产读路径正式拆分为独立 API：`/api/data-assets/summary`、`/api/data-assets/batches`，并保留管理员手动全量重建入口；现有 `/api/database` 继续维持 Episode 明细浏览语义，不再作为长期聚合主路径
  - 迁移顺序固定为：阶段 0 冻结统计口径与实时基线 SQL → 阶段 1 新增 `batches.list_id` 并回填 → 阶段 2 建立 `batch_asset_rollups` 与全量重建能力 → 阶段 3 引入 `batch_asset_recompute_jobs` 与自动重算链路 → 阶段 4 新增独立 API → 阶段 5 前端接入 → 阶段 6 切换与验收 → 阶段 7 清理兼容逻辑
  - 统计能力正式上线前，必须先确认 manifest 派生字段在扫描链路中可稳定写库，避免时长/帧数基线不可信
- Impacted nodes: D, D2
- Status: confirmed

### 2026-07-10 — QC 任务池拆分 + admin 可直接接管 done 任务

- Decision: reviewer 的人工质检入口正式拆分为“我的任务清单（当前可处理任务）”与“历史任务清单（已完成历史记录）”；同时允许 admin 直接认领 `done` 状态任务，认领动作语义定义为 **reopen + ownership transfer**，而不是新增独立 admin 审批入口
- Context: 当前 reviewer 任务池把 `done` 任务也混在当前列表中，导致已完成数据仍可重新进入质检；同时产品希望避免为 admin 增加额外按钮和独立流程，保持最高权限角色可直接处理异常任务
- Alternatives considered:
  - 方案 A：所有角色统一走“申请重新质检 → 审批 → 新建复检任务”
  - 方案 B：admin 直接接管 `done` 任务；reviewer 通过历史池入口申请重新质检
- Reason:
  - 方案 A 审计更严谨，但对 admin 来说链路过长、交互复杂
  - 方案 B 更符合“admin 最高权限”的产品直觉，同时仍可通过严格后端状态机避免双重归属和历史污染
- Implementation detail:
  - reviewer 当前任务池：`is_active=1 AND assignee=当前 reviewer AND status in ('assigned','in_review')`
  - reviewer 历史任务池：按 reviewer 的已完成历史记录 / revision 展示，不再让 `done` 混入当前任务池
  - reviewer claim 仅允许：active + assigned + assignee=本人 + 无他人有效锁
  - admin claim 允许：active + `status in ('new','assigned','done')`，但若他人 `in_review` 锁有效则禁止接管
  - admin 认领 `done` 时，必须原子执行：`task.done -> in_review`、切换 assignee/lock owner、`episode.done -> in_review`、`episode.qc_result -> pending`、`manual_qc_status -> NOT_REVIEWED`、保留旧 revision 并等待新提交追加 revision
  - `release` 禁止对 `done` 生效；`submit` 禁止回退提交非 active task
  - 新增 `QcRereviewRequest` 模型，reviewer 历史卡可提交申请，admin/qc_manager 通过 `rereview-approvals` 页面审批，审批通过后复用原 task reopen（不回退新建 task）
- Impacted nodes: D
- Status: implemented

### 2026-07-10 — D2 导出增强 + admin 任务管理补强（补充记录）

- Decision: 在已确认的批次驳回主流程之外，补齐训练数据导出的关键字段、管理员任务管理能力，以及前端状态原因展示所依赖的配套结构，作为 D2 的配套增强项纳入正式业务记录。

- Context: v1.0 批次驳回模块已落地。实际使用中发现导出字段不够丰富（缺少 MinIO 路径和 L3 分数）、管理员无法回收卡住的任务（质检员请假等场景）、前端缺少状态判定原因展示
- Reason: 下游训练团队需要 MinIO 路径信息来定位原始数据；管理员需要任务管理权限来处理异常情况（请假、负载不均、错误派发）；质检员需要看到"为什么这条 episode 不能用于训练"
- Implementation detail:
  - 导出新增字段：task_type_id/name, l3_training_quality_score, motion_quality_score, learnability_score, data_integrity_score, execution_diagnostic_score, minio_raw/processed_prefix, telemetry/metadata/manifest_path, video_paths, reviewer_id, qc_result_id, created_at, uploaded_at, qc_completed_at
  - 新增 DatasetExportJob 表
  - 新增 TaskOperationLog 表（revoke/reassign/release/force_release）
  - 新增 API: GET/POST admin 任务管理端点
  - MQ-02 Hand Action Continuity 和 DX-01 真正 Lag Alignment 标记为技术债，本版本暂不实现
- Impacted nodes: D2
- Status: active

### 2026-06-29 — 批次驳回失败率分母：抽检数 vs 批次总数

- Decision: 批次驳回判定中的失败率分母采用**抽检数**（\(N_{sampled}\)），而非批次总数（\(N_{batch}\)）
- Context: LaTeX 设计文档初版使用 \(R_{fail} = N_{fail}^{manual} / N_{batch}\)。用户指出这会在抽检比例较低时严重稀释失败率信号。例如批次 100 条、抽检 25 条、发现 12 条不合格：按总数算是 12%，不触发 10% 阈值；按抽检数算是 48%，明显应驳回
- Reason: 抽检本身就是对批次质量的统计推断。如果抽检 25 条就查出 12 条不合格，这批数据质量大概率很差，应驳回重采。用抽检数做分母使失败率对抽检结果更敏感，不会因为"分母很大而掩盖高密度的失败"
- Implementation detail:
  - 公式：\(R_{fail} = N_{fail}^{manual} / N_{sampled}\)
  - 驳回条件：\(R_{fail} > \theta\)（默认 \(\theta = 0.10\)，可在设置页"通用"tab 中调整）
  - 等于阈值时不驳回
  - 驳回阈值因为分母变小，默认值 0.10 可能在实践中偏严，后续需根据真实数据校准
- Impacted nodes: D2
- Status: active

### 2026-06-25 - L3 V1 指标公式、阈值语义与 timeline 触发规则正式细化

- Decision: L3 V1 在实现级别进一步细化为“episode-level 指标卡片 + segment-level 时间窗告警”双输出结构。每个指标必须同时定义：1）输入字段；2）预处理；3）公式口径；4）阈值语义；5）是否进入 timeline；6）中文展示名。所有阈值在 V1 中先采用**保守经验阈值 + 样本分布辅助**策略：明显异常优先抓出，宁可提示偏多，也不追求第一版就做出严格的统计学最优阈值
- Context: 前一版决策已经收口了 P0/P1/P2 指标分档，但还缺少真正能指导代码实现的细节：例如 Dead Actions 中的 ε 怎么设、Action Saturation 对 arm/hand 如何分边界、Tracking Error 用 mean/p95 还是全局 max、哪些指标要产出 timelineSegments 等。如果不把这些细节写死，代码落地时仍会回到“临时拍脑袋”
- Reason: manual QC 的核心诉求不是学术论文复现，而是“给质检员一个可信、可解释、可定位时间段的 L3 自动提示层”。因此指标定义要以“可解释 + 可调 + 能定位异常段”为先，而不是先追求最复杂公式
- Implementation detail:

  **统一输入预处理**
  1. 从 `processed/telemetry.npz` 读取：`timestamps`, `qpos`, `qvel`, `actions`, `effort`, `sync_validation_is_valid`, `sync_validation_max_diff`
  2. `timestamps` 转换为相对秒：`t_rel = timestamps - timestamps[0]`
  3. 维度拆分：
     - `arm_dims`: 机械臂关节维度（弧度制）
     - `hand_dims`: 灵巧手关节维度（0~255）
  4. 手部归一化：`actions_hand_norm = actions_hand / 255.0`，`qpos_hand_norm = qpos_hand / 255.0`
  5. 所有 arm/hand 相关指标优先分别计算，再根据“worst-case / mean”聚合为 episode 级卡片值

  **P0 必做 6 项细则**

  1. `LDLJ 平滑度`
     - 输入：`qpos[:, arm_dims]` 或 `actions[:, arm_dims]`，默认以 `qpos` 为主、`timestamps` 定义时长
     - 公式：沿 Forge/DQAF 口径，使用 dimensionless jerk / LDLJ 评分；输出归一到 0~10，分数越高越好
     - 阈值语义：
       - `good >= 7.0`
       - `warn 5.0 ~ 7.0`
       - `bad < 5.0`
     - timeline：**不直接产 segment**。LDLJ 作为整条轨迹平滑度总分，不直接定位到时间窗
     - 展示：`平滑度 LDLJ*`

  2. `Dead Actions / 无效动作占比`
     - 输入：`actions[:, arm_dims]` 与 `actions_hand_norm[:, hand_dims]`
     - 口径：
       - arm dead: `mean(all(|a_arm| < ε_arm))`
       - hand dead: `mean(all(|a_hand_norm| < ε_hand))`
       - episode 值取 `max(arm_dead, hand_dead)`，保证最差子系统能暴露出来
     - 初始阈值：
       - `ε_arm = 0.01 rad`
       - `ε_hand = 0.02`（归一化后）
     - 阈值语义：
       - `good < 10%`
       - `warn 10% ~ 25%`
       - `bad > 25%`
     - timeline：**是**。连续 `all(|a| < ε)` 的窗口段进入 `stall / 停滞` segment
     - 展示：`无效动作占比`

  3. `Action Saturation / 动作饱和率`
     - 输入：`actions[:, arm_dims]`, `actions[:, hand_dims]`
     - 口径：
       - arm saturation：动作值接近关节物理上下界的比例（首版按 qpos/actions 的观测分布估计上限，后续再替换成正式 joint limit 表）
       - hand saturation：手部值接近 `0` 或 `255` 的比例
       - episode 值取 `max(arm_sat, hand_sat)`
     - 首版手部阈值：`a_hand <= 3 or a_hand >= 252` 视为饱和
     - 首版机械臂阈值：先按该 episode 中 arm `qpos`/`actions` 的 1% / 99% 分位附近 + 固定 margin 检测近边界风险，后续若拿到正式 limit 表再替换
     - 阈值语义：
       - `good < 3%`
       - `warn 3% ~ 8%`
       - `bad > 8%`
     - timeline：**是**。连续 saturation 命中段进入 `动作饱和` segment
     - 展示：`动作饱和率`

  4. `Static Detection / 停滞占比`
     - 输入：`actions[:, arm_dims]`, `actions_hand_norm[:, hand_dims]`, 可选结合 `qvel`
     - 口径：与 Dead Actions 不同，停滞强调“持续时间窗”。以滑动窗口（建议 0.5s）统计窗口内平均动作幅值和速度幅值是否同时低于阈值
     - 初始阈值：
       - arm: `mean(|a_arm|) < 0.01` 且 `mean(|qvel_arm|) < 0.01`
       - hand: `mean(|a_hand_norm|) < 0.02`
     - 阈值语义：
       - `good < 8%`
       - `warn 8% ~ 20%`
       - `bad > 20%`
     - timeline：**是**。停滞窗口直接进入 `停滞` segment
     - 展示：`停滞占比`

  5. `Timestamp Regularity / 时间戳抖动`
     - 输入：`timestamps`
     - 公式：`dt = diff(t_rel)`，`jitter_ratio = std(dt) / mean(dt)`
     - 阈值语义：
       - `good < 0.02`
       - `warn 0.02 ~ 0.05`
       - `bad > 0.05`
     - timeline：**否**。这是整条序列采样时序稳定性指标，不产 segment
     - 展示：`时间戳抖动`

  6. `Qpos-Action Tracking Error / 跟踪误差`
     - 输入：`qpos`, `actions`（arm/hand 分开；hand 先归一化）
     - 口径：
       - 当前状态 vs 目标命令逐帧绝对差
       - episode 卡片值取 `p95`
       - arm 和 hand 分开算后取 weighted max（arm 权重大于 hand）
     - 初始权重：`arm 0.7`, `hand 0.3`
     - 阈值语义：
       - `good < 0.12`
       - `warn 0.12 ~ 0.20`
       - `bad > 0.20`
       - 若继续沿现有原值空间展示，则前端显示需要转换为“归一化误差”中文说明，避免不同量纲误导
     - timeline：**是**。逐帧误差超过 `warn_threshold` 的连续窗口进入 `跟踪误差` segment
     - 展示：`跟踪误差`

  **P1 增强 2 项细则**

  7. `Per-finger Gripper Chatter / 手指颤振`
     - 输入：`actions[:, hand_dims]`
     - 口径：每个手指维度先二值化或差分阈值化，再计算 transitions/sec；episode 值取 `finger_max`，辅助值可保留 `finger_mean`
     - 初始阈值：`> 2 transitions/sec` 视为高 chatter
     - 阈值语义：
       - `good < 1.0/s`
       - `warn 1.0 ~ 2.0/s`
       - `bad > 2.0/s`
     - timeline：**是**。chatter 高发窗口进入 `手指颤振` segment
     - 展示：`手指颤振`

  8. `Joint Effort / 执行力度`
     - 输入：`effort[:, arm_dims]`（如手部无 effort 则只对 arm）
     - 口径：首版卡片值用 `p95(abs(effort))`；后续若要更敏感可增加积分 `sum(abs(effort))*dt` 作为后台排序特征
     - 阈值语义：
       - `good < 0.9`
       - `warn 0.9 ~ 1.5`
       - `bad > 1.5`
     - timeline：可选。V1 首版**不强制进 timeline**，避免时间窗过多；若后续发现高 effort 与异常动作高度耦合，再加 `高负载` segment
     - 展示：`执行力度`

  **Timeline 统一规则**
  - 仅从能提供时间定位的指标生成：`跟踪误差`、`停滞`、`动作饱和`、`手指颤振`，以及平台已有 `sync_validation_max_diff` 导出的 `同步异常`
  - 生成规则：逐帧命中 → 最小持续时长 `>= 0.5s` → gap merge `<= 0.3s` → 中文标签输出
  - V1 segment 标签固定为：`同步异常`、`跟踪误差`、`停滞`、`动作饱和`、`手指颤振`
  - `高速运动` 不作为独立 L3 指标保留；它更像派生告警，可在后续用作辅助 timeline，不进入核心卡片体系

  **前端卡片展示规则**
  - 评分环只显示 `Q_motion` 这一总分
  - 下方子指标卡片按严重度排序（现有逻辑保留），但展示名称和描述全部使用中文业务语义
  - 首版建议卡片集合：`Q_motion`、`平滑度 LDLJ*`、`无效动作占比`、`动作饱和率`、`停滞占比`、`时间戳抖动`、`跟踪误差`、`执行力度`（P1 若启用则加入 `手指颤振`）

- Impacted nodes: D, E
- Status: active

### 2026-07-17 — MinIO 扫描入库架构升级：可靠增量同步 v3

- Type: architecture
- Status: confirmed; replaces the 2026-07-16 v2 decision below
- Importance: critical
- Objective: 以当前约 291 万条对象索引的真实生产规模为基线，一步到位固化每日自动、前端一键、可扩展、可终止、可恢复、可同步删除事实的扫描入库主干。
- Evidence:
  - 生产 PostgreSQL 当前有 58 个 active List、5,987 个 EpisodeInventory、约 2,909,780 条 `episode_objects`
  - 49 个 List 位于一级、9 个位于二级，证明扫描正确性不能依赖固定目录深度
  - 最近两个旧扫描停在 `classifying`，证明瓶颈同时存在于全桶枚举、全量内存、逐对象 ORM upsert 和不可终止线程
  - 现有 `discovered_prefixes/lists/episode_inventory/episode_objects` 均通过字符串扫描 ID 外键引用 `scan_jobs`，不适合重建为 BIGINT 主键表
- Decision:
  - 正式架构采用：任意深度 namespace discovery + 已知 List prefix 分片 + PostgreSQL 持久队列 + 独立 `scan-coordinator`/`scan-worker` Docker Service + 每 shard 可终止子进程 + 流式 Episode 指纹 + 选择性关键对象索引 + 原子 shard 发布 + 二次确认软删除/自动恢复 + 幂等资产重算 + 每日 smart/每周 full + 前端一键操作
  - 扫描职责固定为 `smart / incremental / full / manual_prefix`。普通前端和每日定时任务只使用 `smart`；后端自动完成 discovery、模式升级、分片、重试、缺失确认与资产重算
  - 每日按 `Asia/Shanghai` 配置时间创建 smart job；每周低峰创建 full reconcile。无 MinIO 事件通知时，删除同步采用最终一致性：活跃/到期 List 按 `next_scan_at` 扫描，任何 adaptive List 最长 7 天重扫，每周 full 兜底
  - namespace discovery 使用 `recursive=False` 按层探索，确认 List 后不进入其 Episode/逐帧对象内部；List 仍由结构特征识别并使用 deepest-match，不强制一级目录
  - 新上传推荐 `<bucket>/<list>/`，允许 `<bucket>/<group>/<list>/`；`raw/processed` 必须为 List 直接子级。List 身份固定为 `(bucket, canonical_list_prefix)`；移动/重命名视为旧实体缺失 + 新实体出现，不自动迁移 QC 历史
  - 默认一个 List 一个 shard；保留 `parent_shard_id`。Episode > 10,000、历史对象数 > 1,000,000 或连续两次 > 600s 时，允许自动升级为 Episode-group 子分片
  - `scan_jobs` 原地扩展并保留 String(64) 主键；新 job ID 使用 UUID/ULID 字符串。`scan_shards` 使用 BIGINT IDENTITY，`scan_job_id` 保持字符串外键。废弃 v2 的“旧表改名 + 新 BIGINT scan_jobs”方案
  - `episode_objects` 只保存 manifest/metadata/telemetry/video/MCAP/timestamp 等业务可寻址关键对象；depth PNG、pointcloud PLY 等 bulk 对象不再逐行持久化
  - 所有对象仍参与 Episode 级 count/size/fingerprint 计算；指纹由 `(object_key, etag, size, last_modified)` 确定性生成，任意新增、修改、删除都会改变指纹
  - List、Inventory、关键 Object 来源状态统一为 `present / suspect_missing / missing`。第一次成功完整扫描未见进入 suspect 并安排 10 分钟后确认；第二次独立成功扫描仍未见才确认 missing；重新出现自动恢复
  - skipped/failed/cancelled/timeout shard 不增加 missing streak，且绝不执行删除判断；扫描器永不自动物理删除 List/Batch/Episode/QC/审计历史
  - Episode 增加 active 来源语义；当前 readiness `state` 允许因关键对象缺失降级，另存只升不降的 `max_observed_state`
  - shard 必须在完整枚举后用单一事务原子发布；失败时回滚并保留上次成功快照。数据库写入必须 bulk load/upsert，禁止逐对象 ORM 查询
  - Worker 使用 `FOR UPDATE SKIP LOCKED`、lease、heartbeat、wall-clock timeout、terminate/kill 和最多 3 次指数退避重试；容器/主机重启后从 PostgreSQL 恢复
  - batch/task asset recompute job 增加 `rerun_requested`，running 时再次 enqueue 不得覆盖成 pending
  - 前端主合同固定为一个 `开始扫描` 按钮，默认 `mode=smart`；重复点击返回现有 active job，页面关闭不影响任务。高级 full/prefix/cancel/retry 收入 admin/qc_manager 二级入口
- Resolved questions:
  - `Q-20260623-004`: census 改为动态基线，不是固定常量；当前 DB 快照为 58 active lists，v3 Step 0 重新执行只读 MinIO census
  - `Q-20260624-008`: 正式采用每日 smart + 自适应 incremental + 每周 full + manual_prefix
  - `Q-20260624-009`: 不强制一级目录；结构规则是硬约束，目录深度不是
  - `Q-20260624-010`: 二次成功观测确认 missing，软失活、保留历史、重新出现自动恢复
- Five capability assessment:
  - 每日自动入库：支持；定时 smart job 幂等创建，服务重启可恢复
  - 大幅提速与扩展：支持；通过 discovery 剪枝、List 分片、流式固定内存、Episode 指纹短路、选择性索引、bulk upsert 和 Worker 横向扩展实现。无事件通知时 full scan 仍为 O(对象总数)，这是不可消除下界
  - 鲁棒性：支持；失败必须超时、重试、恢复或明确终止，不能永久 running
  - 删除同步：支持最终一致软删除；仅完整成功 shard 可产生缺失证据
  - 傻瓜式操作：支持；普通用户一次点击 smart scan，后端自动编排全部技术步骤
- Verification target: 详见 `docs/scan-architecture-final-plan-v3.md` 第 13 节
- Reference: `docs/scan-architecture-final-plan-v3.md`
- Impacted nodes: F, D

### 2026-07-18 — MinIO 扫描入库 v3 实施验证完成

- Type: verification
- Status: validated (deployed, real MinIO end-to-end, browser E2E)
- Decision: 扫描 v3 核心实现已完成离线测试、生产无缓存部署、真实 MinIO 扫描、在线迁移验证和浏览器端到端测试，确认核心功能按预期工作。
- Verification scope:
  - **离线测试**：`test_data_assets.py` 11 项通过，compileall 无错，SQLite/PostgreSQL 双数据库 Alembic 迁移兼容。
  - **Docker 无缓存重建**：backend、frontend、scan-coordinator、scan-worker 四镜像重建并强制重启。
  - **在线迁移**：`20260716_0025 → 20260717_0026` PostgreSQL 在线升级成功。
  - **真实 MinIO 扫描**：
    - namespace discovery 展开。
    - manual-prefix scan 成功终态（succeeded/succeeded_shards=1）。
    - 失败 shard 重试（`scan_scheduled_smart_yaocao_20260718` 修复并继续）。
    - pending/running/retry_wait shard 取消保护（`scan_7e652bfb*` 等 3 个 job，共 115 个 shard cancelled）。
    - 取消后已成功 shard 不回滚，不发布错误结果。
    - 数据一致性：59 lists / 5,987 inventory / 2,909,780 objects，重复扫描无重复。
  - **浏览器 E2E**：认证→页面挂载→模式切换→prefix 填写→创建扫描→轮询→终态→取消→cancelled 确认，0 console error/warning。
  - **API**：session、scan 创建/详情/取消/retry，/health。
  - **平台清理**：active job = 0，非终态 shard = 0，无残留 worker。
- Known limitations:
  - 未等待整桶大规模 full scan 自然完成（仅验证了 discovery、分片、部分处理、retry、cancel）。
  - 取消竞态日志中存在 `RuntimeError: scan cancellation was requested before publication`，为发布前取消保护的预期路径，数据正确，可后续优化为 warning。
  - 未开展多 worker 高并发压力测试。
  - Ollama 服务未运行，仅验证了 AI explain fallback。
- Outcome: 2026-07-18 13:02 完成所有服务无缓存重建和 Compose 强制重启，当前平台就绪，待用户手动测试。

### 2026-07-18 — 数据总库扫描操作权限收口

- Decision: 数据总库页面本身仅允许 `admin` 与 `qc_manager` 访问，因此扫描卡片、`full` 模式、取消和失败重试不再在页面内做第二层角色隐藏；页面访问路由与后端扫描 API 的同一角色校验是唯一权限边界。
- Reason: 页面内再次按相同角色条件判断没有增加安全性，反而容易造成“高级功能仅对另一类页面用户显示”的错误产品语义。能进入数据总库的用户都应直接看到完整的扫描操作。
- Implementation detail: 移除 `database-view.vue` 的 `canScanDatabase` 条件渲染；保留 `/database` 路由及 `POST /api/database/scan*` 的 `admin/qc_manager` 授权校验。
- Status: implemented; frontend verification pending

### 2026-07-18 — scan_worker_replicas 可配置化

- Decision: `scan_worker_replicas` 加入 `GeneralConfig` 默认值（`default_general_config()`），前端设置页通用 tab 新增"扫描工作进程"卡片，附带应用脚本 `scripts/set-scan-worker-replicas.sh`。
- Reason: 用户需要在 UI 上查看和调整 worker 数量，不需直接操作 docker-compose。后端配置只做持久化和读取，实际的容器扩缩容通过辅助脚本完成。
- Implementation detail: 后端 `general_config.py` 新增 `scan_worker_replicas: 1` 到 defaults；前端 `settings.vue` 通用 tab 新增 `el-input-number` 控件（1-16），hint 文字说明修改后运行脚本；新增 `scripts/set-scan-worker-replicas.sh`，可带参数直接指定或从 DB 自动读取。
- Script usage:
  ```bash
  # 从数据库读取副本数并应用
  scripts/set-scan-worker-replicas.sh
  # 手动指定副本数
  scripts/set-scan-worker-replicas.sh 3
  ```
- Status: implemented; frontend verification pending

### 2026-07-18 — scan_worker_replicas 保存后自动扩缩容

- Decision: `scan_worker_replicas` 在通用设置保存时自动调用 `docker compose up -d --no-deps --scale scan-worker=N` 生效，不再需要手动运行脚本。
- Reason: 用户期望修改 worker 副本数后立即生效，不需要额外的手动操作。
- Implementation detail: Docker socket (`/var/run/docker.sock`) 及宿主机的 `docker`/`docker-compose` CLI 二进制通过 volume mount 挂入 backend 容器；`PUT /api/admin/general-config` 检测 `scan_worker_replicas` 变化后执行 `_scale_worker_replicas()`；使用 `--no-deps` 避免 `depends_on` 触发 backend 自身重建。
- Status: implemented; verified (3→1→3 scale up/down works)

### 2026-07-16 — MinIO 扫描入库架构升级：分层并行扫描 v2（已被 v3 替代）

- Type: architecture
- Status: replaced by v3 on 2026-07-17
- Importance: high
- Objective: 将当前单线程全桶递归扫描器升级为分层并行、可终止、可重试的正式架构，一步到位按大规模数据设计。

- Context:
  - 当前扫描器使用 `threading.Thread` + `list_objects(recursive=True)` 全桶递归，存在线程挂死后无法终止、无超时、无分片、无进度、无法增量等根本性缺陷
  - 综合两次 GPT 方案反馈，确定了 v2 最终方案
  - 核心原则：MinIO 是数据事实源、PostgreSQL 是业务索引、日常同步只处理变化数据、全量扫描只做最终一致性、任务必须可分片可终止可重试

- Decision:
  - 正式架构：**Prefix 分片 + PostgreSQL 持久化队列 + 独立 Docker Worker Service + 子进程隔离 + 流式指纹对比增量检测 + `next_scan_at` 自适应退避 + shard 级安全删除判断 + `rerun_requested` 幂等资产投影联动**
  - 新增表：`scan_jobs` (v2, BIGINT IDENTITY)、`scan_shards`、`scan_prefix_states`
  - 扩展表：`batch_asset_recompute_jobs.rerun_requested`、`task_asset_recompute_jobs.rerun_requested`
  - 旧 `scan_jobs` → `scan_jobs_legacy`，保留一个发布周期后删除
  - 部署：独立 Docker Service `scan-worker`，与 FastAPI 平级，初始 2 副本
  - 增量策略：`list_objects` 遍历元数据 + 四元组 (object_key, etag, size, last_modified) 指纹对比变化检测，只对已变化对象执行业务解析
  - Prefix 调度：`next_scan_at` 自适应退避（30min → 2h → 12h → 1day → 7day），替代有逻辑缺陷的 `skip_until_next_change`
  - 删除检测：仅限成功完成完整枚举的 shard 范围内执行，skipped/failed/cancelled 的 shard 不参与删除判断
  - 分片级重试：指数退避（30s → 2min → 10min → 1h），max_attempts=3，含随机抖动

- Rejected alternatives:
  - `object_inventory` 新表：经核实，所有 MinIO 对象均归属 Episode（路径模式固定），`episode_objects` 已含所需指纹字段（content_hash/size_bytes/last_modified），额外建表维护两套元数据一致性 ROI 为负
  - HOT/WARM/COLD/ARCHIVED 四级冷热调度：`next_scan_at` 自适应退避实现等价效果，管理复杂度更低
  - `skip_until_next_change` 布尔值：无 MinIO 事件通知时逻辑不闭环（不扫 = 无法知道变化），废弃
  - 超大 Batch 二级拆分：当前无单 Batch > 10K episodes，保留 `parent_shard_id` 接口

- Reference: `docs/scan-architecture-final-plan-v2.md`

- Implementation roadmap (10 steps):
  0. 基线测试 + Feature Flag (`SCANNER_V2_ENABLED=false`)
  1. 数据库模型落地（Alembic migration + 模型代码）
  2. 抽离 `business_resolver.py`（新旧 scanner 共用）
  3. `scan_jobs` + `scan_shards` + 单 Worker Shadow 模式
  4. Prefix Discovery + Full Scan（流式 + 批量写入）
  5. 子进程隔离 + Timeout + Lease + Heartbeat + Retry
  6. 变化检测 + 增量写入
  7. Asset Recompute 幂等化（`rerun_requested`）
  8. `next_scan_at` 自适应调度 + 安全删除
  9. API + 前端（进度展示、取消、重试失败 shard）
  10. 灰度切换 + 多 Worker 并行

- Estimated: ~5,000-8,500 行代码，16-25 人日

- Impact: 扫描子系统整体重写，不影响已上线的 `batch_asset_rollups` / `task_asset_rollups` 数据资产投影链路
