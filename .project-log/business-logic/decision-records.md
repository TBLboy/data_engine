# Business Logic Decision Records

### 2026-06-16 - 项目定位为调研阶段（已演进）

- Decision: 项目启动时为调研阶段
- Context: 项目初期用户明确说明现阶段主要工作是调研公开数据集QC方法
- Why superseded: 2026-06-23 起，项目已从"纯调研"演进到"MinIO 数据湖接入方案设计 + QC 系统实现"阶段；调研阶段决策被后续实施阶段决策覆盖，不再作为当前约束
- Superseded by: 
  - 2026-06-23 MinIO 数据湖接入采用 PostgreSQL 控制面模型
  - 2026-06-22 真实入库/鉴权/部署等实施决策
- Status: superseded（历史记录留存）

### 2026-06-16 - 数据采集平台使用Linker Open TeleDex

- Decision: 数据采集平台已确定为Linker Open TeleDex系统，数据格式不改动
- Context: 用户说明当前使用灵心巧手的数据采集平台
- Alternatives considered:
  - 设计新的数据格式（如KitchenDex）
  - 调整Linker TeleDex数据格式
- Reason: 数据采集平台已确定，不改动采集系统
- Evidence / Verification: Linker TeleDex数据说明文档PDF已阅读，且 MinIO 实查确认 processed 层结构一致
- Impacted nodes: C（数据格式分析节点）
- Impacted edges: B->C（基于Linker TeleDex格式分析）
- Status: active

### 2026-06-16 - 调研推进顺序：02 → 01 → 03，DQAF 优先（已演进）

- Decision: 采纳 GPT 规划的 2–3 周调研路线；报告推进顺序为 **02 → 01 → 03**；第一执行任务为 **DQAF 精读 + TeleDex 指标映射表**
- Context: TeleDex 基线与 DROID 已完成；最缺「拿到一条 episode 如何判断质量」的可落地方案
- Why superseded: 调研报告绝大部分已完成，当前项目重心已从"调研"转移到"MinIO 数据湖控制面设计 + 实施"。B3（数据策展框架）暂缓
- Status: superseded（调研阶段决策已完成使命）

### 2026-06-24 - 任务类型从“扫描器自动归类结果”调整为“人工维护主数据”

- Decision: `task_types` 不再被定义为扫描器自动决定的正式业务分类，而是改为由 `admin` / `qc_manager` 人工维护的业务目录。扫描器的职责收窄为“同步 MinIO 数据到 PostgreSQL”，不再自动创建或自动决定正式任务类型；新批次和未确认批次统一归入 `待分类`
- Context: 当前实现里 `task_type`、扫描归类规则、batch 外键和前端展示维度耦合过深，导致任务类型难以增删改，也不适合后续形成由质检主管主导的任务类型管理体系
- Alternatives considered:
  - 保持当前自动归类为正式任务类型的方案
  - 允许扫描器继续 authoritative 自动决定 batch 所属任务类型
  - 只在前端隐藏自动归类痕迹，不改底层语义
- Reason: 用户明确要求任务类型管理必须成为高频运营能力，`admin/qc_manager` 需要随时新增、删除、重命名任务类型，并能把批次从一个任务类型改挂到另一个任务类型。如果正式任务类型继续由扫描器决定，后续主数据管理会始终被底层扫描逻辑牵制
- Evidence / Verification: 当前代码复核确认 `TaskType` 主要来自 seed 与扫描阶段自动绑定，前端仅有展示/筛选/派发使用能力，没有完整任务类型主数据管理后台
- Impacted nodes: F, D
- Status: active

### 2026-06-24 - 扫描器与任务类型彻底解耦，批次删除/删除任务类型默认回收到“待分类”

- Decision: 扫描器只负责 list / episode / object / batch 的发现与同步，不再把 prefix 规则直接落成正式任务类型。若 batch 已被人工分类，则后续 rescan 不覆盖其任务类型；若 batch 未分类或属于新发现数据，则统一进入 `待分类`。删除某个任务类型时，不物理删除其批次，而是把该任务类型下所有 batch 自动回收到 `待分类`
- Context: 真实业务需要同时支持新增数据入库、批次人工调整、任务类型增删改和历史 QC 保留；如果任务类型删除会直接波及 batch/episode 物理删除，审计和历史追溯会被破坏
- Alternatives considered:
  - 删除任务类型时联动删除批次和 episode
  - 删除任务类型时保留 batch 原任务类型字符串作为悬空值
  - 让扫描器每次重扫都重新覆盖 batch 所属任务类型
- Reason: `待分类` 必须成为系统保底池，承接所有未确认或被回收的数据；这样既允许运营侧灵活调整目录，也能保持历史 batch/episode/QC 数据稳定存在
- Evidence / Verification: 当前 V1 运行状态已确认 batch 是扫描产物而非人工录入对象，且页面上的任务派发、manual QC、qc-history 均依赖 batch/episode 稳定存在
- Impacted nodes: F, D
- Status: active

### 2026-06-23 - MinIO 数据湖接入采用 PostgreSQL 控制面模型

- Decision: MinIO 在 V1 中只承担原始对象存储层；业务查询、任务归类、episode 状态推进、QC 派发与对象映射统一由 PostgreSQL 控制面承接
- Context: `yaocao` bucket 中真实对象结构已经确认是 `bucket/<list_prefix>/{raw|processed}/episode_xxxxxx/...`，manual QC 当前依赖 processed 层对象，且单个 episode 元数据里尚未发现可稳定充当业务任务主键的单字段
- Alternatives considered:
  - 直接把 MinIO 路径字符串当业务主键
  - 让前端直接依赖 bucket/prefix 规则读取对象
  - 将任务类型绑定到单个对象元数据字段
- Reason: 真实数据湖场景里存在一个任务拆散到多个 list、一个 list 包含不定数 episode、raw/processed 不对称存在等情况；如果把对象路径直接当业务主键，后续 schema、扫描、派发和审计都会变脆弱
- Evidence / Verification: 已完成 `yaocao` bucket 样例对象实查，确认 processed 依赖 `manifest.json`、`metadata.json`、`telemetry.npz` 与多路媒体对象
- Impacted nodes: C, D
- Status: active

### 2026-06-23 - MinIO list 定义与全量扫描规则确定

- Decision: V1 中的 list 定义为 `bucket + list_prefix` 所代表的一次采集/上传来源批次；扫描 `yaocao` bucket 时必须递归遍历所有层级 prefix，并用结构特征而不是固定深度或命名文本识别 list
- Context: 当前 bucket 中既存在 `yaocao/<list>/...`，也存在 `yaocao/K1/<list>/...` 这类第二层 list；用户已明确后续需要对 `yaocao` 做全面扫描，不能漏掉任何真实 list
- Alternatives considered:
  - 只扫描 bucket 第一层 prefix
  - 只扫描第一层和第二层 prefix
  - 仅依赖 `double_linkerhand_task_xxx_timestamp` 这类命名正则识别 list
- Reason: list 的真实位置深度并不稳定，但其结构特征相对稳定：list 的直接子级会命中 `raw/`、`processed/` 之一或两者，且其下会出现 `episode_xxxxxx/`。因此扫描器应做全层级递归发现，再按结构规则判定 list，不能把"第几层"当成规则本身
- Evidence / Verification: 已观察到 `yaocao` 下同类业务 list 同时存在于第一层和 `K1/` 等第二层路径下，且 raw/processed episode 数量并非严格完全对齐
- Impacted nodes: C, D
- Status: active

### 2026-06-23 - Episode 状态采用 ingestable / processable / qc_ready 三层模型

- Decision: Episode 在 MinIO 接入后不做二元"存在/不存在"建模，而是分为 `ingestable`、`processable`、`qc_ready` 三层状态；manual QC 仅接收 `qc_ready` episode
- Context: 当前 bucket 中既有 raw-only 场景，也有 raw/processed 不完全对齐的场景；同时 manual QC 依赖 processed 层关键对象
- Alternatives considered:
  - 所有发现到的 episode 一律视为可 QC
  - 仅区分 raw 与 processed 两种状态
- Reason: 用户已明确后续会有"多次少量写入"，如果不把 raw 发现、processed 补齐、QC 派发拆开，后续扫描和任务池状态会混乱
- Evidence / Verification: 已读取样例 `manifest.json`、`metadata.json`、`recording_info.json`，并确认 QC 所需核心对象位于 processed 层
- Impacted nodes: C, F, D
- Status: active

### 2026-06-23 - 控制面 schema v0.1：6 表 + 扫描器状态机 + deepest-match 排重

- Decision: MinIO 控制面采用 6 张新表（`scan_jobs`、`discovered_prefixes`、`lists`、`episode_inventory`、`episode_objects`、`classification_rules`），扫描器分 scanning/classifying/episode-inventory/done 四阶状态机，父子 prefix 冲突用 deepest-match 规则排重。现有 `episodes`/`batches`/`ingest_jobs` 通过 `ingested_episode_id` 桥接，不做 drop/rename
- Context: Node F 需要在不改动现有 QC 表的前提下，补一层"bucket 里有什么"的对象清单映射层
- Alternatives considered:
  - 直接改现有 `episodes.source_path` 并移除本地扫描逻辑，不新增表
  - 把所有 MinIO prefix 扁平化塞进 `episodes` 表加 bucket/key 列
- Reason: 对象映射和 QC 业务是两个独立的生命周期。`episode_inventory` 只管"bucket 里出现的是什么 episode"，状态推进到 `qc_ready` 才下联到现有的 `episodes`/`batches`
- Evidence / Verification: 已复核现有 5 张业务表 schema，确认新表字段不冲突，迁移计划不涉及现有表 drop/rename
- Impacted nodes: F, D
- Status: active
- Document: `control-plane-schema-v1.md`

### 2026-06-23 - 控制面 schema v0.2：扫描器实现级规则、状态推进、object_role 清单补齐

- Decision: 在 schema v0.1 基础上，补齐 V1 可直接落地的三块规则：递归扫描算法（含分页、结构识别、deepest-match 排重、失败恢复）、episode 单调状态推进规则、`object_role` 规范化字典与 `qc_ready` 最小清单
- Context: 用户明确要求先把业务逻辑完善到可直接指导落地级别，再进入代码实现；同时 `yaocao` bucket 已确认存在多层 prefix、raw/processed 不对称与多次少量写入场景
- Reason: 如果这三块规则继续停留在 schema 草案层，迁移、扫描器实现和 QC 入库都会反复返工；尤其 V1 需要明确哪些对象只记录、哪些对象影响 `qc_ready`，以及 partial upload 下状态是否允许回退
- Evidence / Verification: 已基于 MinIO 实查结果、已确认的 Q-DD-001~004 以及当前 TeleDex processed 对象结构，将规则细化写入 `control-plane-schema-v1.md` v0.2
- Impacted nodes: F, D
- Status: active
- Document: `control-plane-schema-v1.md`

### 2026-06-23 - classification_rules 种子策略采用分层匹配 + 人工覆盖保留

- Decision: `classification_rules` 的 V1 种子采用三层策略：高置信单义 token 可 authoritative 自动定类；复合或歧义 token 只写 `candidate_task_type`；无命中列表进入 unclassified 队列。匹配按 `priority DESC`、`pattern` 长度 DESC、`basename` 优先、再按规则 id 稳定决胜；人工设置的 `final_task_type_id` 在后续 rescan 中不得被自动覆盖
- Context: 当前 `yaocao` list 命名已能提供部分业务线索，但用户已明确多个 list 可能属于同一业务任务，且 MinIO 前缀中同时存在设备位、层级位与时间戳噪音
- Reason: 如果直接用简单 substring 自动写死最终 `task_type`，复合任务和歧义命名会被误归类；但若完全不做种子规则，manual classify 队列又会过大。分层策略能在降低人工量的同时保留业务可控性
- Evidence / Verification: 已将规范化规则、match scope、seed category、冲突优先级和人工 override 语义写入 `control-plane-schema-v1.md` v0.2
- Impacted nodes: F, D
- Status: active
- Document: `control-plane-schema-v1.md`

### 2026-06-23 - 任务目录、MinIO list 绑定与删除语义收口

- Decision: V1 中必须区分三类对象：`task_types` 是可管理的业务任务目录，`lists` 是扫描器发现的 MinIO 采集/上传单元，`qc_tasks` 是下游派发出的审核工作项。人工操作允许创建/停用 `task_type`、允许对 `lists.final_task_type_id` 做绑定或清空，但不允许把 `lists` 当成可手工删除的业务实体；“删除任务”默认按 retire/disable 处理，而不是物理删除已有历史引用的 `task_type`
- Context: 现有 schema 已确定 `list` 不等于任务，且一个业务任务可能对应多个 list；如果不进一步收口新增/删除/解绑语义，后续 Node D 实现时任务管理、list 检查页和历史稳定性都会出现歧义
- Alternatives considered:
  - 把 MinIO `list` 直接当成可增删的任务实体
  - 允许删除已被 list/episode/history 引用的 `task_type`
  - 只支持绑定，不支持清空回退到 unclassified
- Reason: `lists` 是扫描结果，不应由人工随意破坏；而 `task_type` 是业务目录，确实需要新增和停用能力。历史 QC 与已入库 episode 的任务归属又必须稳定，不能因为后续清理目录就反向篡改历史数据
- Evidence / Verification: 已与 `control-plane-schema-v1.md` 中 `final_task_type_id`、manual override 保留、已入库 episode 不重分配等既有规则对齐，并补齐了 bind/unbind/check API 语义
- Impacted nodes: F, D
- Status: active
- Document: `control-plane-schema-v1.md`

### 2026-06-23 - Node F 业务逻辑闭环标准更新为“规则完整，可进入实现；但仍保留一项规模性开放问题”
- Decision: Node D 的 V1 manual QC API 合同采用 embedded media descriptor 方案：`qc-context` 直接返回带 `previewUrl`/`previewExpiresAt` 的 `media[]`；预览 URL 刷新通过 `POST /api/episodes/{episode_id}/media/refresh` 按 `objectId` 定向更新；显式下载通过独立 `GET /api/episodes/{episode_id}/objects/{object_id}/download` 受控提供
- Context: 对象访问协议虽然已确定为混合模式，但现有前后端合同里仍没有媒体字段，且 `url` 是在上下文阶段直接嵌入还是通过单独 access endpoint 二次换取，之前仍有实现选择空间
- Alternatives considered:
  - `qc-context` 只返回 object metadata，由前端逐个请求 `/media/{object_id}/access`
  - 使用通用 `url` 字段，同时允许“302 跳转型 access endpoint”和“直接 presigned URL”两种模式并存
  - 让前端在 URL 过期后整页重拉 `qc-context`
- Reason: manual QC 页面需要同时加载多路视频；如果首屏后还要求前端逐路调用 access endpoint，会放大请求数和播放器初始化复杂度。把 `previewUrl` 直接嵌入 `qc-context` 能保持播放器接入简单，同时 `objectId` 定向 refresh 又避免每次过期都整页重载。把下载与预览拆开，才能在权限和审计上保持显式边界
- Evidence / Verification: 已复核当前 `ManualQcContextSchema` 与 `frontend/src/api/client.ts` 均无媒体字段；`manual-qc.vue` 媒体区仍是固定占位布局，因此需要在实现前先给出稳定 descriptor shape、refresh payload 和 download 边界
- Impacted nodes: D
- Status: active
- Document: `control-plane-schema-v1.md`

### 2026-06-23 - manual QC 的 MinIO 对象访问采用混合协议

- Decision: V1 的 manual QC 对象访问采用混合协议。预览/播放类 MP4 由后端签发短时 presigned URL；`manifest.json`、`metadata.json`、`telemetry.npz` 等结构化对象继续由后端直接读取/解析；显式下载、导出和非预览对象访问仍走后端受控接口
- Context: 当前 manual QC 页面已经是后端 API 驱动，但媒体区仍是占位 UI；后端真实上下文仍依赖宿主本地 processed 目录读取，尚未具备 MinIO 媒体访问协议。真实 `yaocao` processed episode 同时包含多路 `mp4`、`telemetry.npz`、`manifest.json` 与 `metadata.json`
- Alternatives considered:
  - 所有对象统一走后端流式代理
  - 所有对象统一走 presigned URL
- Reason: 纯代理会把多路视频预览流量全部压到 backend/nginx，增加吞吐和时延压力；纯 presigned 会让前端过度感知 bucket/key 语义，并削弱结构化对象解析、权限控制和审计边界。混合协议能保持“前端只调后端 API”的架构约束，同时让浏览器原生 `<video>` 直接播放 MinIO 媒体
- Evidence / Verification: 已复核当前代码，确认 `manual-qc.vue` 视频区域仍未接真实媒体，`payloads.py` 当前只会从本地 processed 目录读取 `manifest.json`、`metadata.json`、`telemetry.npz`；`ManualQcContext` 现有 payload 尚无媒体描述字段，因此该协议需要通过后端扩展 media descriptor 合同落地
- Impacted nodes: F, D
- Status: active
- Document: `control-plane-schema-v1.md`

### 2026-06-23 - `yaocao` basename 首版 seed 盘点完成，authoritative 范围收敛到单义单物料 token

- Decision: 基于真实 `yaocao` basename 样本，V1 首版 `classification_rules` 的 authoritative 自动定类先收敛到 `huanggua`、`huangguakuai`、`tudou`、`tudoutiao`、`luobo` 五类单义 token；复合词和专有流程词一律降级为 suggest-only 或 no-match
- Context: 已完成真实 bucket 盘点，当前共观察到 36 个结构命中 list，其中 35 个业务样式 basename、1 个技术性 `raw_data` 子分支；命名中普遍混有 `double_linkerhand`、`task`、`K1/`、时间戳和批次序号等噪音
- Reason: 真实样本证明单物料 basename 与复合任务 basename 同时存在。如果把 `fanqieluobo`、`huanggualuobo`、`misezhuobu_tudoutiao` 这类复合词也做 authoritative 自动写入，会过早把多个业务动作压扁成单一 `task_type`
- Evidence / Verification: 已对真实 basename 样本进行首轮盘点，确认 `qingdaohuanggua`、`qingdaotudou`、`qingdao_luobo`、`huangguakuai`、`tudoutiao` 存在重复批次且无竞争物料 token；复合词仅出现为混合/流程型命名，适合作为 suggest-only
- Impacted nodes: F, D
- Status: active
- Document: `control-plane-schema-v1.md`

### 2026-06-23 - 四条 schema 设计确认（Q-DD-001~004）

- Decision: Q-DD-001（episode 所属 list 不跨区）、Q-DD-002（qc_ready 对象清单硬编码最小集）、Q-DD-003（task_type 修改仅新入库生效）、Q-DD-004（deepest-match 保留父级独有条目）全部按 V1 方案确认
- Context: schema v0.1 产出后遗留 4 个开放设计问题
- Why: 用户确认 "暂时就按照这个来走"，V1 scope 不再扩展
- Impacted nodes: F
- Status: active(confirmed)
