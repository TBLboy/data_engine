# Open Business Logic Questions

## Active Questions

### Q-20260623-004

- Related node: C
- Related edge: C->F
- Question: `yaocao` bucket 当前完整有多少个 list？它们中哪些是 raw_only、哪些是 processed_only、哪些两者兼有？
- Why it matters: 这个数量决定 V1 扫描器和 episode inventory 表需要处理的数据规模和判定覆盖范围
- Current status: Open
- Answer: Unknown（样本检查确认每 list 约 101–151 个 episode，但全量统计未做）

### Q-20260623-005（Resolved 2026-06-23）

- Related node: D
- Related edge: F->D
- Question: V1 中 manual QC 的视频/媒体对象最终采用什么访问协议？
- Resolution: 采用混合协议。预览/播放类 MP4 由后端签发短时 presigned URL，供 manual QC 页面直接播放；`manifest.json`、`metadata.json`、`telemetry.npz` 等结构化对象继续由后端读取/解析；显式下载、导出和非预览对象访问继续走后端受控接口。前端只接收后端返回的 media descriptors，不拼接 bucket/key 规则，也不直接持有 MinIO 凭据

### Q-20260623-007（Resolved 2026-06-23）

- Related node: D
- Related edge: F->D
- Question: Node D 中 `ManualQcContext.media[]`、预览 URL 刷新与显式下载的 API 合同应该如何收口？
- Resolution: `GET /api/episodes/{episode_id}/qc-context` 直接返回 embedded `media[]` descriptors，字段至少包含 `objectId`、`role`、`label`、`variant`、`slot`、`mimeType`、`previewUrl`、`previewExpiresAt`、`refreshable`、`downloadable`、`sortOrder` 以及可选媒体元数据。URL 刷新通过 `POST /api/episodes/{episode_id}/media/refresh` 按 `objectId` 定向更新；显式下载走独立 `GET /api/episodes/{episode_id}/objects/{object_id}/download`。前端不拼接 bucket/key，不请求通用 access endpoint，也不把 preview 与 download 语义混用

### Q-20260624-011（Resolved 2026-06-24）

- Related node: F
- Related edge: C->F
- Question: 任务类型与 batch 的人工管理模型应该如何正式落地？尤其是“新 batch 默认进 `待分类`”、“已人工分类 batch 的 rescan 不覆盖”、“删除任务类型后批次自动回收到 `待分类`”这三条规则，对 schema/API/UI 的最终约束分别是什么？
- Resolution: 已确定方向。任务类型改为 `admin/qc_manager` 人工维护主数据；扫描器只同步数据，不自动决定正式任务类型；新 batch 默认进入 `task_type:unclassified` / `待分类`；从任务中移除 batch 或删除任务类型时，batch 都回收到 `待分类`；错分 batch 的标准纠正流程是“先移出到待分类，再加入正确任务”；`数据总库` 负责按批次确认当前归属，后续任务类型管理页负责改挂与维护

### Q-20260624-008

- Related node: F
- Related edge: C->F
- Question: 当前 `yaocao` bucket 继续增长后，V1 的“全量递归扫描 + 幂等落库”是否还能承担日常入库？如果不能，后续应该如何拆分成全量校准、增量发现和定向重扫三种模式？
- Why it matters: 目前扫描发现阶段仍是全量递归遍历所有对象，数据量增长后扫描耗时会持续上升。若不提前规划增量模式，生产现场每次新上传一批数据都要等待全量扫描，入库体验和系统负载都会越来越差
- Current status: Open
- Answer: Pending。当前判断是 V1 方案适合作为稳妥兜底，但长期生产主路径大概率需要升级为“低频全量校准 + 高频增量入库/指定 list 重扫”的分层模式

### Q-20260624-009

- Related node: F
- Related edge: C->F
- Question: 是否应该把 MinIO 上传规范正式收紧为“bucket 下一层每个目录必须直接代表一个 list，禁止 `K1/<list>` 这类二层嵌套”，从而把新数据发现阶段降级为只列 bucket 下一层 prefix 名单？
- Why it matters: 如果上传规范可以严格约束，后续就不需要每次为发现新 list 而递归扫全部对象，只需要列出 bucket 下一层目录并和 PostgreSQL 已知 list 做差集，再对新增 list 做深扫入库，成本会明显更低
- Current status: Open
- Answer: Pending。用户建议这一方向可行，但还需要结合真实上传流程、采集侧约束、历史兼容成本和异常数据处理方式综合评估，不能只从扫描性能单点决定

### Q-20260624-010

- Related node: F
- Related edge: C->F
- Question: 当 MinIO 中某个 list / episode / 对象被删除或替换后，PostgreSQL 应该如何同步？是立即物理删除、标记 inactive、保留历史版本，还是区分“用户主动删除”和“暂时缺失”？
- Why it matters: 动态数据关联系统不能只处理新增入库，还必须定义删除与失活语义，否则 MinIO 和 PostgreSQL 会越来越不一致；同时若处理过于激进，又可能破坏历史 QC 记录、审计链和可追溯性
- Current status: Open
- Answer: Pending。当前更倾向先做状态同步而非直接物理删除，即优先引入 inactive/missing/soft-delete 一类语义，再在后续明确何时允许彻底清理历史记录

## Resolved Questions

### Q-20260623-006（Resolved 2026-06-23）

- Related node: F
- Related edge: C->F
- Question: `yaocao` 现有 list basename 的真实样本中，哪些 token 可以 authoritative 自动映射到具体 `task_type`，哪些只能作为 suggest-only 候选？
- Resolution: 真实样本盘点后，V1 authoritative 范围收敛到单义单物料 token：`huanggua`、`huangguakuai`、`tudou`、`tudoutiao`、`luobo`。复合或流程型 basename（如 `qingdaofanqieluobo`、`qingdaohuanggualuobo`、`chengfanghuanggualuobo`、`misezhuobu_tudoutiao`、`fengqintudou`、`tiaoliaoping`）仅生成 suggest-only `candidate_task_type`；`quanliucheng1`、`naguo`、`chengfanghuangguang`、`raw_data` 保持 no-match

### Q-20260623-001（Resolved 2026-06-23）

- Related node: F
- Related edge: C->F
- Question: V1 中 `candidate_task_type` 到最终 `task_type` 的具体规则映射表如何设计？
- Resolution: 采用三层 seed 策略：高置信单义 token 用 authoritative 规则直接写 `final_task_type_id`；复合或歧义 token 只写 `candidate_task_type`；无命中保持 unclassified。匹配顺序按 `priority DESC`、`pattern` 长度 DESC、`basename` 优先、再按 rule id 稳定决胜；人工确认后的 `final_task_type_id` 不被 rescan 自动覆盖

### Q-20260623-002（Resolved 2026-06-23）

- Related node: F
- Related edge: C->F
- Question: V1 中 `qc_ready` 的最小对象清单是否需要按任务类型进一步细分？
- Resolution: V1 不按 `task_type` 建模板，统一采用最小公约数清单：`manifest` + `metadata` + `telemetry_npz` + `>=1 camera_rgb_video`。其他对象进入 `episode_objects` 记录但不阻塞 `qc_ready`

### Q-20260623-003（Resolved 2026-06-23）

- Related node: F
- Related edge: C->F
- Question: 父子 prefix 同时命中 list 结构规则时，扫描器应如何消除重复识别？
- Resolution: 采用 deepest-match；深层命中优先，但若父级自身拥有不属于子级的直接 raw/processed episode，则父级保留为独立 list 条目

### Q-20260616-004（Resolved 2026-06-23）

- Related node: C
- Related edge: B->C
- Question: 是否可以获取Linker TeleDex实际采集的数据样本？
- Resolution: 已在 MinIO 对象存储中通过 `boto3` 直接读取了 `yaocao` 和 `20260527` bucket 中的真实样例数据，包括 `manifest.json`、`metadata.json`、`recording_info.json` 等完整 episode 元数据，以及 `telemetry.npz` 和多路 mp4 等媒体对象

### Q-20260616-002（Resolved 2026-06-23）

- Related node: C
- Related edge: B->C
- Question: Linker TeleDex系统是否已经内置部分QC功能？
- Resolution: MinIO 实查确认平台确实内置了同步校验、结尾裁剪、sync_error 等 QC 基础能力。同时 MinIO 实查结果已提供足够证据进行后续方案设计，无需再追问 TeleDex 团队

### Q-20260616-003（Resolved 2026-06-23）

- Related node: D
- Related edge: C->D
- Question: QC方案是否需要考虑后续自动化实施的可行性？
- Resolution: 用户已明确 AutoQC 暂时不需要做。当前工作集中在 manual QC 和 MinIO 数据湖控制面设计上

### Q-20260616-005（Archived 2026-06-23）

- Related node: B
- Related edge: B->C
- Question: LA7 和 Linker Hand 各 DOF 的关节上下限、安全范围、速度限制是否有正式表？
- Resolution: 已降级。当前项目重心已转向 MinIO 数据湖架构，详细的 per-DOF limit 表可在后续 QC 指标精度提升时再做补充

### Q-20260616-006（Archived 2026-06-23）

- Related node: B
- Related edge: B->C
- Question: collect_tactile 是否在实际采集任务中启用？
- Resolution: 已降级。tactile 相关指标不属于 V1 范围，待后续版本再评估
