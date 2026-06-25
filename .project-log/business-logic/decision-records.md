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

### 2026-06-24 - 数据总库页面切换到服务端分页/筛选作为长期正式方案

- Decision: `database` 页面不再把“全量 episodes 拉到前端后本地过滤 + 一次性渲染整表”作为长期正式模式，而是确定后续实现方向为“服务端分页 + 服务端筛选 + 前端短时缓存”。前端仍只消费后端 API，不直接保留全量 episode 作为页面事实源
- Context: 真实生产数据已达到 4416 条 episode，页面每次切换进入 `database` 时都会出现明显卡顿。排查确认早期瓶颈包含 `/api/database` payload 过重与 batch 序列化放大，但在后端 payload 减重后，运行中 backend 容器内 `database_payload()` 已可在约 `0.116s` 内完成构造，仍存在的主要体感卡顿更符合前端一次性过滤并渲染 4000+ 行 Element Plus 表格的表现
- Alternatives considered:
  - 保持现状，只继续压缩 `/api/database` 后端 payload
  - 只在前端做本地分页，但仍一次拉取全量 episodes
  - 使用 `KeepAlive` 或纯页面缓存掩盖重复进入卡顿
- Reason: 只做后端减重或前端本地分页，都无法从根本上解决“数据规模继续增长 + 多用户远程访问”下的网络、浏览器内存和大表渲染压力。服务端分页/筛选可以同时控制响应大小、数据库访问范围和前端渲染量，是唯一符合长期演进方向的正式方案；前端短时缓存只作为二级体验增强，而不是主优化手段
- Evidence / Verification: 当前运行中的 backend 容器已验证 `database_payload()` 仅返回最近 20 条 `ingestJobs`，并在 `episodes=4416, batches=44, jobs=20` 条件下测得 payload 构造耗时约 `0.116s`，说明“切页仍卡数秒”不能再主要归因于后端接口本身
- Impacted nodes: D, E
- Status: active

### 2026-06-24 - 数据总库服务端分页的业务边界与前端缓存语义收口

- Decision: `database` 页面后续分页接口必须由后端同时承担三类职责：1）按 `page/page_size` 返回当前页 episode 列表；2）按 `keyword/batch_id/qc_status/qc_result` 执行服务端筛选；3）返回总数与分页元信息供前端渲染。前端可以保留很短 TTL 的页面缓存，但缓存的角色是“先显示最近一次结果并后台刷新”，而不是替代分页查询或长期持有全量 episodes
- Context: 当前 `database-view.vue` 的筛选模型完全建立在 `episodes` 全量数组本地过滤上，这种交互模式在小数据下简单，但在远程多用户和持续增长的数据量下会让单次页面进入承担不必要的网络与渲染成本
- Alternatives considered:
  - 先只做 page/page_size，筛选仍在前端本地执行
  - 让前端缓存整份全量 `DatabasePayload`，靠 TTL 避免频繁请求
  - 拆成多个页面各自维护独立事实源，不再保留统一的 `database` 查询入口
- Reason: 分页、筛选和总数统计必须属于同一后端查询语义，否则前端会出现“页码是服务端的、筛选是本地的、总数又不是同一套结果”的不一致体验。短时缓存可以改善切页体感，但不能改变事实源仍由后端分页查询决定这一原则
- Evidence / Verification: 当前页面只需要表格当前页和筛选结果，不需要在浏览器中长期持有所有 episodes；同时现有业务已明确“前端继续只调后端 API，不直接承担数据湖式查询职责”，因此分页与筛选自然应收口在后端
- Impacted nodes: D, E
- Status: active

### 2026-06-24 - 任务派发主流程迁移到工作台，manual QC 页面只负责质检

- Decision: `qc_admin/qc_manager` 的主派发流程不再以 `task-pool` 的逐条任务指派为中心，而是迁移到工作台（`dashboard`）中完成。工作台负责选择 batch、生成本轮待派发任务、选择 reviewer 并执行批量分配；`manual-qc` 页面只负责 claim/release/提交质检结果，不再混入派发语义或派发入口
- Context: 当前实现把“任务派发”和“进入人工质检”混在同一个 `task-pool` 页面里，同时又在任务表中提供逐条派发 reviewer 的交互。这与真实工作流不一致，也让管理员操作成本过高
- Alternatives considered:
  - 继续在 `task-pool` 页面上迭代逐条派发
  - 保持派发与人工质检混合，但只做局部 UI 美化
  - 让 `manual-qc` 继续承担部分派发职责
- Reason: 用户明确要求人工质检页面只做质检，派发应该是管理员在工作台里完成的批量运营动作，而不是 reviewer 执行页面里的附带操作
- Evidence / Verification: 现有 `task-pool` 页面已确认同时包含 batch 预览、任务队列、单条派发和进入 manual QC 的入口，职责混杂；同时当前 `manual-qc` 已具备独立 review lock、媒体、提交链路，适合单独保留为质检执行面
- Impacted nodes: D, E
- Status: active

### 2026-06-24 - 任务派发采用“两段式”：先生成待派发任务，再批量分配 reviewer

- Decision: 任务派发的正式业务流程改为两段式。第一段是针对 batch 级别生成本轮待派发任务池（`full` / `sampled`）；第二段是在 reviewer 集合上执行批量分配，支持“平均派发”和“自定义每人条数”两种模式。逐条 `episode -> reviewer` 手工指定不再作为主流程
- Context: 当前 `dispatch-plan` 接口会一边决定采样范围、一边直接创建 `QcTask`，而任务分配还需要管理员在表格里对每条任务分别选择 reviewer，流程冗长且不适合真实批量运营
- Alternatives considered:
  - 保留现有 `dispatch-plan + 单条 assign` 组合为主流程
  - 仅支持平均派发，不支持自定义条数
  - 继续把 reviewer 分配逻辑停留在逐条任务层面
- Reason: 用户的真实工作流是“先生成待派发任务，再一次性派给若干 reviewer”，而不是生成后逐条人肉分发。批量分配是流程上的必要能力，不是 UI 小优化
- Evidence / Verification: 当前 `task-pool` 实现和后端 `assign_task` 路由都证实系统目前仍以逐条派发为主；同时用户现场工作流已经明确要求平均派发与自定义条数两种模式
- Impacted nodes: D, E
- Status: active

### 2026-06-24 - 任务重生成采用“活跃派发版本”语义，修复 full/sample 切换残留 bug

- Decision: 对同一 batch 的任务生成必须引入“活跃派发版本”语义。每次重新生成派发任务，都视为新的派发版本；页面运营视图只看当前活跃版本。旧版本中未开始的任务必须被退役或标记为 superseded，不能继续作为当前有效任务出现
- Context: 当前实现中，先执行 `full` 再切换到 `sampled` 重新生成后，旧的全量任务仍保留在活跃任务集中，导致用户看到的仍是 full 任务集而不是新的 sampled 结果
- Alternatives considered:
  - 保留旧任务不动，只继续追加新任务
  - 每次重生成都直接物理删除旧任务
  - 只更新 batch 的 dispatch_mode/sampling_ratio，不处理历史任务集
- Reason: 追加不退役会直接破坏当前运营视图；直接物理删除又会丢失审计历史。引入“当前活跃版本 + 历史版本保留”的语义，既能修复当前 bug，也能保留后续审计与追溯能力
- Evidence / Verification: 当前 `dispatch-plan` 路由已确认只创建缺失任务，不会回收旧任务，因此 `full -> sampled` 后旧 full 集合仍然存在；这正是用户现场复现出的 bug
- Impacted nodes: D, E
- Status: active

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

### 2026-06-24 - manual QC 页面采用统一同步播放器，而非独立视频播放器

- Decision: manual QC 页面中的多路视频必须由统一 frame control bar 控制，三路画面按共享 `currentFrame/currentTimeSec/playing` 状态同步播放；不允许用户通过单个视频窗口的本地 controls 独立播放、暂停或 seek
- Context: 当前页面虽然已经能加载真实三路视频，但底部 frame 区与视频窗口没有真正联动，且前端把秒数计算硬编码为 `currentFrame / 30`，导致 frame 区显示时长与真实视频时长不一致
- Alternatives considered:
  - 保留三个视频各自独立播放，再让 frame 栏只做参考显示
  - 允许用户继续点击单个视频 controls，同时尽量同步其他视频
  - 继续使用硬编码 fps 近似映射 frame/time
- Reason: manual QC 的核心不是“看三个普通视频”，而是“检查同一时刻下的多视角一致性”。只要允许单画面独立播放或独立 seek，就会天然破坏同步检查语义，也会让 frame bar 失去事实源地位
- Evidence / Verification: 代码复核确认当前 `manual-qc.vue` 中视频仍使用原生 `<video controls>`，而 frame bar 只修改前端变量、未控制视频元素；当前时间文本也直接使用 `currentFrame / 30` 计算，未消费 backend 已提供的 `fps` / `durationSec`
- Impacted nodes: D
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
