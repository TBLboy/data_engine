# Main Business Logic

## Status

- Current main path status: Draft

## 技术选型与代码组织

### 技术栈
- 前端：Vue 3 + TypeScript + Vite + Element Plus
- 后端：FastAPI (Python)
- 数据库：PostgreSQL
- 运行环境：Docker Compose（中心主机部署）

### 代码目录结构
```
data_collect/
├── frontend/               # 前端代码根目录
│   ├── src/                # 源码
│   │   ├── api/            # API 请求层
│   │   ├── components/     # 通用组件
│   │   ├── pages/          # 页面组件
│   │   ├── router/         # 路由配置
│   │   ├── stores/         # Pinia 状态管理
│   │   ├── types/          # TypeScript 类型定义
│   │   └── utils/          # 工具函数
│   ├── public/             # 静态资源
│   ├── index.html          # 入口 HTML
│   ├── vite.config.ts      # Vite 配置
│   └── package.json        # 依赖管理
├── backend/                # 后端代码根目录
│   ├── app/                # 核心应用
│   │   ├── api/            # 路由/接口层
│   │   ├── models/         # SQLAlchemy 数据模型
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   ├── services/       # 业务逻辑层
│   │   └── core/           # 配置/数据库连接/中间件
│   ├── converter/          # raw→processed 转换模块
│   ├── metrics/            # L3 指标计算模块
│   ├── scripts/            # 工具脚本
│   ├── main.py             # 应用入口
│   ├── requirements.txt    # Python 依赖
│   └── Dockerfile          # 后端 Docker 镜像
├── docker-compose.yml      # 容器编排（后端 + 数据库）
└── README.md               # 项目说明
```

### 目录组织原则
- `frontend/` 和 `backend/` 完全独立，互不依赖
- 前端构建产物为静态文件（HTML/CSS/JS），部署时由 Nginx 承载
- 后端作为独立服务运行，前端通过 HTTP API 与其通信
- 不允许前后端代码混在同一层目录

## 后端模块

| 模块 | 职责 |
|------|------|
| Scanner | 扫描 collection_data 目录，索引 task_type、batch 和 episode |
| Converter | raw→processed 适配层，5 阶段流水线 |
| DispatchPlanner | 按批次执行抽检比例或全量派发，生成 `qc_task` |
| DataReader | 按帧读取 processed 数据 |
| Metrics | L3 指标计算与摘要生成 |
| ResultStore | 持久化 QC 结果、revision、audit 与批次统计 |

## API 路由

```
POST   /api/ingest/scan
POST   /api/convert/{episode_id}
GET    /api/task-types
GET    /api/task-types/{id}/batches
GET    /api/task-types/{id}/episodes
GET    /api/qc/tasks
GET    /api/qc/batches/{batchId}/dispatch-preview
POST   /api/qc/batches/{batchId}/dispatch-plan
POST   /api/qc/tasks/{id}/assign
GET    /api/episodes/{id}/qc-context
GET    /api/episodes/{id}/frames
POST   /api/qc/manual/{episode_id}
GET    /api/report/batches
```

## 前端页面

| 页面 | 功能 |
|------|------|
| Dashboard | 总览批次规模、抽检覆盖率、样本完成率、pass_rate |
| Database View | 任务目录与 episode 明细浏览 |
| Task Pool | 候选池预览、抽检/全量派发、任务分配 |
| Manual QC | 核心：视频同步播放 + 指标面板 + 判定 |
| QC History | 历史记录、revision、审计追溯 |
| Batch Report | 批次结果汇总/筛选/导出 |

## Manual QC Flow

### 页面定位
- 手动 QC 页面是人工最终裁决页，目标不是重新计算指标，而是借助预计算结果完成视觉质量、任务完成度和关键轨迹问题的快速确认。
- 同一页面服务两类入口：`new` 批次的首次人工质检，以及 `auto_done` 批次的人工复查。
- QC 对象始终是 `processed` episode；若缺少 processed 数据，则先走 `Converter` 适配层。

### 进入方式
- 从 Dashboard 选择批次后点击 `手动质检`，进入该批次的待检 episode 队列。
- 从 Dashboard 选择 `auto_done` 批次后点击 `复查`，进入待复查 episode 队列。
- 从 Database View 直接打开单条 episode，进入独立手动 QC 页面。
- 进入页面前，后端准备 `frames`、`episode summary metrics`、`segment violations`、`existing qc result` 四类数据。

### 页面目标
- 让操作员在最少跳转、最少认知负担下完成 episode 的最终判断。
- 页面不要求操作员自己计算指标，只要求操作员看、核、判、记。
- 页面输出 `pass/fail`、`reason_code`、`note`，以及是否需要返工或重采。

### 页面布局
- 左侧主区域约 60%：三相机同步视频区。
- 右上区域约 25%：episode 摘要、自动分析摘要、关键问题列表。
- 右下区域约 15%：结论面板、reason code、备注、提交按钮。
- 底部横向区域：统一时间轴与遥测曲线联动区。
- 原则：视频始终是第一视觉中心，指标永远只做辅助证据。

### 首屏内容
- episode 基本信息：`task_type`、`batch_id`、`episode_id`、`frame_count`、`duration`、`fps`。
- 当前模式：首次人工质检或自动质检复查。
- episode 总体摘要：`Q_sync`、`Q_visual`、`Q_motion`、`Q_task`、`q(τ)`。
- 问题摘要卡片：例如“第 3 段右手 thumb chatter 超阈值”、“左腕相机 12.4s–14.1s 遮挡严重”。
- 首屏只展示最值得看的异常，不展示所有细节。

### 视频区交互
- 三路视频默认同步播放：`top`、`left_wrist`、`right_wrist`。
- 默认主视图显示 `top`，两个 wrist 视角并列小窗，可切换主视图。
- 支持播放、暂停、逐帧前进、逐帧后退、时间轴拖动、点击跳转、变速播放。
- 用户跳到异常段时，三路视频同时跳到对应帧。
- 若某一路视频缺失或损坏，页面明确提示 warning，但仍允许完成人工判定。

### 时间轴设计
- 时间轴同时显示当前播放位置、段级异常区间、自动 QC 标记点、人工标记点。
- 颜色建议：黄色为接近阈值 `V^N`，红色为超阈值 `V^E`，蓝色为人工关注点，绿色为任务完成关键节点。
- 点击异常区块可直接跳到该段起点附近。
- 通过时间轴把人工检查从“盲看”改成“先看系统认为有问题的地方，再决定是否全程抽查”。

### 指标与曲线区职责
- 该区域只做辅助确认，不要求操作员理解所有数值。
- 默认展示少量高价值曲线：`qpos vs actions` 偏差、`effort`、`sync_validation_max_diff`、手指关键维度轨迹。
- 曲线与视频帧严格联动：当前帧对应竖线，异常段背景高亮，点击曲线位置可跳视频。
- 默认折叠复杂指标明细，避免首屏过乱。

### 推荐检查顺序
- 第一步看首屏摘要，确认系统标出的重点问题。
- 第二步优先跳转红色异常段，检查是否真异常。
- 第三步检查视觉质量：清晰度、曝光、目标物体可见性、手部/指尖可见性。
- 第四步检查动作质量：抖动、停滞、异常回撤、频繁开合等。
- 第五步检查结尾结果：任务是否完成、是否存在“过程很好但任务没做完”。
- 第六步填写最终结论。

### 判定逻辑
- 手动 QC 最终只给整条 episode 出结论，不要求对每个指标单独打分。
- 建议结论结构：`qc_result`、`qc_confidence`、`primary_reason_code`、`secondary_reason_codes[]`、`note`。
- `pass` 表示可进入训练池，`fail` 表示不合格，需要隔离或返工。
- 对 `auto_done` 复查可增加 `review_decision`：`confirm_auto_pass`、`confirm_auto_fail`、`override_auto_result`。
- 自动 QC 的准确率可由复查结果反向统计。

### reason code 交互
- reason code 不以自由文本为主，否则后期统计会失效。
- 交互方式建议为：主原因码必选、次原因码可多选、自由备注可选。
- reason code 一级分类建议直接对应 L2/L3/L4：视觉类、轨迹类、任务类、系统类。
- 页面展示给人时使用中文标签，底层存英文 code。

### 人工标记能力
- 页面支持中途打点：在当前帧添加人工标记、选择标记类型、写短备注。
- 人工标记不一定直接成为最终 reason code，但会帮助操作员回顾和后续复核。
- 典型流程是先在某时刻标“右手抖动”，再继续看，最后提交时选 chatter 作为主原因。

### 首次手动 QC 与自动复查差异
- `new -> 手动QC`：不预设结论，首屏仅显示计算摘要与异常建议，操作员从零作最终判断。
- `auto_done -> 复查`：首屏显示自动 QC 已有结论、理由和重点时间段，操作员任务是确认、推翻或修正。
- 若推翻自动结论，建议要求补充备注，便于分析自动系统误判原因。

### 提交前校验
- 前端提交前校验 `pass/fail` 必选，`fail` 时主原因码必选。
- 若是 override 自动结果，备注建议必填。
- 后端校验 episode 是否存在、是否被占用、提交版本是否冲突。
- 多人协作时建议进入页面即打软锁，标记为 `in_review`。

### 提交后状态流转
- 对 `new` 数据，手动提交后直接变 `done`。
- 对 `auto_done` 数据，复查提交后变 `done`。
- 对 `done` 数据，允许重新质检，但必须保留 revision 记录。
- 提交后写入 `reviewer_id`、`review_mode`、`submitted_at`、`result`、`reason_codes`、`note`、`reviewed_segments`、`auto_result_snapshot`。

### reason code 使用规则矩阵
- 原因码的核心目标是服务三件事：人工裁决、批次统计、自动 QC 复盘。
- 统计口径以 `primary_reason_code` 为主，`secondary_reason_codes` 只做辅助分析，不作为 batch 主失败原因。
- 页面交互上，先选 `qc_result`，再按结果动态限制可选原因码。

#### 1. `pass` 结果下的规则
- `pass` 表示该条 episode 可以进入训练池。
- `pass` 时默认 `primary_reason_code = null`。
- `pass` 时允许填写 `secondary_reason_codes`，但仅限“轻微瑕疵、不影响训练可用性”的 code。
- `pass` 时不允许选择明显失败性质的 code 作为次原因，例如 `task_incomplete`、`grasp_failed`、`camera_missing`、`conversion_issue`。
- `pass` 时若填写次原因码，其业务含义是“可用，但存在轻微问题”，便于后续低权重采样或人工复盘。

#### 2. `fail` 结果下的规则
- `fail` 表示该条 episode 不进入主训练池。
- `fail` 时必须选择且只能选择一个 `primary_reason_code`。
- `fail` 时可追加多个 `secondary_reason_codes`，用于补充伴随问题。
- `primary_reason_code` 必须表达“最主要、最直接导致 fail 的原因”。
- 若同时存在多个严重问题，主原因遵循“最靠前阻断训练可用性”的原则：系统类 > 任务类 > 轨迹类 > 视觉类。

#### 3. 主原因码优先级原则
- 若数据本身不可读、模态缺失、转换损坏，则主原因优先选系统类。
- 若数据可读但任务根本未完成，则主原因优先选任务类。
- 若任务表面完成但动作质量明显不可接受，则主原因优先选轨迹类。
- 若任务完成且动作基本正常，但关键视觉证据不可用，则主原因优先选视觉类。
- 这个优先级是为了保证统计口径稳定，而不是为了描述全部问题；其他问题放到 `secondary_reason_codes`。

#### 4. 允许作为 `primary_reason_code` 的 code
- L2 视觉主原因码：`blur`、`exposure_over`、`exposure_under`、`occlusion_hand`、`occlusion_object`、`hand_not_visible`、`fingertip_not_visible`、`object_not_visible`、`focus_bad`、`depth_invalid`、`camera_missing`
- L3 轨迹主原因码：`motion_abnormal`、`chatter`、`stall`、`saturation`、`spike`、`tracking_error`、`joint_limit_risk`、`low_smoothness`、`path_inefficient`、`effort_abnormal`、`timestamp_jitter`、`sync_bad`、`tactile_abnormal`
- L4 任务主原因码：`task_incomplete`、`wrong_final_state`、`excessive_backtracking`、`grasp_failed`、`transfer_failed`、`placement_failed`、`subtask_order_wrong`
- 系统主原因码：`conversion_issue`、`metadata_missing`、`device_issue`、`modality_missing`、`file_corrupted`、`unsupported_format`

#### 5. 只建议作为 `secondary_reason_codes` 的 code
- `color_cast`：通常是轻微视觉问题，更多用于质量画像，不建议直接作为主失败原因。
- `path_inefficient`：若任务完成且轨迹只是略绕，可作为次原因，不一定直接 fail。
- `timestamp_jitter`：若未明显破坏视觉-动作对应，可先作次原因观察。
- `effort_abnormal`：若只是轻度异常，可先作为次原因，用于设备健康监测。
- 后续如果你们决定更严格门禁，这几个 code 可以再升级为常规主原因码。

#### 6. `secondary_reason_codes` 允许范围
- `pass` 时允许的次原因码建议限制为：`blur`、`exposure_over`、`exposure_under`、`color_cast`、`occlusion_hand`、`occlusion_object`、`fingertip_not_visible`、`path_inefficient`、`timestamp_jitter`、`effort_abnormal`
- `fail` 时允许所有非重复 code 进入次原因码。
- `secondary_reason_codes` 不允许与 `primary_reason_code` 重复。
- `secondary_reason_codes` 建议数量上限为 3，避免一条 episode 被挂过多标签导致统计失真。

#### 7. 自动复查模式的附加规则
- `review_mode = review_auto` 时，若人工与自动结论一致，则 `review_decision` 取 `confirm_auto_pass` 或 `confirm_auto_fail`。
- 若人工推翻自动结论，则 `review_decision = override_auto_result`。
- `override_auto_result` 时建议强制填写 `free_text_note`。
- 若推翻自动结果，同时人工主原因与自动主原因不同，应保留 `auto_result_snapshot` 用于后续统计自动误判类型。

#### 8. 典型判定示例
- 示例 A：图像略过曝，但抓取、转移、放置都完成，动作平稳 → `qc_result = pass`，`primary_reason_code = null`，`secondary_reason_codes = ["exposure_over"]`
- 示例 B：任务没完成，同时末段 wrist 相机也被遮挡 → `qc_result = fail`，`primary_reason_code = "task_incomplete"`，`secondary_reason_codes = ["occlusion_object"]`
- 示例 C：任务完成，但右手 thumb 持续 chatter，抓取过程明显不稳定 → `qc_result = fail`，`primary_reason_code = "chatter"`，`secondary_reason_codes = []`
- 示例 D：processed 文件损坏，视频无法正常载入 → `qc_result = fail`，`primary_reason_code = "file_corrupted"`，`secondary_reason_codes = []`

#### 9. 统计口径建议
- batch 的 Top1 失败原因只统计 `primary_reason_code`。
- 原因共现分析使用 `primary_reason_code + secondary_reason_codes`。
- 自动 QC 准确率统计时，至少比较三项：`qc_result` 是否一致、`primary_reason_code` 是否一致、是否发生 `override_auto_result`。
- `pass with minor issues` 应单独统计，不应混入 fail 原因统计。

### 页面提交交互规则
- 手动 QC 页面结论面板采用“先选结果，再展开后续字段”的交互方式，避免操作员一次看到过多表单项。
- 表单交互的核心原则是：让合法输入尽量顺滑，让非法输入在前端就被拦住。

#### 1. 初始状态
- 页面初始未选择 `qc_result` 时，仅展示：`通过(pass)` 按钮、`不通过(fail)` 按钮、只读的 episode 摘要与自动分析摘要。
- 在未选择 `qc_result` 前，不展示原因码选择器和最终提交按钮。
- 若当前模式为 `review_auto`，首屏同时展示自动 QC 原结论卡片，但人工结论默认仍为空。

#### 2. 选择 `pass` 后的表单行为
- 选中 `pass` 后：
  - `primary_reason_code` 保持隐藏或禁用，默认值为 `null`
  - 展示 `secondary_reason_codes` 多选框，但只允许选择轻微问题码
  - 展示 `free_text_note` 可选输入框
  - 展示 `qc_confidence` 选择器
  - 激活提交按钮
- 若用户此前在 `fail` 状态下已选过主原因码，切换到 `pass` 时应自动清空 `primary_reason_code`。
- 若 `secondary_reason_codes` 中存在 fail-only code，切换到 `pass` 时应自动移除并提示“该原因码仅可用于不通过结果”。
- `pass` 的业务含义是“可进入训练池”，页面提示文案应强调这一点，避免用户把“有轻微问题”误判成 fail。

#### 3. 选择 `fail` 后的表单行为
- 选中 `fail` 后：
  - 强制展示 `primary_reason_code` 单选选择器
  - 展示 `secondary_reason_codes` 多选框
  - 展示 `free_text_note` 输入框
  - 展示 `qc_confidence` 选择器
  - 仅在选定 `primary_reason_code` 后才激活提交按钮
- `primary_reason_code` 一次只能选一个。
- `secondary_reason_codes` 可多选，但建议前端数量上限为 3。
- 若用户从 `pass` 切到 `fail`，原有 `secondary_reason_codes` 仍可保留，但需要重新校验是否与主原因重复。

#### 4. `review_auto` 模式下的附加行为
- `review_mode = review_auto` 时，页面必须额外展示 `review_decision` 区域。
- 建议交互为三个互斥按钮：
  - `确认自动通过` (`confirm_auto_pass`)
  - `确认自动不通过` (`confirm_auto_fail`)
  - `推翻自动结果` (`override_auto_result`)
- 若人工选择的 `qc_result` 与自动结果一致，页面默认高亮对应的 confirm 按钮，但仍允许修改。
- 若人工选择的 `qc_result` 与自动结果不一致，页面自动切换 `review_decision = override_auto_result`。
- `override_auto_result` 时：
  - `free_text_note` 必填
  - 建议要求至少填写一个 `reviewed_segments` 人工核查区间
  - 保留 `auto_result_snapshot`，禁止前端清空

#### 5. 原因码选择器行为
- `primary_reason_code` 采用分组单选：视觉类 / 轨迹类 / 任务类 / 系统类。
- 每个原因码展示中文标签 + 英文 code + 简短说明，避免操作员误选。
- `secondary_reason_codes` 采用分组多选。
- 当前已作为 `primary_reason_code` 的 code，在 `secondary_reason_codes` 中应自动禁用。
- 对于 `pass` 状态下不允许选择的 code，直接隐藏或置灰，并显示“仅不通过可用”。

#### 6. 人工标记与表单联动
- 当操作员在时间轴上新增人工标记后，系统可在结论面板中提示“是否将该标记转为原因码”。
- 若人工标记 tag 与某个标准 reason code 对应，可一键加入 `secondary_reason_codes`。
- 若用户最终选择 `fail`，且存在多个人工标记，页面可推荐其中最频繁或最严重的 tag 作为 `primary_reason_code` 候选，但不自动替用户提交。

#### 7. 提交按钮激活条件
- 初始状态：禁用。
- `pass` 状态：选择完 `qc_result` 即可激活；如果你们后续决定 `qc_confidence` 必填，则需同时选定 confidence 后激活。
- `fail` 状态：必须满足 `qc_result` + `primary_reason_code` 后才可激活。
- `review_auto + override_auto_result`：必须满足 `qc_result` + `primary_reason_code(若fail)` + `free_text_note` 后才可激活。
- 若前端启用“必须看过所有红色异常段”的策略，则在未满足前提交按钮保持禁用。

#### 8. 前端错误提示与拦截规则
- `fail` 未选主原因码时提交：提示“请选择一个主原因码”。
- `pass` 下误选 fail-only 次原因码：提示“该原因码仅适用于不通过结果”。
- `secondary_reason_codes` 与 `primary_reason_code` 重复：提示“次原因码不能与主原因码重复”。
- `override_auto_result` 未填备注：提示“推翻自动结果时请填写说明”。
- `reviewed_segments` 区间非法：提示“核查区间超出 episode 时长或起止顺序错误”。
- 所有错误提示都应直接指向具体字段，不使用笼统的“提交失败”。

#### 9. 提交后的确认反馈
- 提交成功后，页面弹出简短确认：`QC 结果已保存`。
- 若当前来自 batch 队列，提交后自动跳转下一条 episode，并保留当前筛选上下文。
- 若当前来自 database-view 的单条入口，提交后返回上一页或停留当前页显示只读结果。
- 若提交的是 `override_auto_result`，成功提示中可附加“已记录自动结果覆写”。

#### 10. 建议的前端显示文案
- `pass`：通过，可进入训练池
- `fail`：不通过，需隔离/返工
- `primary_reason_code`：主原因（必选）
- `secondary_reason_codes`：次原因（可多选）
- `free_text_note`：补充说明
- `review_decision`：复查结论
- `override_auto_result`：人工推翻自动结果

### 提交数据结构
- 建议手动 QC 提交采用统一 JSON 结构，兼容首次人工质检与自动复查。
- 核心字段分为五类：结果字段、原因码字段、复查字段、人工标记字段、审计字段。

```json
{
  "episode_id": "episode_000123",
  "batch_id": "batch_2026_06_17_01",
  "task_type": "double_linkerhand_grasp",
  "review_mode": "manual",
  "qc_result": "fail",
  "qc_confidence": "high",
  "primary_reason_code": "chatter",
  "secondary_reason_codes": [
    "fingertip_not_visible",
    "task_incomplete"
  ],
  "review_decision": null,
  "free_text_note": "右手拇指出现持续开合抖动，末段也未完成稳定放置。",
  "reviewed_segments": [
    {
      "start_sec": 12.4,
      "end_sec": 14.1,
      "tag": "chatter",
      "note": "right thumb repeated open-close"
    },
    {
      "start_sec": 18.2,
      "end_sec": 20.0,
      "tag": "task_incomplete",
      "note": "object not placed to target state"
    }
  ],
  "auto_result_snapshot": null,
  "reviewer_id": "qc_user_01",
  "submitted_at": "2026-06-17T15:32:10+08:00",
  "client_version": "web-frontend-0.1.0"
}
```

### 提交字段规则
- `review_mode`：`manual` 或 `review_auto`。
- `qc_result`：`pass` 或 `fail`。
- `qc_confidence`：`high`、`medium`、`low`，用于记录人工判断把握度。
- `primary_reason_code`：`fail` 时必填且只能选一个；`pass` 时默认可为空。
- `secondary_reason_codes`：可多选，用于轻微问题或伴随问题记录。
- `review_decision`：仅 `review_auto` 模式使用，取值为 `confirm_auto_pass`、`confirm_auto_fail`、`override_auto_result`。
- `reviewed_segments`：可选，用于保留人工重点核查区间，支持后续复盘和二次复查。
- `auto_result_snapshot`：仅自动复查时可带上，用于保存复查时看到的自动 QC 原始结论快照。
- `reviewer_id`、`submitted_at`、`client_version`：用于审计追踪。

### 提交校验建议
- `pass/fail` 必选。
- `fail` 时 `primary_reason_code` 必填。
- `review_auto` 且 `review_decision = override_auto_result` 时，`free_text_note` 建议必填。
- `secondary_reason_codes` 不可包含与 `primary_reason_code` 完全重复的 code。
- `reviewed_segments` 中的 `start_sec` 必须小于 `end_sec`，且区间不能超出 episode 总时长。

### QC 数据模型与持久化设计
- 人工 QC 链路要稳定落地，必须把“页面提交”落成明确的数据模型，而不是只停留在表单字段层。
- 建议最少拆成四类持久化对象：`episode`、`qc_result`、`qc_review_revision`、`batch_qc_summary`。
- 原则：`episode` 保存当前状态，`qc_result` 保存当前生效结论，`qc_review_revision` 保存历史版本，`batch_qc_summary` 保存聚合结果。

#### 1. `episode`（数据主表，已有或应有）
- 用途：保存一条 episode 的基础信息和当前 QC 状态。
- 关键字段：
  - `episode_id`
  - `task_type`
  - `batch_id`
  - `source_path_raw`
  - `source_path_processed`
  - `frame_count`
  - `duration_sec`
  - `fps`
  - `has_processed`
  - `qc_status`：`new` / `auto_done` / `done` / `in_review`
  - `current_qc_result_id`
  - `current_assignee_reviewer_id`（可空）
  - `last_reviewed_at`
- 设计原则：`episode` 只存当前态，不存全部历史。

#### 2. `qc_result`（当前生效 QC 结论表）
- 用途：保存当前这条 episode 最新、对外生效的 QC 结论。
- 一条 episode 在任一时刻只应有一个当前生效 `qc_result`。
- 建议字段：
  - `qc_result_id`
  - `episode_id`
  - `review_mode`：`manual` / `review_auto` / `recheck`
  - `qc_result`：`pass` / `fail`
  - `qc_confidence`
  - `primary_reason_code`
  - `secondary_reason_codes_json`
  - `review_decision`
  - `free_text_note`
  - `reviewed_segments_json`
  - `auto_result_snapshot_json`
  - `reviewer_id`
  - `submitted_at`
  - `is_active`
- 设计原则：查询当前结论时只查这张表，避免每次都扫 revision 历史。

#### 3. `qc_review_revision`（复核历史版本表）
- 用途：完整记录每次人工提交，保证审计与追溯能力。
- 每次点击提交，无论是首次手动 QC、自动复查还是重新质检，都新增一条 revision。
- 建议字段：
  - `revision_id`
  - `episode_id`
  - `qc_result_id`
  - `revision_no`
  - `action_type`：`manual_submit` / `auto_review_submit` / `recheck_submit`
  - `payload_json`（原始提交 JSON 完整快照）
  - `previous_qc_result_id`
  - `operator_id`
  - `created_at`
- 设计原则：`qc_result` 是当前态，`qc_review_revision` 是历史真相。

#### 4. `batch_qc_summary`（批次统计表）
- 用途：给 Dashboard / Batch Detail / Report 提供快速统计。
- 建议字段：
  - `batch_id`
  - `task_type`
  - `episode_total`
  - `qc_new_count`
  - `qc_auto_done_count`
  - `qc_done_count`
  - `pass_count`
  - `fail_count`
  - `pass_rate`
  - `top_primary_reason_codes_json`
  - `updated_at`
- 设计原则：这是缓存型聚合表，可由提交后异步刷新，也可定时重算。

#### 5. `review_lock`（可选，协作锁表）
- 用途：避免多位 reviewer 同时编辑同一条 episode。
- 建议字段：
  - `episode_id`
  - `reviewer_id`
  - `lock_status`
  - `locked_at`
  - `expires_at`
- 设计原则：软锁即可，不做强事务锁；过期可自动释放。

### 人工 QC 状态机
- 页面链路要产品化，必须把状态流转写死，避免后续多人理解不一致。

#### 1. episode 级状态
- `new`：新入库，尚未经过自动 QC 或人工 QC。
- `in_review`：某位 reviewer 正在人工检查。
- `auto_done`：自动 QC 已完成，等待人工复查。
- `done`：人工最终裁决已完成。

#### 2. 状态流转规则
- `new -> in_review`
  - 触发条件：reviewer 打开手动 QC 页面并成功占用软锁。
- `in_review -> done`
  - 触发条件：reviewer 完成首次人工质检并提交。
- `new -> auto_done`
  - 触发条件：自动 QC 全流程完成。
- `auto_done -> in_review`
  - 触发条件：reviewer 打开复查页面并成功占用软锁。
- `in_review -> done`（复查路径）
  - 触发条件：复查提交完成。
- `done -> in_review`
  - 触发条件：用户点击重新质检，进入新一轮 revision。

#### 3. 状态回写原则
- 页面打开时，不立刻把 `new` 或 `auto_done` 改成 `done`，只能先改成 `in_review`。
- 只有提交成功后才写成 `done`。
- 若页面关闭、崩溃或超时未提交，则释放锁并回退到原状态：
  - 原来是 `new`，回退 `new`
  - 原来是 `auto_done`，回退 `auto_done`

### 人工 QC 端到端业务时序
- 下面这条时序是产品级主链路，建议作为后续前后端实现的统一蓝本。

#### 场景 A：首次人工质检
1. reviewer 在 Dashboard 或 Database View 选择一条 `new` episode。
2. 后端检查 processed 数据是否存在；若不存在，提示先转换。
3. 后端尝试创建 `review_lock`，成功后把 episode 状态改为 `in_review`。
4. 页面加载视频、summary metrics、segment violations、空白结论表单。
5. reviewer 完成检查，填写 `qc_result`、原因码、备注等。
6. 前端校验通过后调用 `POST /api/qc/manual/{episode_id}`。
7. 后端写入一条 `qc_review_revision`。
8. 后端 upsert 当前 `qc_result`，并把旧的 `is_active` 设为 false。
9. 后端把 `episode.qc_status` 改为 `done`，更新 `current_qc_result_id`。
10. 后端刷新 `batch_qc_summary`。
11. 页面提示成功，并按入口决定跳转下一条还是返回列表。

#### 场景 B：自动 QC 后人工复查
1. reviewer 在 Dashboard 选择一条 `auto_done` episode 并点击复查。
2. 后端创建锁并把 episode 状态改为 `in_review`。
3. 页面加载视频、summary metrics、segment violations、自动 QC 原结论。
4. reviewer 选择 `confirm_auto_pass` / `confirm_auto_fail` / `override_auto_result`。
5. 若为 override，前端要求补备注，必要时补 `reviewed_segments`。
6. 提交后，后端同样写 revision + 当前生效 qc_result。
7. 后端把状态改为 `done`，并保留 `auto_result_snapshot` 供统计。
8. 后端刷新 batch 汇总与自动 QC 准确率统计。

#### 场景 C：重新质检
1. 用户从 `done` episode 触发重新质检。
2. 系统复制上一版 `qc_result` 作为页面只读参考，但不直接复用为当前提交。
3. 页面进入 `recheck` 模式。
4. 提交后新增 revision，并替换当前生效结论。
5. 报表中保留版本链，当前页面只显示最新 active 版本。

### 权限与角色建议
- 为了达到产品级链路，建议尽早把角色概念写进逻辑里。
- 最少分三类角色：
  - `collector`：采集人员，只看自己批次结果，不做最终 QC 裁决。
  - `reviewer`：质检员，可执行手动 QC、复查、重检。
  - `admin`：可查看全部 revision、解锁、强制重置状态。
- 一般情况下只有 `reviewer` 和 `admin` 可以提交 `POST /api/qc/manual/{episode_id}`。

### 失败与异常处理规则
- 若提交接口失败，不改变前端已填写内容，允许用户重试。
- 若提交成功但 batch 汇总刷新失败，不回滚 QC 主结果，汇总改为异步补偿重算。
- 若锁已被其他 reviewer 占用，当前用户进入只读模式或提示稍后再试。
- 若 `auto_result_snapshot` 缺失但处于 `review_auto` 模式，允许提交，但记录 warning。
- 若 `reason_code` 已下线或版本不兼容，后端拒绝提交并返回明确错误。

### 推荐新增 API
- `GET /api/episodes/{id}/qc-context`
  - 一次返回手动 QC 页所需上下文：基础信息、summary metrics、自动 QC 摘要、当前锁状态、已有结果。
- `POST /api/episodes/{id}/review-lock`
  - 创建软锁。
- `DELETE /api/episodes/{id}/review-lock`
  - 主动释放软锁。
- `GET /api/episodes/{id}/qc-history`
  - 返回 revision 历史。
- `POST /api/qc/manual/{episode_id}`
  - 统一接收 manual / review_auto / recheck 提交。

### 实施收口建议
- 到目前为止，人工 QC 主链路已经具备：页面流程、原因码体系、表单规则、提交结构、状态机、数据模型、异常处理。
- 本节以下内容作为最终收口结果，视为人工 QC 链路的公司产品级主规范。

## L3 Teleoperation Quality Spec

### 1. 模块定位
- L3 专门负责 **遥操作轨迹质量计算**，它不判断图像质量，也不直接判断任务是否成功。
- L3 的职责是把 `telemetry.npz` 中的遥操作数据转成一组稳定、可解释、可落地的质量指标，供两条链路共同使用：
  - 人工 QC 页面：作为人工核查与裁决证据
  - 自动 QC 流程：作为非视觉自动检测主模块
- 因此 L3 是一个“计算型 QC 模块”，不是 VLM 模块，也不是人工主观判断模块。

### 2. 设计目标
- 指标数量适中：不能太少，导致信息不足；不能太多，导致冗余和维护负担过高。
- 强适配 TeleDex 数据格式：直接消费 `telemetry.npz`、`manifest.json`、`metadata.json`。
- 强适配双臂 + 灵巧手场景：不能照搬夹爪数据集的单末端逻辑。
- 支持 episode 级评分 + segment 级定位，不追求 frame 级全指标。
- 第一版优先高鲁棒性、高可解释性、高工程落地性，不追求学术上最全覆盖。

### 3. 数据输入边界
#### 主输入
- `telemetry.npz`
  - `timestamps`
  - `qpos`
  - `qvel`
  - `effort`
  - `actions`
  - `ee_poses_qpos_left/right`
  - `ee_poses_actions_left/right`
  - `sync_validation_is_valid`
  - `sync_validation_max_diff`
  - `tactile_*`（若存在）

#### 辅助输入
- `manifest.json`
  - `frame_count`
  - `duration`
  - `fps`
  - `sync_error`
- `metadata.json`
  - `alignment`
  - `device`
  - `recording`
- 机器人关节限位配置（来自 URDF / SDK 配置）

### 4. L3 职责边界
#### 属于 L3
- 轨迹平滑度
- 动作稳定性
- 控制效率
- 主从跟踪一致性
- 关节/力矩安全性
- 时间序列规律性
- 可选触觉异常

#### 不属于 L3
- 图像模糊、遮挡、曝光（属于 L2）
- 任务是否完成、最终状态是否正确（属于 L4）
- raw 采集缺话题、转换损坏、硬门禁（属于 L1 或系统类）

### 5. 最终指标清单（v1 收口版）
- 第一版不采用“大而全”策略，而采用 **8 个核心指标 + 2 个可选指标** 的结构。
- 这套组合兼顾稳定性、解释性、灵巧手适配性和工程效率。

#### 5.1 核心必算指标（8个）
1. `ldlj_smoothness`
   - 含义：整体动作平滑度
   - 数据源：`qpos`, `qvel`
   - 粒度：episode + segment
   - 工具：Forge 主算，monalysa 交叉验证

2. `action_saturation_rate`
   - 含义：动作是否长时间触及控制边界
   - 数据源：`actions`
   - 粒度：episode + segment
   - 工具：Forge + 灵巧手边界适配

3. `static_fraction`
   - 含义：异常停滞占比
   - 数据源：`actions`
   - 粒度：episode + segment
   - 工具：Forge

4. `finger_chatter_max`
   - 含义：灵巧手最差手指的颤振程度
   - 数据源：`actions[hand_dims]`
   - 粒度：episode + segment
   - 工具：自定义（基于 DQAF/Forge 思路）

5. `path_efficiency`
   - 含义：末端路径是否过度绕行
   - 数据源：`ee_poses_qpos_left/right`
   - 粒度：episode 为主，segment 可选
   - 工具：自定义

6. `tracking_error`
   - 含义：`qpos` 与 `actions` 的主从跟踪偏差
   - 数据源：`qpos`, `actions`
   - 粒度：episode + segment
   - 工具：自定义

7. `joint_limit_risk`
   - 含义：是否长期逼近关节物理极限
   - 数据源：`qpos` + joint limits
   - 粒度：episode + segment
   - 工具：自定义

8. `effort_abnormality`
   - 含义：异常力矩/负载模式
   - 数据源：`effort`
   - 粒度：episode + segment
   - 工具：自定义（积分 + MAD spike）

#### 5.2 辅助必算指标（2个，轻量）
9. `timestamp_jitter`
   - 含义：时间轴规律性异常
   - 数据源：`timestamps`
   - 粒度：episode
   - 工具：Forge 或自定义

10. `sync_bad_ratio`
   - 含义：L1 已算出的同步异常在 L3 中作为质量背景量继续引用
   - 数据源：`sync_validation_is_valid`, `sync_validation_max_diff`
   - 粒度：episode
   - 工具：直接读取

### 6. 第一版不纳入核心链路的指标
- 为了避免冗余和维护成本，以下指标第一版不作为主链路核心指标：
- `SPARC`：保留为内部验证指标，不进入 v1 主输出；原因是与 LDLJ 高度相关，首版保留一个主平滑度指标更稳。
- `Jerk RMS`：与 LDLJ 信息重叠，保留为调试辅助，不进主规格。
- `Dead Actions`：与 `static_fraction` 高重叠，首版不单列。
- `Action Entropy`：解释性一般，容易受任务类型影响，首版不进主规格。
- `Manipulability`：有理论价值，但依赖 Jacobian/URDF 和数值实现稳定性，首版暂不纳入必算链路。
- `State-Conditioned Action Variance`：更适合跨 episode 数据策展分析，不适合作为单条 episode 的一线 QC 核心指标。
- `PSD Band Energy`：适合研究和诊断，不作为 v1 标准输出。

### 7. 工具策略（最终选型）
#### 主工具：Forge
- 定位：L3 主引擎
- 原因：
  - 直接支持 numpy arrays
  - 与 `telemetry.npz` 高匹配
  - 已覆盖 LDLJ / saturation / static / timestamp regularity 等主指标
  - 工程落地快，解释性好
- 在本项目中的角色：提供 v1 主体计算骨架

#### 辅助工具：monalysa
- 定位：平滑度校验工具
- 角色：仅用于内部验证 `LDLJ/SPARC` 计算一致性，不作为主流程依赖
- 原因：主流程不宜依赖双工具并行输出，否则链路复杂度增加

#### 自定义实现
- 必须自定义的原因：TeleDex 是双臂 + 灵巧手，不是标准夹爪遥操作
- 需要自定义的指标：
  - `finger_chatter_max`
  - `path_efficiency`
  - `tracking_error`
  - `joint_limit_risk`
  - `effort_abnormality`
  - `sync_bad_ratio`

### 8. 灵巧手专项适配策略
#### 8.1 分子系统计算
- 所有 L3 计算都必须按子系统拆分，而不是直接在 D=26 上混算：
  - 左臂：`0:7`
  - 右臂：`7:14`
  - 左手：`14:20`
  - 右手：`20:26`
- 原因：机械臂和灵巧手单位不同、动态特性不同、阈值体系不同。

#### 8.2 手部归一化
- 灵巧手 `qpos/actions` 为 `0~255`，必须在计算 hand 相关指标前归一化到 `[0,1]`。
- 归一化仅用于指标计算，不修改原始数据存储。

#### 8.3 chatter 计算策略
- 不采用夹爪二值开合逻辑，采用 per-finger 独立计算。
- 每根手指单独计算 chatter rate，episode 级输出取 `max`，原因是最差手指通常决定抓取稳定性。
- segment 级输出同时保留 `mean` 作为人工页面辅助信息。

#### 8.4 饱和判定策略
- 臂：按关节物理边界附近阈值判定
- 手：按归一化后接近 `0` 或 `1` 判定
- 手部饱和阈值应比臂更严格，因为灵巧手末端精细动作对饱和更敏感

### 9. 计算粒度策略
#### episode 级
- 用途：排序、汇总、报告、自动 QC 总结
- 输出：10 个最终指标 + `Q_motion`

#### segment 级
- 用途：定位异常区间，服务人工 QC 页面和自动 QC 反馈
- 默认切分：`2.5s/segment`
- 若 fps = 15，则约 37 帧/段
- 若末段不足半段长度，合并到上一段

#### frame 级
- 第一版只保留极少数 frame-level 引用量：
  - `sync_validation_is_valid`
  - `sync_validation_max_diff`
- 不做 frame 级全指标计算，避免噪声过大且工程收益低

### 11. Depth 在 Manual QC 中的产品策略
#### 11.1 是否需要展示 depth
- 需要，但不应该作为人工 QC 的默认主视图。
- 原因不是 depth 不重要，而是人工 QC 的主任务仍然是快速判断“这条 episode 是否可用”，默认视觉中心必须保持在 RGB 三视角与关键指标上。
- 对当前 TeleDex 场景，depth 更适合作为 **辅助证据层**，主要服务以下场景：
  - RGB 中目标物与手部边界不清，需辅助判断遮挡关系
  - 判断是否真的发生接触、接近、离桌过高/过低
  - 物体颜色/背景接近导致 RGB 难以分辨时，辅助判断目标是否仍在视野内
  - 排查 `depth_invalid`、`occlusion_object`、`object_not_visible` 一类问题
- 因此产品结论应是：**depth 要显示，但默认收起，按需调用，不常驻抢占主布局。**

#### 11.2 推荐展示方式
- 第一版推荐采用“单相机视图切换 + 可选分屏对照”，而不是给三路相机全部常驻再加三路 depth。
- 默认状态：页面仍是三路 RGB 同步播放。
- 当 reviewer 对某一路相机需要看 depth 时，在该相机卡片上提供：
  - `RGB` / `Depth` 切换按钮
  - `对照` 按钮：将该相机临时切成 `RGB | Depth` 左右分屏
- 这样做的原因：
  - 不额外挤占主页面固定空间
  - reviewer 只在“有疑问的那一路相机”上打开 depth，认知负担最低
  - 与三相机同步时间轴兼容，不需要重做主布局
- 不建议第一版默认同时展示三路 RGB + 三路 depth，小屏幕和普通办公显示器上会明显过挤，反而降低人工效率。

#### 11.3 人工 QC 页面中的深度职责边界
- depth 在 Manual QC 中的职责是“帮助人判断空间关系”，不是让人直接检查原始 16-bit 深度数值。
- 因此页面给人工看的应当优先是 **depth colormap 预览视频**，而不是原始深度 PNG。
- 原始深度保留给后端算法与高级诊断用途，例如：
  - depth 无效比例统计
  - 距离裁剪异常排查
  - 后续自动 QC 的几何规则检测
- 这意味着前端主读取链路应优先消费 `*_depth_colormap.mp4`，而不是自己在浏览器端实时把 uint16 depth 转成伪彩图。

#### 11.4 深度转换应该如何做
- 从当前样例数据和 requirements 看，上游 processed 流水线已经包含 depth 可视化转换：
  - `requirements.md` 已明确写入“阶段 4：深度预览：深度图 color-map → 预览 MP4”
  - 实际样例目录 `/home/tbl/Project/data_collect/data/raw/process/episode_000099/cameras` 中也已存在：
    - `cam_top_depth_colormap.mp4`
    - `cam_left_wrist_depth_colormap.mp4`
    - `cam_right_wrist_depth_colormap.mp4`
- 所以可以确认：**上游转换链路已经有 depth→可视化预览的过程。**
- QC 软件不应该把“浏览器里临时做 depth 渲染”当作主方案，而应该复用 processed 阶段已经产出的可视化文件。

#### 11.5 推荐的 depth colormap 转换原则
- 第一版产品逻辑层面，不一定要绑定某一个 OpenCV 颜色表名字，但应固定以下规则：
  - 输入：原始 `uint16` 深度，单位 mm
  - 先做有效深度裁剪：剔除 0 值、异常远值、异常近值
  - 再做区间归一化：把有效深度映射到 8-bit 可视化区间
  - 最后做伪彩映射并编码为 MP4
- 推荐采用“按相机/按 episode 稳定范围”而不是“逐帧自适应范围”作为默认策略。
- 原因：逐帧自适应虽然每帧都更鲜艳，但会导致同一物体在相邻帧里颜色跳变，人工检查时非常难看。
- 更合适的第一版做法是：
  - 对每个 episode 的每个相机，使用固定 depth 可视化范围
  - 0 值/无效值统一映射为黑色或指定背景色
  - 超出上限值截断，不让色带随帧抖动
- 这条规则比“具体用 TURBO / JET / VIRIDIS 哪个颜色表”更重要。

#### 11.6 这个功能应该集成在哪里
- 应集成在 **raw→processed 转换适配层 / Converter**，不应集成在 Manual QC 页面内部。
- 原因：
  - depth 可视化本质上属于 processed 衍生资产生成，不属于 review-time 交互逻辑
  - 若每次打开页面再临时转码，会增加加载延迟、前端复杂度和结果不一致风险
  - 统一在 Converter 产出后，Manual QC、Database View、后续 AutoQC 都可以复用同一份结果
- 因此系统分层建议是：
  - `Converter`：负责生成 `*_depth_colormap.mp4`
  - `manifest.json`：负责登记 depth 预览文件索引
  - `DataReader`：负责按需提供 depth preview 帧/流
  - `Manual QC UI`：只负责显示和切换，不负责计算 colormap

#### 11.7 对现有样例结构的一个发现
- 当前样例 `manifest.json` 的 `files.cameras` 只正式登记了 RGB `video` 和 `timestamps`，没有把 depth 预览文件写进去。
- 但 episode 目录中实际已经存在 depth 相关文件。
- 这说明产品规格上最好补一条：`manifest.json` 后续应正式索引 depth 资产，至少包括：
  - `depth_raw_dir` 或等价引用
  - `depth_timestamps`
  - `depth_preview_video`
- 否则前端需要额外猜文件名，链路会变脆。

#### 11.8 `manifest.json` depth 索引规范（建议正式化）
- 为了避免前端靠文件名猜测 depth 资产，建议把 depth 也纳入 `manifest.json` 正式索引。
- 每个 camera 节点建议至少包含：
  - `video`
  - `timestamps`
  - `depth_raw_dir`
  - `depth_timestamps`
  - `depth_preview_video`
- 推荐结构示例：

```json
{
  "files": {
    "cameras": {
      "cam_left_wrist": {
        "video": "cameras/cam_left_wrist.mp4",
        "timestamps": "cameras/cam_left_wrist.timestamps.npy",
        "depth_raw_dir": "cameras/cam_left_wrist_depth",
        "depth_timestamps": "cameras/cam_left_wrist_depth.timestamps.npy",
        "depth_preview_video": "cameras/cam_left_wrist_depth_colormap.mp4"
      }
    }
  }
}
```

#### 11.9 前后端接口层收口建议
- `GET /api/episodes/{id}/qc-context`
  - 返回人工 QC 首屏需要的主信息，并告知各相机是否存在 `depth_preview_video`
- `GET /api/episodes/{id}/frames`
  - 默认返回 RGB 帧
  - 支持 `view_mode=rgb|depth_preview`
  - 支持 `camera=cam_top|cam_left_wrist|cam_right_wrist`
- `GET /api/episodes/{id}/depth-raw`
  - 仅后端诊断或后续算法模块使用，不给普通 reviewer 默认调用
- 这样可以把“人工预览”和“算法读取原始深度”彻底拆开，避免接口混乱。

#### 11.10 第一版最终建议
- Manual QC 中展示 depth，但作为辅助视图，不作为默认主视图。
- 默认主页面维持三路 RGB + 时间轴 + 指标摘要。
- 某一路相机需要进一步核查时，reviewer 可切换该路为 depth colormap，或打开 RGB/Depth 对照。
- 前端显示用 `*_depth_colormap.mp4`。
- 原始 `uint16` depth 保留在后端与转换链路，用于算法和诊断，不作为人工主显示源。
- depth colormap 生成放在 `Converter`，并补充到 `manifest.json` 正式索引。
- 这样最符合你们当前“processed 为主、人工 QC 高效优先、后续自动 QC 可复用”的整体架构。

#### 10.4 `finger_chatter_max`
- 每指独立算开合切换率
- 每只手输出：`finger_max`, `finger_mean`
- episode 主输出取双手总体 `max`
- 人工页面显示时可下钻到具体手指

#### 10.5 `path_efficiency`
- 分左右臂分别计算末端实际路径长度与起终点直线距离之比
- 若任务天然需要弧线动作，仍保留该指标，但只作为软指标，不单独硬失败
- episode 主输出取双臂较差值

#### 10.6 `tracking_error`
- 分左右臂、左右手分别算 `|qpos-actions|` 平均偏差
- 手部误差必须在归一化空间算，不能直接和 arm rad 空间混合
- episode 主输出分成 `arm_tracking_error` 与 `hand_tracking_error` 两个内部量，再映射到统一 `tracking_error`

#### 10.7 `joint_limit_risk`
- 仅对机械臂作为必算指标
- 灵巧手若后续拿到稳定关节物理限位，可扩展；第一版手部不纳入 joint limit 核心统计
- episode 主输出取双臂较差值

#### 10.8 `effort_abnormality`
- 组合两部分：
  - effort 积分（整体负载水平）
  - effort spike density（MAD 异常尖峰密度）
- 两者合成一个 `effort_abnormality` 输出，避免单独拆太多指标

#### 10.9 `timestamp_jitter`
- 计算 `diff(timestamps)` 的均值、标准差、变异系数
- 对外主输出使用 jitter ratio
- 若上游 fixed-fps 对齐已经很稳定，该指标大多用于发现异常 episode，而非日常主导评分

#### 10.10 `sync_bad_ratio`
- 直接读取 `sync_validation_is_valid == false` 的占比
- 不重新发明同步指标，复用上游已有结果
- 在 L3 中它更像“背景质量权重”，用于解释其他指标是否可信

### 11. 阈值策略（v1）
- 阈值分三层，不搞一刀切：
#### 第一层：硬阈值
- 用于明显异常拦截
- 例如：
  - `sync_bad_ratio` 过高
  - `finger_chatter_max` 极高
  - `joint_limit_risk` 极低
  - `tracking_error` 极大

#### 第二层：软阈值
- 基于任务级历史分布（建议 p95 / p05）
- 用于 warning、排序、低分但不直接 fail

#### 第三层：人工解释阈值
- 用于页面显示红黄区间
- 红：显著超阈
- 黄：接近阈值

### 12. L3 最终输出结构
#### 面向人工 QC 页面
- `Q_motion`
- 10 个核心指标摘要
- segment 级异常列表
- 每个异常的时间区间、指标名、严重度、建议标签

#### 面向自动 QC 流程
- `Q_motion`
- `motion_fail_flags[]`
- `motion_warning_flags[]`
- 供 L4/VLM 汇总使用的结构化文本摘要

#### 面向 batch/report
- episode 级 `Q_motion`
- 主异常类型
- 是否命中高风险标记
- 用于统计的主指标分桶结果

### 13. L3 评分聚合策略
- v1 不建议把 10 个指标直接平均。
- 建议采用“分组聚合 + 权重”方式：
  - 平滑度组：`ldlj_smoothness`
  - 稳定性组：`static_fraction`, `finger_chatter_max`
  - 效率组：`action_saturation_rate`, `path_efficiency`
  - 一致性组：`tracking_error`, `effort_abnormality`
  - 安全性组：`joint_limit_risk`
  - 时序背景组：`timestamp_jitter`, `sync_bad_ratio`
- 再将各组映射到统一 `Q_motion`。
- 原因：组内指标相关性高，先组内聚合可减少某一类指标过度主导总分。

### 14. v1 最终推荐实现方案
- **主引擎**：Forge
- **辅助校验**：monalysa（仅内部验证）
- **自定义补充**：`finger_chatter_max`、`path_efficiency`、`tracking_error`、`joint_limit_risk`、`effort_abnormality`、`sync_bad_ratio`
- **最终核心指标数**：8 核心 + 2 轻量背景 = 10
- **计算粒度**：episode + segment 为主，frame 级只保留同步引用量
- **适用场景**：同时服务人工 QC 页面与自动 QC 非视觉模块

### 15. 业务结论
- L3 不应做成一个“学术指标堆砌模块”，而应做成一个“企业级遥操作质量计算模块”。
- 对你当前的数据格式和双臂灵巧手场景，**Forge 为主、自定义补充为辅、10 个指标收口** 是当前最鲁棒、最高效、最可落地的版本。
- 这版 L3 规范可以直接进入后续产品设计、API 设计和实现拆分。

## QC Platform Data & Operations Spec

### 1. 模块定位
- 本模块定义 QC 软件的**平台级数据与运营架构**，解决的不是单一页面问题，而是整套系统如何在公司环境中真正运行起来。
- 它覆盖四类核心能力：
  - 数据入库与集中存储
  - 多电脑访问与部署方式
  - 账号、角色与任务派发
  - 结果留痕、审计与溯源
- 这部分是 Manual QC、AutoQC、Report、Batch 管理等上层业务的共同底座。

### 2. 背景约束与设计目标
#### 已知公司背景
- 公司有空余台式机，可长期复用为系统主机。
- 公司当前没有正式服务器机房。
- 可接受低成本租借服务器，但不希望把主数据放在高成本云端。
- 优先要求数据保存在公司本地，可控、低成本、可持续运维。
- 系统需要支持不同员工在不同电脑上访问同一套数据与 QC 结果。

#### 设计目标
- 让数据集中、访问统一、结果可追溯。
- 在小公司成本约束下，优先实现“够稳定、够简单、够可运维”的方案。
- 不为了理论最先进而引入高复杂度基础设施。
- 为后续 AutoQC、批次统计、重检、审计、远程访问预留扩展空间。

### 3. 总体落地架构（最终推荐）
- 最终推荐采用：**公司本地 1 台中心主机 + 浏览器访问 + 本地集中存储 + PostgreSQL + 任务派发 + 审计留痕**。
- 这是结合你当前背景后，最适合的企业可落地方案。

#### 架构原则
- 大文件集中存本地，不分散到员工电脑。
- 结构化业务数据统一入数据库，不靠扫目录临时计算。
- 员工电脑只作为访问终端，不承担主数据保存职责。
- 云资源仅作为可选补充，不作为第一阶段主存储。

#### 第一阶段推荐部署形态
- 1 台公司内部常开台式机作为 `qc-platform-host`
- 运行：
  - `Vue` 前端静态站点
  - `FastAPI` 后端服务
  - `PostgreSQL`
  - 本地文件存储目录
- 所有员工通过浏览器访问，不要求本地安装完整系统。

#### 为什么不推荐的方案
- 不推荐“每个员工电脑各存一份数据”
- 不推荐“只有共享目录、没有数据库索引”
- 不推荐“小公司第一版就上复杂云原生集群/Kubernetes”
- 不推荐“一开始就把主数据全部迁到公网云对象存储”

### 4. 数据入库与存储架构
#### 4.1 存储总原则
- 采用 **文件存储 + 关系数据库索引** 的混合模式。
- 大文件落磁盘，业务元数据落数据库。
- 系统必须同时理解“文件资产”和“业务实体”，不能只认其中一边。

#### 4.2 数据分层
- `raw`：原始采集数据层
  - 保存采集软件输出的原始 episode 数据
  - 原则上只增不改，作为底档和追溯源
- `processed`：标准 QC 工作数据层
  - 保存转换后的 `telemetry.npz`、视频、深度、元数据等
  - 是 Manual QC / AutoQC 的直接输入层
- `qc_artifacts`：QC 衍生资产层
  - 保存自动检测产物、人工截图、导出报告、诊断中间文件
- `business_db`：平台业务层
  - 保存用户、任务、批次、episode、状态、结果、审计、统计索引

#### 4.3 推荐目录逻辑
- 推荐采用稳定、中心化的数据目录：
  - `/data/raw/...`
  - `/data/processed/...`
  - `/data/qc_artifacts/...`
  - `/data/backup/...`
- 数据库中只保存这些目录下资产的：
  - 逻辑归属
  - 绝对路径或受控相对路径
  - 文件 hash / 版本
  - 是否有效 / 是否缺失
  - 与 task / batch / episode 的映射关系

#### 4.4 文件与数据库边界
- 存磁盘的内容：
  - 视频、深度图、`telemetry.npz`、截图、报告文件、大型 JSON/NPY
- 存数据库的内容：
  - task / batch / episode 基础信息
  - raw / processed 可用性状态
  - QC 状态与结论
  - 任务分配关系
  - 审计日志
  - 统计缓存
- 不建议把大文件二进制直接塞进数据库。

#### 4.5 主机硬件建议
- 系统盘：SSD
- 数据盘：大容量 HDD
- 备份盘：外接 HDD 或第二块盘
- 若预算允许，优先升级：
  - 数据盘容量
  - 备份盘
  - UPS / 简单断电保护
- 第一阶段不要求专用服务器，但要求主机稳定、可长期常开。

### 5. 入库流程规范
#### 5.1 入库触发原则
- 新数据进入公司数据主机后，不能只停留在“目录里多了文件”。
- 系统必须把“文件存在”转成“平台内已建档的业务对象”。

#### 5.2 标准入库链路
1. 采集端把新 batch 数据拷贝/同步到中心主机的 `raw` 区域。
2. `Scanner` 扫描到新任务目录 / 新 batch / 新 episode。
3. 系统创建或更新：
   - `task_type`
   - `batch`
   - `episode`
4. 系统检查该 episode 是否已有 `processed` 产物。
5. 若无 processed，则标记为 `needs_convert`，等待 `Converter`。
6. 若已有 processed，则直接进入 `processed_ready` 候选状态。
7. 系统不默认立即为全部 episode 创建 QC 任务，而是先进入待抽检候选池。
8. `qc_manager` / `admin` 按 batch 发起派发计划：默认按百分比抽检，也可切换为全量派发。
9. 系统仅为抽中的 sample episode 创建 QC 任务并进入待派发池。

#### 5.3 入库状态建议
- `raw_detected`
- `indexed`
- `needs_convert`
- `processed_ready`
- `sampling_candidate`
- `task_created`
- `qc_queue_ready`
- 这些是平台内部运营状态，不等于最终 QC 判定状态。

#### 5.4 入库异常处理
- raw 目录不完整：标记 `ingest_error`
- processed 缺关键文件：标记 `processed_invalid`
- metadata 不一致：标记 `metadata_warning`
- 文件损坏：标记 `asset_corrupted`
- 异常 episode 仍应建档，但不能直接进入正常 QC 队列。

### 6. 多电脑访问与部署模式
#### 6.1 标准访问方式
- 平台采用 Web 访问。
- 所有员工通过浏览器使用同一套系统。
- 员工电脑只负责访问与操作，不作为主数据承载节点。

#### 6.2 第一阶段部署建议
- 在本地主机上使用 `Docker Compose` 统一管理：
  - 前端服务
  - 后端 API
  - `PostgreSQL`
  - 可选后台 worker
- 第一阶段不要求拆分成多台服务器。
- 目标是先把可运行的中心化平台稳定落地。

#### 6.3 网络访问策略
- 默认访问范围：公司局域网
- 访问形式：内网 IP 或固定内网域名
- 若后续出现跨地点办公需求：
  - 优先采用 `Tailscale` / `WireGuard` / VPN
  - 或租便宜 VPS 只做远程入口/反向代理
- 主数据默认不离开公司本地。

#### 6.4 分阶段扩展策略
- 第一阶段：单机中心主机
- 第二阶段：本地中心主机 + 远程 VPN 访问
- 第三阶段：本地存储主机 + 独立应用主机（若并发和负载上升）
- 这样升级时不需要推倒重来。

### 7. 账号、角色与权限体系
#### 7.1 是否需要账号
- 必须需要。
- 因为没有账号就无法实现：
  - 任务派发
  - 责任归属
  - 结果留痕
  - 重检审批
  - 自动结果覆写追踪

#### 7.2 角色定义（最终推荐）
- `admin`
  - 管理系统配置、账号、解锁、强制状态修复、查看全量审计
- `qc_manager`
  - 管理任务派发、复查调度、批次推进、报表查看
- `reviewer`
  - 执行手动 QC、自动复查、填写结论
- `viewer`
  - 只读查看数据与报表，不可提交

#### 7.3 权限矩阵（核心）
- `admin`
  - 可查看全部任务 / 全部结果 / 全部审计
  - 可强制解锁
  - 可发起重检
  - 可重置异常状态
- `qc_manager`
  - 可分配任务
  - 可查看批次进度与 reviewer 工作量
  - 可发起复查/重检流程
  - 默认不可直接修改历史审计记录
- `reviewer`
  - 只能处理分配给自己或自己认领的任务
  - 可提交 Manual QC / Review Auto 结果
  - 不可删除历史结果
- `viewer`
  - 只读浏览，无提交权限

### 8. 任务派发与待办机制
#### 8.1 是否需要任务派发
- 必须需要。
- 因为这套系统不是个人工具，而是多人协作平台。
- 没有派发机制会导致：
  - 重复质检
  - 新数据无人负责
  - 积压不可见
  - 责任人不明确

#### 8.2 任务粒度建议
- 平台视角：按 `batch` 管理
- 执行视角：按 `episode` 派发
- 即：主管看批次推进，reviewer 看个人 episode 待办。

#### 8.3 标准派发链路
1. 新 batch 入库并完成建档
2. processed 就绪的 episode 先进入抽检候选池
3. 系统默认等待 `qc_manager` / `admin` 选择派发计划：按比例抽检或全量派发
4. 若选择按比例抽检，系统按 batch 生成 sample 子集
5. 系统仅为 sample 集创建 QC 任务并进入 `pending_assign`
6. `qc_manager` 指派 reviewer，或允许 reviewer 自主认领
7. 任务进入 `assigned`
8. reviewer 打开任务后进入 `in_review`
9. reviewer 提交结果后进入 `review_done` / `auto_done_wait_human` / `closed`
10. 若后续决定补派剩余样本或切换全量派发，再为未抽中的 episode 增量创建任务

#### 8.4 推荐任务状态
- `pending_assign`
- `assigned`
- `in_review`
- `review_done`
- `auto_done_wait_human`
- `recheck_required`
- `closed`

#### 8.5 任务流转原则
- 每个 episode 同时只能有一个 active reviewer 任务。
- 批次可以由多个 reviewer 并行处理，但单条 episode 不允许并发写入。
- 任务分配变更必须进入审计日志。
- reviewer 的首页必须有“我的待办”视图。
- `processed_ready` / `sampling_candidate` 表示可被派发，但不等于已经生成 `qc_task`。
- 抽检派发下必须把“候选总量”“已抽中样本量”“已完成样本量”分开统计，避免把未抽样 episode 误判成积压任务。

### 9. 结果留痕、审计与溯源体系
#### 9.1 设计原则
- QC 结果不是一次性表单提交，而是需要长期追溯的业务证据。
- 系统必须默认支持：
  - 谁做了什么
  - 在什么时间做的
  - 为什么这么判
  - 后来有没有被改动

#### 9.2 三层留痕模型
- **操作事件层**
  - 记录登录、派发、认领、打开页面、提交、解锁、重检、导出等行为
- **结果版本层**
  - 记录每次 QC 提交的版本快照
- **任务流转层**
  - 记录任务从创建到关闭全过程的状态变化

#### 9.3 核心审计字段
- `operator_id`
- `role`
- `action_type`
- `task_id`
- `batch_id`
- `episode_id`
- `before_status`
- `after_status`
- `payload_snapshot`
- `created_at`
- 可选：`client_version`、`source_ip`

#### 9.4 结果保存原则
- 当前生效结果单独保存，便于快速读取。
- 历史 revision 永久保留，不可覆盖。
- 审计事件与业务结果分开建模。
- 自动结果被人工推翻时，必须保留自动原结果快照。

### 10. 平台级数据库实体建议
#### 10.1 主业务实体
- `task_type`
- `batch`
- `episode`
- `qc_task`
- `user`
- `role`

#### 10.2 QC 结果实体
- `qc_result`
- `qc_review_revision`
- `auto_qc_result`
- `review_lock`

#### 10.3 审计与运营实体
- `audit_event`
- `task_assignment_history`
- `batch_qc_summary`
- `ingest_job`
- `convert_job`

#### 10.4 建模原则
- `episode` 保存当前态
- `qc_result` 保存当前 active 结论
- `qc_review_revision` 保存每次人工提交真相
- `audit_event` 保存动作历史
- `qc_task` 保存运营分配和待办状态
- 抽检计划与补派动作至少要在 `audit_event.payload_snapshot` 中落审计，V1.0 可先不单独拆 `sampling_plan` 表

### 11. 平台级状态机建议
#### 11.1 episode 运营状态
- `raw_detected`
- `indexed`
- `needs_convert`
- `processed_ready`
- `sampling_candidate`
- `qc_queue_ready`
- `in_review`
- `done`
- `recheck_required`
- `archived`

#### 11.2 QC 任务状态
- `pending_assign`
- `assigned`
- `in_review`
- `review_done`
- `auto_done_wait_human`
- `recheck_required`
- `closed`

#### 11.3 关键流转
- `raw_detected -> indexed -> needs_convert -> processed_ready -> qc_queue_ready`
- `qc_queue_ready -> assigned -> in_review -> review_done -> closed`
- `auto_done_wait_human -> in_review -> review_done -> closed`
- `closed -> recheck_required -> assigned -> in_review -> closed`

### 12. 低成本企业落地建议（最终推荐）
#### 第一阶段
- 复用公司空余台式机
- 部署单机版平台
- 本地磁盘保存主数据
- 局域网内浏览器访问
- 完成账号、派发、留痕闭环

#### 第二阶段
- 增加自动备份盘
- 增加 VPN 远程访问
- 增加异地冷备/低成本云备份

#### 第三阶段
- 若数据量和并发增长，再拆成：
  - 本地数据主机
  - 独立应用主机
- 但数据主存储仍优先留在公司本地

### 13. 本模块业务结论
- 对你当前公司背景，**本地中心主机 + 浏览器访问 + PostgreSQL + 本地集中存储 + 账号派发 + 审计留痕** 是最合适的企业可落地架构。
- 这套方案在成本、可运维性、本地可控性和后续扩展性之间达到了最均衡。
- 后续工程实现时，应直接按本模块展开：
  - 数据库表设计
  - API 设计
  - 账号权限实现
  - 入库与任务创建流程
  - 审计日志链路

### 14. 平台级数据库表设计（字段级收口版）
- 本节不是工程 migration 文件，而是业务逻辑层的字段级主规范。
- 目标是把前面已经收口的平台架构、任务机制、留痕逻辑正式落成一组可实现的数据模型。
- 设计原则继续严格贴合你的背景：小公司、本地主机优先、多人协作、需要任务派发和审计溯源。

#### 14.1 `task_type`
- 用途：保存任务种类定义，支撑 Dashboard 下拉选择、任务种类管理、统计聚合。
- 主键：`task_type_id`
- 核心字段：
  - `task_type_id`
  - `task_code`（英文稳定编码，唯一）
  - `task_name`（中文显示名）
  - `is_active`
  - `description`
  - `created_at`
  - `updated_at`
- 约束建议：
  - `task_code` 唯一
  - 逻辑删除优先，不建议物理删除
- 设计说明：
  - 任务种类是平台级主维度，不能只靠目录名临时推断。

#### 14.2 `batch`
- 用途：保存一次入库事件对应的一批数据，是主管管理与统计的核心对象。
- 主键：`batch_id`
- 核心字段：
  - `batch_id`
  - `task_type_id`
  - `batch_name`
  - `source_root_path`
  - `ingest_status`
  - `episode_total`
  - `raw_episode_count`
  - `processed_ready_count`
  - `qc_new_count`
  - `qc_auto_done_count`
  - `qc_done_count`
  - `created_by`
  - `ingested_at`
  - `updated_at`
- 外键：
  - `task_type_id -> task_type.task_type_id`
- 约束建议：
  - 同一 `task_type_id` 下 `batch_name` 唯一
- 设计说明：
  - batch 是运营视角的核心单位，后续任务派发和进度统计都围绕它展开。

#### 14.3 `episode`
- 用途：保存单条 episode 的当前态，是 Manual QC / AutoQC / Report 的核心实体。
- 主键：`episode_id`
- 核心字段：
  - `episode_id`
  - `task_type_id`
  - `batch_id`
  - `episode_name`
  - `source_path_raw`
  - `source_path_processed`
  - `raw_available`
  - `processed_available`
  - `frame_count`
  - `duration_sec`
  - `fps`
  - `qc_status`
  - `ops_status`
  - `current_qc_result_id`
  - `current_auto_qc_result_id`
  - `current_assignee_reviewer_id`
  - `last_reviewed_at`
  - `created_at`
  - `updated_at`
- 外键：
  - `task_type_id -> task_type.task_type_id`
  - `batch_id -> batch.batch_id`
- 状态字段建议：
  - `qc_status`：`new` / `auto_done` / `in_review` / `done`
  - `ops_status`：`raw_detected` / `indexed` / `needs_convert` / `processed_ready` / `sampling_candidate` / `qc_queue_ready` / `recheck_required` / `archived`
- 约束建议：
  - `episode_name` 在同一 `batch_id` 下唯一
- 设计说明：
  - `episode` 只存当前态，不直接承担完整历史责任，历史交给 revision 与 audit 表。

#### 14.4 `user`
- 用途：保存平台账号。
- 主键：`user_id`
- 核心字段：
  - `user_id`
  - `username`
  - `display_name`
  - `password_hash`
  - `email`（可空）
  - `is_active`
  - `last_login_at`
  - `created_at`
  - `updated_at`
- 约束建议：
  - `username` 唯一
- 设计说明：
  - 第一版适合内建账号体系，不需要为小公司场景一开始引入复杂 SSO。

#### 14.5 `role`
- 用途：保存平台角色定义。
- 主键：`role_id`
- 核心字段：
  - `role_id`
  - `role_code`
  - `role_name`
  - `description`
  - `created_at`
- 推荐角色：
  - `admin`
  - `qc_manager`
  - `reviewer`
  - `viewer`
- 约束建议：
  - `role_code` 唯一

#### 14.6 `user_role`
- 用途：保存用户与角色关系。
- 主键：`user_role_id`
- 核心字段：
  - `user_role_id`
  - `user_id`
  - `role_id`
  - `assigned_at`
  - `assigned_by`
- 外键：
  - `user_id -> user.user_id`
  - `role_id -> role.role_id`
- 约束建议：
  - `user_id + role_id` 唯一
- 设计说明：
  - 用关联表而不是把角色硬塞在 user 表里，便于后续扩展多角色场景。

#### 14.7 `qc_task`
- 用途：保存平台派发给 reviewer 的实际 QC 待办任务，仅针对已进入抽检样本集或全量派发集的 episode。
- 主键：`qc_task_id`
- 核心字段：
  - `qc_task_id`
  - `task_type_id`
  - `batch_id`
  - `episode_id`
  - `task_source`
  - `dispatch_mode`
  - `sampling_ratio`
  - `task_status`
  - `priority`
  - `assignee_user_id`
  - `assigned_by`
  - `assigned_at`
  - `claimed_at`
  - `started_at`
  - `completed_at`
  - `due_at`
  - `recheck_round`
  - `created_at`
  - `updated_at`
- 外键：
  - `task_type_id -> task_type.task_type_id`
  - `batch_id -> batch.batch_id`
  - `episode_id -> episode.episode_id`
  - `assignee_user_id -> user.user_id`
- 状态建议：
  - `pending_assign`
  - `assigned`
  - `in_review`
  - `review_done`
  - `auto_done_wait_human`
  - `recheck_required`
  - `closed`
- 约束建议：
  - 同一 `episode_id` 在同一时刻只能存在一个 active 任务
- 设计说明：
  - `qc_task` 是运营派发对象，不等于 QC 结果本身。
  - V1.0 如不单独建 `sampling_plan` 表，至少要在任务和审计中保留生成该任务时的派发模式与抽检比例。

#### 14.8 `task_assignment_history`
- 用途：保存任务派发、转派、认领历史。
- 主键：`assignment_history_id`
- 核心字段：
  - `assignment_history_id`
  - `qc_task_id`
  - `from_user_id`
  - `to_user_id`
  - `action_type`
  - `note`
  - `created_at`
  - `operator_id`
- 外键：
  - `qc_task_id -> qc_task.qc_task_id`
- 行为类型建议：
  - `assign`
  - `reassign`
  - `claim`
  - `unassign`
- 设计说明：
  - 这张表承担任务责任链追溯，不应被 `qc_task` 当前字段替代。

#### 14.9 `auto_qc_result`
- 用途：保存自动 QC 当前结论与摘要。
- 主键：`auto_qc_result_id`
- 核心字段：
  - `auto_qc_result_id`
  - `episode_id`
  - `run_no`
  - `qc_result`
  - `primary_reason_code`
  - `secondary_reason_codes_json`
  - `l2_summary_json`
  - `l3_summary_json`
  - `l4_summary_json`
  - `segment_flags_json`
  - `model_version`
  - `status`
  - `created_at`
  - `updated_at`
- 外键：
  - `episode_id -> episode.episode_id`
- 设计说明：
  - 自动结果必须单独建模，不能和人工结果混成一张“谁都能写”的表。

#### 14.10 `qc_result`
- 用途：保存当前对外生效的人工 QC 结果。
- 主键：`qc_result_id`
- 核心字段：
  - `qc_result_id`
  - `episode_id`
  - `review_mode`
  - `qc_result`
  - `qc_confidence`
  - `primary_reason_code`
  - `secondary_reason_codes_json`
  - `review_decision`
  - `free_text_note`
  - `reviewed_segments_json`
  - `auto_result_snapshot_json`
  - `reviewer_id`
  - `submitted_at`
  - `is_active`
  - `created_at`
  - `updated_at`
- 外键：
  - `episode_id -> episode.episode_id`
  - `reviewer_id -> user.user_id`
- 约束建议：
  - 同一 `episode_id` 只能有一条 `is_active = true`
- 设计说明：
  - `qc_result` 追求当前态快速查询，历史责任交给 revision 表。

#### 14.11 `qc_review_revision`
- 用途：保存每次人工提交的完整历史快照，是最终审计真相表之一。
- 主键：`revision_id`
- 核心字段：
  - `revision_id`
  - `episode_id`
  - `qc_result_id`
  - `revision_no`
  - `action_type`
  - `payload_json`
  - `previous_qc_result_id`
  - `operator_id`
  - `created_at`
- 外键：
  - `episode_id -> episode.episode_id`
  - `qc_result_id -> qc_result.qc_result_id`
- 行为类型建议：
  - `manual_submit`
  - `auto_review_submit`
  - `recheck_submit`
- 设计说明：
  - 无论首检、复查、重检，都必须新增 revision，禁止覆盖历史。

#### 14.12 `review_lock`
- 用途：保存当前软锁状态，防止多人并发修改同一 episode。
- 主键：`review_lock_id`
- 核心字段：
  - `review_lock_id`
  - `episode_id`
  - `qc_task_id`
  - `reviewer_id`
  - `lock_status`
  - `locked_at`
  - `expires_at`
  - `released_at`
- 外键：
  - `episode_id -> episode.episode_id`
  - `reviewer_id -> user.user_id`
- 约束建议：
  - 同一 `episode_id` 同时最多一条有效锁
- 设计说明：
  - 你们是多电脑协作场景，软锁是必需项，不是可有可无。

#### 14.13 `audit_event`
- 用途：保存关键操作审计日志。
- 主键：`audit_event_id`
- 核心字段：
  - `audit_event_id`
  - `operator_id`
  - `role_code`
  - `action_type`
  - `task_id`
  - `batch_id`
  - `episode_id`
  - `before_status`
  - `after_status`
  - `payload_snapshot`
  - `client_version`
  - `source_ip`
  - `created_at`
- 外键：
  - `operator_id -> user.user_id`
- 行为范围建议：
  - 登录
  - 派发
  - 认领
  - 提交
  - 解锁
  - 重检
  - 导出
- 设计说明：
  - `audit_event` 是行为留痕表，不应与业务结果表混用。

#### 14.14 `batch_qc_summary`
- 用途：保存 Dashboard / Batch Detail / Report 所需的批次统计缓存。
- 主键：`batch_qc_summary_id`
- 核心字段：
  - `batch_qc_summary_id`
  - `batch_id`
  - `task_type_id`
  - `episode_total`
  - `sampling_mode`
  - `sampling_ratio`
  - `sampled_episode_count`
  - `sample_coverage_rate`
  - `qc_new_count`
  - `qc_auto_done_count`
  - `qc_done_count`
  - `dispatch_completion_rate`
  - `sample_review_completion_rate`
  - `pass_count`
  - `fail_count`
  - `pass_rate`
  - `top_primary_reason_codes_json`
  - `updated_at`
- 外键：
  - `batch_id -> batch.batch_id`
- 设计说明：
  - 这是缓存型聚合表，允许异步重算，不要求每次都全量现算。
  - `pass_rate` 默认只基于已完成人工 QC 的样本集计算，不以整批 episode_total 直接做分母。

#### 14.15 `ingest_job`
- 用途：保存入库扫描任务记录。
- 主键：`ingest_job_id`
- 核心字段：
  - `ingest_job_id`
  - `batch_id`
  - `job_status`
  - `scan_root_path`
  - `detected_episode_count`
  - `indexed_episode_count`
  - `error_message`
  - `started_at`
  - `finished_at`
  - `created_at`
- 设计说明：
  - 入库不是瞬时动作，必须可追踪，否则后续很难排查为什么某批数据没进系统。

#### 14.16 `convert_job`
- 用途：保存 raw → processed 转换任务记录。
- 主键：`convert_job_id`
- 核心字段：
  - `convert_job_id`
  - `episode_id`
  - `job_status`
  - `source_raw_path`
  - `target_processed_path`
  - `converter_version`
  - `error_message`
  - `started_at`
  - `finished_at`
  - `created_at`
- 设计说明：
  - 转换链路是你们平台的重要适配层，必须显式建模。

### 15. 字段级统一约束建议
#### 15.1 时间字段
- 所有主表必须带：
  - `created_at`
  - `updated_at`（若该表需要被修改）
- 所有提交/动作型表必须带明确业务时间字段，例如：
  - `submitted_at`
  - `assigned_at`
  - `started_at`
  - `finished_at`

#### 15.2 JSON 字段使用原则
- 可用 JSON 保存但不宜强拆表的字段：
  - `secondary_reason_codes_json`
  - `reviewed_segments_json`
  - `top_primary_reason_codes_json`
  - `payload_snapshot`
  - `l2/l3/l4_summary_json`
- 不建议把核心状态、主键关系、当前责任人存在 JSON 里。

#### 15.3 逻辑删除原则
- `task_type`、`user`、`role` 等主数据优先逻辑删除或禁用。
- `qc_result`、`qc_review_revision`、`audit_event` 不应做任意物理删除。

#### 15.4 唯一性与并发原则
- 同一 `episode` 同时只能有一个 active `qc_result`
- 同一 `episode` 同时只能有一个有效 `review_lock`
- 同一 `episode` 同时只能有一个 active `qc_task`
- 这些约束是多人协作稳定性的关键。

### 16. 表之间的关系主线
- `task_type -> batch -> episode`
- `episode -> auto_qc_result`
- `episode -> qc_result -> qc_review_revision`
- `episode -> review_lock`
- `episode -> qc_task -> task_assignment_history`
- `user -> user_role -> role`
- `user -> qc_result / review_lock / audit_event / task_assignment_history`
- `batch -> batch_qc_summary`

### 17. 贴合你背景的最终数据库方案结论
- 对你现在的小公司背景，这套表设计有三个优势：
  - 不依赖昂贵基础设施，适合本地主机 + PostgreSQL 直接落地
  - 足够支持多人协作、任务派发、审计追溯
  - 后续做 AutoQC、报表、权限系统时不需要推翻重来
- 所以数据库层最终建议不是追求最复杂，而是追求：
  - 字段边界清楚
  - 当前态与历史态分离
  - 任务、结果、审计三条线分开建模
- 这版字段级规范已经可以直接作为后续后端表结构设计和 API 设计蓝本。

### 17.1 V1.0 API Business Interface Spec

#### 17.1.1 模块定位
- 本节定义 V1.0 可落地版本的后端 API 业务接口规范。
- 目标不是写 OpenAPI 细节，而是先把**接口边界、职责、调用顺序、返回对象、权限要求**定清楚。
- 这套接口必须严格服务当前 V1.0 目标：
  - 本地部署
  - 多人协作
  - 人工 QC 主链闭环
  - 任务派发
  - 结果留痕
  - 基础统计
- 明确不为 V1.0 预埋复杂 AutoQC 接口主链。

#### 17.1.2 设计原则
- 前后端分离，前端只通过 HTTP API 访问数据。
- 接口优先围绕业务对象设计，而不是围绕数据库表直接暴露。
- 大文件走受控读取接口，不让前端直接拼本地磁盘路径。
- 写接口必须带审计语义，不能只做“写表成功”。
- 同一业务页面尽量有聚合上下文接口，避免前端首屏发过多碎请求。

#### 17.1.3 V1.0 接口分组
- `Auth & Me`
- `TaskType / Batch / Episode`
- `Ingest / Convert`
- `QC Task Queue`
- `Manual QC Context & Submit`
- `Frames / Metrics / Depth Preview`
- `QC History / Audit`
- `Report / Batch Summary`

#### 17.1.4 Auth & Me
- `POST /api/auth/login`
  - 用途：用户登录
  - 输入：`username`、`password`
  - 输出：`access_token` 或 session、`user_profile`、`roles[]`
  - 权限：公开接口
- `POST /api/auth/logout`
  - 用途：用户登出
  - 审计：记录 `logout` 行为
- `GET /api/me`
  - 用途：返回当前登录用户信息与角色
  - 输出：`user_id`、`username`、`display_name`、`roles[]`、`permissions[]`(可选)

#### 17.1.5 TaskType / Batch / Episode 查询接口
- `GET /api/task-types`
  - 用途：返回任务种类列表
  - 输出：`task_type_id`、`task_code`、`task_name`、`is_active`
- `GET /api/task-types/{taskTypeId}/batches`
  - 用途：返回某任务种类下的批次汇总
  - 输出：`batch_id`、`batch_name`、`episode_total`、`qc_new_count`、`qc_auto_done_count`、`qc_done_count`、`pass_rate`、`updated_at`
- `GET /api/task-types/{taskTypeId}/episodes`
  - 用途：返回某任务种类下全量 episode 明细
  - 支持筛选：`batch_id`、`qc_status`、`qc_result`、`assignee_user_id`、`keyword`
  - 输出：`episode_id`、`batch_id`、`episode_name`、`frame_count`、`duration_sec`、`qc_status`、`current_qc_result`、`primary_reason_code`、`assignee_user`
- `GET /api/batches/{batchId}`
  - 用途：返回 batch 详情页所需基础信息
- `GET /api/episodes/{episodeId}`
  - 用途：返回单条 episode 基础信息
  - 输出：`source_path_raw`、`source_path_processed`、`raw_available`、`processed_available`、`frame_count`、`duration_sec`、`fps`、`qc_status`、`ops_status`

#### 17.1.6 Ingest / Convert 接口
- `POST /api/ingest/scan`
  - 用途：手动触发一次数据扫描建档
  - 权限：`admin` / `qc_manager`
  - 输出：`ingest_job_id`、`job_status`
  - 业务动作：扫描目录、建档、标记 `needs_convert` / `processed_ready` / `sampling_candidate`，但不默认立即为整批创建 QC 任务
- `GET /api/ingest/jobs`
  - 用途：查询入库扫描任务列表
- `POST /api/convert/{episodeId}`
  - 用途：对缺少 processed 的 episode 触发转换
  - 权限：`admin` / `qc_manager`
  - 输出：`convert_job_id`、`job_status`
- `GET /api/convert/jobs`
  - 用途：查看转换任务状态

#### 17.1.7 QC Task Queue 接口
- `GET /api/qc/tasks`
  - 用途：查询 QC 任务池或“我的待办”
  - 支持筛选：`task_status`、`assignee_user_id`、`batch_id`、`task_type_id`、`mine=true`
- `POST /api/qc/batches/{batchId}/dispatch-plan`
  - 用途：为某个 batch 创建或更新派发计划
  - 权限：`qc_manager` / `admin`
  - 输入：`dispatch_mode=sampled|full`、`sampling_ratio`、`note`(可选)
  - 输出：`sampled_episode_count`、`sample_coverage_rate`、`created_task_count`
  - 审计：写 `audit_event`，记录派发模式、抽检比例、补派说明
- `GET /api/qc/batches/{batchId}/dispatch-preview`
  - 用途：返回该 batch 当前候选总量、已抽中数量、未抽中数量、当前派发模式
  - 权限：`qc_manager` / `admin`
- `POST /api/qc/tasks/{taskId}/assign`
  - 用途：主管派发任务给 reviewer
  - 权限：`qc_manager` / `admin`
  - 输入：`assignee_user_id`、`note`(可选)
  - 审计：写 `task_assignment_history` + `audit_event`
- `POST /api/qc/tasks/{taskId}/claim`
  - 用途：reviewer 自主认领任务
  - 权限：`reviewer`
  - V1.0 可先保留接口，不强制开放前端入口
- `POST /api/qc/tasks/{taskId}/close`
  - 用途：关闭任务
  - 权限：`qc_manager` / `admin`

#### 17.1.8 Manual QC Context & Submit
- `GET /api/episodes/{episodeId}/qc-context`
  - 用途：返回 Manual QC 页面首屏所需聚合上下文
  - 输出：episode 基础信息、batch/task_type 信息、`qc_task` 当前状态、`review_lock` 状态、当前 active `qc_result`、最近一次自动结果(若有)、L3 摘要入口引用、depth 预览可用性
- `POST /api/episodes/{episodeId}/review-lock`
  - 用途：申请人工质检软锁
  - 输出：`lock_status`、`locked_at`、`expires_at`
- `DELETE /api/episodes/{episodeId}/review-lock`
  - 用途：主动释放软锁
- `POST /api/qc/manual/{episodeId}`
  - 用途：提交 Manual QC / review_auto / recheck 结果
  - 输入至少包括：`review_mode`、`qc_result`、`primary_reason_code`、`secondary_reason_codes`、`free_text_note`、`review_decision`、`reviewed_segments`、`qc_confidence`、`client_version`
  - 后端标准动作：校验权限与锁、写 `qc_review_revision`、更新 active `qc_result`、更新 `episode.qc_status`、更新 `qc_task.task_status`、释放锁、写 `audit_event`、触发 `batch_qc_summary` 刷新

#### 17.1.9 Frames / Metrics / Depth Preview
- `GET /api/episodes/{episodeId}/frames`
  - 用途：读取视频帧或预览帧
  - 参数：`camera`、`frame_index`、`view_mode=rgb|depth_preview`
- `GET /api/episodes/{episodeId}/metrics`
  - 用途：返回 L3 摘要与异常段信息
  - 输出：`Q_motion`、核心指标摘要、segment 异常区间、时间轴标注数据
- `GET /api/episodes/{episodeId}/depth-preview`
  - 用途：查询 depth 预览可用性或读取 depth 预览资源

#### 17.1.10 QC History / Audit
- `GET /api/episodes/{episodeId}/qc-history`
  - 用途：查看该 episode 的人工 QC 历史
- `GET /api/audit`
  - 用途：查看审计事件列表
  - 权限：`admin` / `qc_manager`
  - 支持筛选：`operator_id`、`action_type`、`batch_id`、`episode_id`、`time_range`

#### 17.1.11 Report / Batch Summary
- `GET /api/report/batches`
  - 用途：返回批次级统计结果
  - 输出：`episode_total`、`sampling_mode`、`sampling_ratio`、`sampled_episode_count`、`sample_coverage_rate`、`qc_done_count`、`sample_review_completion_rate`、`pass_count`、`fail_count`、`pass_rate`、`top_primary_reason_codes`
- `GET /api/report/episodes`
  - 用途：按 episode 粒度查询结果列表
  - 支持筛选：`task_type_id`、`batch_id`、`qc_result`、`primary_reason_code`、`reviewer_id`

#### 17.1.12 接口权限边界总结
- 公开接口：`POST /api/auth/login`
- 登录后可读：`GET /api/me`、`GET /api/task-types`、`GET /api/task-types/{id}/batches`、`GET /api/task-types/{id}/episodes`、`GET /api/episodes/{id}`
- reviewer 可写：`POST /api/episodes/{id}/review-lock`、`DELETE /api/episodes/{id}/review-lock`、`POST /api/qc/manual/{episodeId}`
- `qc_manager` / `admin` 可写：`POST /api/ingest/scan`、`POST /api/convert/{episodeId}`、`POST /api/qc/tasks/{id}/assign`、`POST /api/qc/tasks/{id}/close`
- 仅 `admin` / `qc_manager` 可审计查看：`GET /api/audit`

#### 17.1.13 V1.0 明确不做的接口范围
- 不做 AutoQC 主链接口组作为 V1.0 核心交付要求
- 不做复杂 websocket 协同接口
- 不做复杂 BI 导出接口
- 不做外部 SSO / LDAP 对接接口
- 不做公网开放 API

#### 17.1.14 接口级业务结论
- 到这里，V1.0 已经具备了从**功能范围 -> 数据模型 -> API 边界**的完整主规范。
- 对你当前背景，最合理的落地方式就是：
  - 本地主机部署
  - 浏览器访问
  - 人工 QC 主链优先
  - 数据入库、派发、提交、统计全靠这套接口串起来
- 因此后续工程实现可以直接按本节接口组推进前后端开发，而不需要再先补业务逻辑定义。

## V1.0 前端页面与数据流规范

### 1. 模块定位
- 本节定义 V1.0 可落地版本的前端页面清单、页面间跳转、数据加载策略和状态边界。
- 它不是 UI 设计稿，而是**页面级业务逻辑 + 数据依赖 + 用户动线**的产品规范。
- 每个页面都必须说清楚：干什么、加载什么、从哪来、去哪、出异常怎么处理。

### 2. V1.0 完整页面清单
- V1.0 共定义 6 个主页面 + 1 个通用组件：

| 序号 | 页面 ID | 页面名称 | 必需角色 | V1.0 说明 |
|------|---------|----------|----------|-----------|
| 1 | `login` | 登录页 | 无(公开) | 内建账号登录 |
| 2 | `dashboard` | 主界面/批次总览 | 所有登录用户 | 核心入口，按角色展示不同内容 |
| 3 | `database-view` | 数据库/Episode 列表 | 所有登录用户 | 全量检索与筛选入口 |
| 4 | `manual-qc` | 人工质检页 | `reviewer` / `qc_manager` / `admin` | V1.0 核心生产页面 |
| 5 | `task-pool` | 任务派发/管理 | `qc_manager` / `admin` | 主管操作页面 |
| 6 | `qc-history` | QC 历史与审计 | `admin` / `qc_manager` | 追溯与审计入口 |
| 通用 | `qc-reason-picker` | 原因码选择器(组件) | — | 被 manual-qc 复用 |

### 3. 全局页面状态规范
- 每个页面必须覆盖这些状态边界，V1.0 不做缺省：
  - `loading` — 正在加载关键数据
  - `empty` — 无数据可展示
  - `error` — 接口或数据异常
  - `ready` — 正常可交互
  - `submitting` — 表单正在提交
- 任何页面都不允许直接展示"空白+无提示"。

### 4. 页面之间主跳转关系（用户动线）
- `login -> dashboard`
- `dashboard -> database-view`（某 task_type 下全量数据）
- `dashboard -> manual-qc`（选中批次，进入质检）
- `database-view -> manual-qc`（选中 episode 进入质检）
- `dashboard -> task-pool`（主管进入派发管理）
- `task-pool -> dashboard`
- `manual-qc -> dashboard | database-view | 下一条 episode`（提交后根据入口决定跳转去向）
- `dashboard | database-view -> qc-history`（查看历史）

### 5. 各页面详细规范

#### 5.1 Login（登录页）
- 页面目标：用户认证入口
- 数据依赖：`POST /api/auth/login`
- 页面状态：
  - `ready`：展示用户名/密码输入框与登录按钮
  - `submitting`：按钮禁用，显示"登录中"
  - `error`：明确提示"用户名或密码错误"，不清空已输入内容
- 成功后：根据角色跳转到 `dashboard`
- 登录失败：不暴露后端具体错误原因，统一提示认证失败
- 登出：`POST /api/auth/logout` 后回到登录页

#### 5.2 Dashboard（主界面/批次总览）
- 页面目标：全局入口 + 批次进度一屏可览 + 快速进入质检
- 数据依赖：
  - 首次：`GET /api/task-types`
  - 选 task_type 后：`GET /api/task-types/{taskTypeId}/batches`
  - reviewer 附加：`GET /api/qc/tasks?mine=true`（我的待办角标）
- 页面布局：
  - 顶部：任务种类下拉选择器（支持搜索）
  - 中间：批次列表（表格或卡片）
  - 侧栏：我的待办 / 任务池 / 数据库快捷入口
- 批次列表展示：`batch_name`、`episode_total`、`sampled_episode_count`、`sample_coverage_rate`、样本完成进度、`pass_rate`、操作按钮
- 状态颜色：灰色(new)、橙色(auto_done)、绿色(done)
- 按钮按角色可见：
  - `reviewer`：手动质检 + 进入数据库
  - `qc_manager`：额外看到"派发任务"入口
  - `viewer`：只看到"进入数据库"（只读）
- V1.0 裁剪：不做自动质检按钮，不做复查按钮，只有 new/done 两态
- 状态边界：`loading` / `empty` / `error` / `ready`

#### 5.3 Database View（数据库/Episode 列表）
- 页面目标：按 task_type 全量检索与筛选 episode
- 数据依赖：`GET /api/task-types/{taskTypeId}/episodes`（支持筛选参数）
- 页面布局：
  - 顶部：当前 task_type 面包屑 + 返回按钮
  - 筛选区：batch 下拉、qc_status 下拉、关键字搜索、重置
  - 中间：episode 列表（分页）
  - 底部：分页控件
- 每行展示：`episode_id`、`batch_name`、`frame_count`、`duration`、`qc_status`、`qc_result`、`primary_reason_code`、操作按钮
- 支持筛选：按 batch、qc_status、qc_result、关键字搜索，支持组合筛选
- 状态边界：`loading` / `empty` / `error` / `ready`
- 跳转：点击"进入质检"-> `manual-qc`，点击"查看历史"-> `qc-history`

#### 5.4 Task Pool（任务派发/管理页）
- 页面目标：主管查看候选池与任务池，决定按抽检比例还是全量派发，再把已生成任务分配给 reviewer
- 数据依赖：
  - `GET /api/qc/tasks`
  - `GET /api/qc/batches/{batchId}/dispatch-preview`
  - `POST /api/qc/batches/{batchId}/dispatch-plan`
  - `POST /api/qc/tasks/{taskId}/assign`
  - `POST /api/qc/tasks/{taskId}/close`
- 页面布局：筛选区（状态、reviewer、batch）+ 抽检计划区 + 任务列表 + 派发操作
- 抽检计划区展示：候选总量、已抽中样本数、未抽中数量、当前派发模式、抽检比例
- 每行：`qc_task_id`、`episode_id`、`batch_name`、`task_status`、`priority`、`dispatch_mode`、`assignee_user`、操作
- 派发交互：先选择 `sampled` 或 `full`，若为 `sampled` 再填写比例 -> 生成任务 -> 下拉选 reviewer -> 确认 -> 状态刷新
- 支持按 batch 批量派发
- 状态边界：`loading` / `empty` / `error` / `ready`

#### 5.5 Manual QC（人工质检页）
- 页面目标：质检员完成单条 episode 的人工核查与裁决
- 数据依赖：
  - `GET /api/episodes/{episodeId}/qc-context`（聚合上下文）
  - `GET /api/episodes/{episodeId}/frames`（视频帧）
  - `GET /api/episodes/{episodeId}/metrics`（L3 摘要与异常段）
  - `POST /api/episodes/{episodeId}/review-lock`（进入时）
  - `DELETE /api/episodes/{episodeId}/review-lock`（退出时）
  - `POST /api/qc/manual/{episodeId}`（提交时）
- 进入页面标准流程：
  1. 请求 `GET /api/episodes/{episodeId}/qc-context`
  2. 请求 `POST /api/episodes/{episodeId}/review-lock`
  3. 锁成功 -> 进入质检
  4. 锁失败 -> 提示当前被谁占用，或进入只读模式
- 页面布局（与 Manual QC Spec 对齐）：
  - 左侧 60%：三相机同步视频区
  - 右上 25%：episode 摘要 + 关键问题列表
  - 右下 15%：结论面板 + 原因码选择器
  - 底部：时间轴 + 遥测曲线
- 首屏展示：
  - episode 基本信息
  - L3 摘要：`Q_motion`、异常段列表
  - 当前 QC 状态和已有结果
  - 检查顺序引导
- 视频区交互：
  - 三路同步播放/暂停/逐帧
  - 时间轴拖动/点击跳转/异常段高亮
  - depth 切换按钮（RGB -> depth_preview），V1.0 先做单路切换
- 结论面板交互：
  - 初始只显示 [通过(pass)] [不通过(fail)]
  - 选 pass -> 次原因码多选 + 备注 + [提交]
  - 选 fail -> 主原因码单选 + 次原因码多选 + 备注 + [提交]
  - 原因码选择器使用 `qc-reason-picker` 组件
- 提交前校验：pass/fail 必选，fail 必选 primary_reason_code
- 提交后：
  - 成功：弹出"QC 结果已保存" -> 释放锁 -> 自动加载下一条或返回列表
  - 失败：表单内容不丢失，显示错误详情，允许重试
- 退出行为：
  - 已提交：正常释放锁
  - 未提交：提示"当前检查未提交，是否放弃？"-> 确认后释放锁并回退状态
- 状态边界：`loading` / `lock-failed` / `ready` / `submitting` / `submitted`

#### 5.6 QC History（QC 历史与审计页）
- 页面目标：查看 episode 历史 QC 记录 + 系统审计事件
- 数据依赖：`GET /api/episodes/{episodeId}/qc-history`、`GET /api/audit`
- 页面布局：搜索区 + 审计事件列表（表格视图）
- 每行：操作人、角色、动作、时间、变更前后状态、关联 episode
- V1.0：基础表格视图，不做复杂可视化
- 状态边界：`loading` / `empty` / `error` / `ready`

### 6. 跨页面数据一致性与刷新策略
- Dashboard 刷新时机：reviewer 提交 QC 后、主管派发后、抽检计划更新后、手动刷新
- Database View 刷新时机：从 manual-qc 返回后、筛选条件改变时、手动刷新
- V1.0 不需要 websocket 推送，页面可见时自然刷新即可

### 7. 全局异常处理规范
- 网络异常：顶部提示"网络连接异常，请检查网络后重试"
- 服务异常(5xx)：提示"服务暂时不可用，请稍后重试"
- 认证过期(401)：跳回登录页，显示"登录已过期，请重新登录"
- 权限不足(403)：显示"您没有权限访问此页面"，不跳转
- 资源不存在(404)：显示"该数据不存在或已被移除"

### 8. 前端构建与部署约定（V1.0）
- 前端独立构建为静态文件（HTML/CSS/JS），部署时由中心主机 Web 服务承载
- 所有 API 请求走统一配置的后端地址
- V1.0 用 SPA 模式，不要求 SSR/SEO
- 前端版本号通过统一配置文件注入

### 9. 前端页面与后端接口映射表
| 页面 | 依赖的 API |
|------|-----------|
| `login` | `POST /api/auth/login`、`POST /api/auth/logout` |
| `dashboard` | `GET /api/task-types`、`GET /api/task-types/{id}/batches`、`GET /api/qc/tasks?mine=true` |
| `database-view` | `GET /api/task-types/{id}/episodes`、`GET /api/episodes/{id}` |
| `task-pool` | `GET /api/qc/tasks`、`GET /api/qc/batches/{batchId}/dispatch-preview`、`POST /api/qc/batches/{batchId}/dispatch-plan`、`POST /api/qc/tasks/{id}/assign`、`POST /api/qc/tasks/{id}/close` |
| `manual-qc` | `GET /api/episodes/{id}/qc-context`、`GET /api/episodes/{id}/frames`、`GET /api/episodes/{id}/metrics`、`GET /api/episodes/{id}/depth-preview`、`POST /api/episodes/{id}/review-lock`、`DELETE /api/episodes/{id}/review-lock`、`POST /api/qc/manual/{episodeId}` |
| `qc-history` | `GET /api/episodes/{id}/qc-history`、`GET /api/audit` |

### 10. 本模块业务结论
- 到这里，V1.0 的前端已经不是在"列想法"，而是每个页面都有了：
  - 明确的目标
  - 明确的数据依赖（直接对应已定义的 API）
  - 明确的用户动线和跳转关系
  - 明确的状态边界（loading/empty/error/ready/submitting）
  - 明确的异常处理
- 这版前端规范可以直接作为后续前端实现蓝本，不需要再填补业务逻辑层面的缺口。

### 18. V1.0 功能范围清单（公司可用闭环版）
- 本节用于给当前软件定义一版**可上线、可交付、可在公司真实使用**的 V1.0 功能边界。
- 设计原则不是“功能越多越好”，而是“尽快形成可用闭环”。
- 因为你的当前目标非常明确：先尽快给公司交一版能用的完整版本，验证效果，再继续做高级能力。

#### 18.1 V1.0 产品目标
- V1.0 的目标不是做成智能化平台，而是做成一套**多人可协作的人工 QC 管理系统**。
- 它必须满足以下最小闭环：
  - 新数据能入库
  - 数据能被扫描、建档、进入待检池
  - 主管能派发任务
  - reviewer 能登录并做人工质检
  - 结果能保存、可追溯
  - 主管能看到批次进度和基本统计
- 若这 6 件事没闭环，就不算 V1.0 完成。

#### 18.2 V1.0 必做功能范围（In Scope）
##### A. 数据入库与扫描
- 支持公司本地主机上的中心化数据目录。
- 支持扫描 `collection_data` 结构，识别：
  - `task_type`
  - `batch`
  - `episode`
- 支持识别 raw / processed 是否存在。
- 支持将扫描结果建档进入数据库。
- 支持把异常 episode 标成：
  - `needs_convert`
  - `processed_invalid`
  - `ingest_error`
- 业务价值：保证新数据进入系统，而不是只停留在磁盘目录里。

##### B. raw→processed 适配转换
- 支持对缺少 processed 的 raw 数据执行转换。
- 转换结果至少包括：
  - `telemetry.npz`
  - `manifest.json`
  - `metadata.json`
  - `camera_info.json`
  - RGB 视频
  - depth 预览视频
- 第一版允许转换是手动触发，不强求全自动调度。
- 业务价值：避免上游偶尔不转数据时，QC 平台完全无法工作。

##### C. 账号登录与角色权限
- 支持内建账号体系。
- 支持至少 4 类角色：
  - `admin`
  - `qc_manager`
  - `reviewer`
  - `viewer`
- 支持登录、登出、账号禁用。
- 支持按角色限制页面与操作权限。
- 业务价值：没有账号，就无法派发、追责、溯源。

##### D. 任务派发与待办列表
- 支持系统把 processed-ready episode 先纳入候选池，而不是默认立即全量建任务。
- 支持 `qc_manager` 按 batch 选择默认百分比抽检或手动切换为全量派发。
- 支持系统按抽检比例生成 sample 任务集，并支持后续补派剩余 episode。
- 支持 `qc_manager` 按 batch / episode 派发给 reviewer。
- 支持 reviewer 查看“我的待办”。
- 支持任务状态流转：
  - `pending_assign`
  - `assigned`
  - `in_review`
  - `review_done`
  - `closed`
- V1.0 中允许先不做复杂抢单机制，优先保证主管派发可用。
- 业务价值：在控制任务量的前提下，让系统真正进入多人协作模式。

##### E. Dashboard / 主界面
- 支持任务种类下拉选择与搜索。
- 支持展示各 task_type 下 batch 列表。
- 支持每个 batch 显示：
  - episode 总数
  - 已抽检样本数
  - 抽检覆盖率
  - 样本已完成数
  - `qc_status` 状态
  - `pass_rate`
- 支持从 Dashboard 进入：
  - 任务数据库页
  - 批次详情/待检列表
  - Manual QC 页面
- V1.0 中主界面必须服务“看进度 + 发任务 + 找入口”，不追求花哨运营面板。

##### F. Database View / 数据库页面
- 支持查看某 task_type 下的全部 episode。
- 支持按 batch、状态、结果筛选。
- 支持搜索 `episode_id` / `batch_name`。
- 支持从列表进入 Manual QC。
- 业务价值：主管和 reviewer 需要有一个完整检索入口，而不只靠主界面列表。

##### G. Manual QC 主链
- 支持三路视频同步播放。
- 支持逐帧前进/后退、时间轴拖动、点击跳转。
- 支持显示 L3 预计算摘要与 segment 异常区间。
- 支持 reason code、备注、pass/fail 提交。
- 支持 review lock，避免并发覆盖。
- 支持自动保存最终结果、revision 历史、当前 active 结果。
- depth 作为辅助视图保留在 V1.0 内，但不做过度复杂交互。
- 业务价值：这是 V1.0 最核心的生产功能。

##### H. 结果存储与审计留痕
- 支持保存当前 active `qc_result`。
- 支持保存 `qc_review_revision` 历史。
- 支持保存 `audit_event`。
- 支持查询“谁在什么时间对哪条 episode 提交了什么结果”。
- 支持重检新增版本，不覆盖历史。
- 业务价值：保证这不是演示工具，而是可管理的公司系统。

##### I. 批次进度与基础统计
- 支持按 batch 汇总：
  - `episode_total`
  - `sampled_episode_count`
  - `sample_coverage_rate`
  - `qc_done_count`
  - `sample_review_completion_rate`
  - `pass_count`
  - `fail_count`
  - `pass_rate`
  - `top_primary_reason_codes`
- 支持 Dashboard 与基础 Report 共用同一统计口径。
- 第一版只做基础统计，不做复杂 BI 分析。
- 业务价值：主管必须能实际看到质检推进情况，也能明确知道当前只是抽检而不是全检。

##### J. 本地部署与多电脑访问
- 支持部署在公司一台中心主机上。
- 支持局域网内通过浏览器访问。
- 支持前后端分离部署，后端作为独立服务运行。
- 支持本地磁盘集中保存数据。
- 业务价值：符合你当前“有空余台式机、优先本地存储、低成本上线”的现实条件。

#### 18.3 V1.0 建议做但不必阻塞上线的功能（Nice to Have）
- reviewer 首页展示个人工作量统计
- batch 详情页显示更丰富原因分布
- 登录操作日志页面
- convert job / ingest job 的简单列表页
- depth 视图中的 RGB/depth 对照模式
- 这些可以做，但不应阻塞主闭环上线。

#### 18.4 V1.0 明确不做功能范围（Out of Scope）
##### A. AutoQC 全链路
- 不做自动图像检测
- 不做 VLM 判定
- 不做自动任务完成度判断
- 不做自动结果写回人工复查流
- 原因：这是高级能力，不是 V1.0 可用闭环的前置条件。

##### B. 高级运营能力
- 不做复杂 SLA 管理
- 不做多级审批流
- 不做复杂工时核算
- 不做部门级组织架构管理
- 原因：超出当前公司规模与 V1 验证目标。

##### C. 高级基础设施能力
- 不做 Kubernetes
- 不做对象存储集群
- 不做高可用多副本数据库
- 不做复杂微服务拆分
- 原因：当前阶段成本和维护复杂度不匹配。

##### D. 高级分析与智能功能
- 不做高级 BI 仪表盘
- 不做异常趋势预测
- 不做 reviewer 质量评分模型
- 不做自动推荐最优 reviewer
- 原因：这些属于 V2+ 优化能力。

##### E. 复杂远程办公体系
- 不做公网直接暴露服务
- 不做企业 SSO / LDAP 集成
- 不做多办公点分布式主存储
- 原因：先以内网可用、本地稳定为主。

#### 18.5 V1.0 最小交付判定标准
- 只有以下条件都满足，才算 V1.0 真正完成：
1. 新 batch 能入库并建档。
2. raw 缺 processed 时可被识别并支持手动转换。
3. 主管能按 batch 配置抽检比例或切换为全量派发。
4. 系统只为已抽中的样本或全量派发集创建任务。
5. reviewer 能登录并看到自己的待办。
6. reviewer 能完成 Manual QC 并提交结果。
7. 提交后结果、revision、audit 都能保存。
8. 主管能看到批次抽检覆盖率、样本完成率和 pass_rate。
9. 不同电脑可以访问同一套系统和同一套数据。

#### 18.6 V1.0 开发优先级建议
- P0：
  - 数据入库扫描
  - 数据库表结构
  - 登录与角色
  - 任务派发
  - Manual QC 提交闭环
  - 结果保存与审计
- P1：
  - Dashboard 统计
  - Database View 筛选查询
  - 转换任务入口
- P2：
  - 更好的统计页
  - 更好的 depth 辅助视图
  - 更好的任务池体验
- 这个优先级是为了保证你最快交付能用版本，而不是追求一次做满。

#### 18.7 V1.0 业务结论
- 对你当前阶段，V1.0 的本质不是“智能 QC 平台”，而是“公司可实际使用的人工 QC 协作平台”。
- 因此 V1.0 的主线必须是：
  - 入库
  - 建档
  - 派发
  - 人工质检
  - 留痕
  - 统计
- 只要这条线闭环，公司就能开始真实使用；AutoQC 和高级能力放到下一阶段是合理且务实的。

## Final Manual QC Product Spec

### 1. 产品定位
- Manual QC 是整套 QC 软件中的人工最终裁决链路。
- 它不是单一页面功能，而是一条完整业务链：任务入口、episode 占用、人工检查、结果提交、状态回写、历史追溯、batch 统计刷新全部闭环。
- 最终目标是让 reviewer 以统一标准、可追溯方式，对每条 processed episode 给出最终质量结论。

### 2. 适用范围
- 适用于 `processed` episode 的人工质检与自动质检后的人工复查。
- 不覆盖 raw 侧 L1 硬门禁，也不替代 raw→processed 转换逻辑。
- 若 episode 尚未完成 processed 产出，则人工 QC 链路不启动，必须先走 converter。

### 3. 角色定义
- `collector`：采集人员，只看结果，不负责最终裁决。
- `reviewer`：质检员，执行手动 QC、自动复查、重新质检。
- `admin`：管理员，可查看全部 revision、解锁、强制改状态、处理异常 case。

### 4. 标准输入与输出
#### 输入
- episode 基础信息：`episode_id`、`task_type`、`batch_id`、`frame_count`、`duration_sec`、`fps`
- processed 数据：三路视频、时间轴、telemetry、summary metrics、segment violations
- 可选输入：自动 QC 原结果、已有 QC 历史、锁状态

#### 输出
- 当前生效 QC 结论：`pass/fail`
- 原因码：`primary_reason_code` + `secondary_reason_codes`
- 审计记录：`qc_review_revision`
- 状态回写：`episode.qc_status`
- 统计回写：`batch_qc_summary`

### 5. 标准入口
- 入口 A：Dashboard 选择 `new` 批次 → 点击 `手动质检`
- 入口 B：Dashboard 选择 `auto_done` 批次 → 点击 `复查`
- 入口 C：Database View 选择单条 episode → 进入独立 Manual QC 页面
- 所有入口在真正进入页面前都必须先做 processed 存在性检查和软锁申请。

### 6. 页面职责边界
- 页面负责：展示视频、异常导航、人工核查、表单收集、提交结果。
- 页面不负责：实时计算复杂指标、修改原始数据、直接改 batch 汇总。
- 指标全部由后端预计算，页面只负责消费与展示。

### 7. 页面标准布局
- 左侧 60%：三相机同步视频区
- 右上 25%：episode 摘要、自动分析摘要、关键问题列表
- 右下 15%：结论面板（pass/fail、原因码、备注、提交）
- 底部：时间轴 + 遥测曲线联动区
- 设计原则：视频是主证据，指标是辅助证据，时间轴是导航骨架，结论面板是最终出口。

### 8. 页面标准检查顺序
1. 查看首屏摘要，理解本条 episode 的核心风险点。
2. 优先跳转红色异常段，核查系统标注是否真实。
3. 检查视觉质量：清晰度、曝光、目标物可见性、手部/指尖可见性。
4. 检查轨迹质量：抖动、停滞、饱和、异常回撤、跟踪误差。
5. 检查任务完成度：抓取、转运、放置、最终状态。
6. 给出最终裁决并提交。
- 该顺序是统一作业标准，目的是降低 reviewer 之间的判定漂移。

### 9. 页面交互总规则
- 先选 `qc_result`，再展开对应字段。
- `pass`：可进入训练池，默认不填主原因码，只允许挂轻微问题的次原因码。
- `fail`：必须选择一个主原因码，可附加最多 3 个次原因码。
- `review_auto` 模式下必须额外给出 `review_decision`。
- `override_auto_result` 时必须填写备注；`reviewed_segments` 是否强制填写由配置策略控制。

### 10. 结果定义标准
#### `pass`
- 表示该条 episode 可进入主训练池。
- 允许存在轻微瑕疵，但这些问题不能破坏训练可用性。
- 轻微问题仅记录在 `secondary_reason_codes` 中。

#### `fail`
- 表示该条 episode 不进入主训练池。
- 必须给出唯一主原因，表达最主要的失效来源。
- 其他伴随问题仅做辅助记录。

### 11. 原因码主规则
- 统计主口径只看 `primary_reason_code`。
- `secondary_reason_codes` 只用于共现分析、轻微问题画像和人工复盘。
- 主原因优先级固定为：`系统类 > 任务类 > 轨迹类 > 视觉类`
- 该优先级不是为了描述全部问题，而是为了让统计稳定。

### 12. 自动复查规则
- 自动 QC 后的人工复查与首次手动 QC 共用同一页面。
- 差异在于复查页面必须展示自动原结果，并要求人工给出：
  - `confirm_auto_pass`
  - `confirm_auto_fail`
  - `override_auto_result`
- 若人工推翻自动结果，则必须保留 `auto_result_snapshot`，用于后续分析自动系统误判。

### 13. 人工标记规则
- reviewer 可在时间轴上添加人工标记。
- 人工标记用于辅助核查和复盘，不直接等价于最终原因码。
- 页面可建议将人工标记映射成标准原因码，但不能自动替用户作最终裁决。

### 14. 提交数据标准
- 所有人工 QC 提交统一走一套 JSON 结构。
- 必备字段包括：
  - `episode_id`
  - `review_mode`
  - `qc_result`
  - `primary_reason_code`（fail 必填）
  - `secondary_reason_codes`
  - `free_text_note`
  - `review_decision`（review_auto 使用）
  - `reviewer_id`
  - `submitted_at`
- 可选字段包括：
  - `qc_confidence`
  - `reviewed_segments`
  - `auto_result_snapshot`
  - `client_version`

### 15. 前端提交校验标准
- 未选择 `qc_result` 不可提交。
- `fail` 未选择 `primary_reason_code` 不可提交。
- `secondary_reason_codes` 不得与 `primary_reason_code` 重复。
- `pass` 状态下不得选择 fail-only code。
- `override_auto_result` 未填写备注不可提交。
- `reviewed_segments` 区间非法不可提交。
- 所有错误提示必须指向具体字段，不能只报“提交失败”。

### 16. 状态机标准
#### episode 状态集合
- `new`
- `in_review`
- `auto_done`
- `done`

#### 标准流转
- `new -> in_review -> done`
- `new -> auto_done -> in_review -> done`
- `done -> in_review -> done`（重新质检）

#### 状态回退
- 若进入页面后未提交且锁超时/释放，则回退到进入前状态。
- 不允许页面打开即直接把状态写成 `done`。

### 17. 锁机制标准
- 进入 Manual QC 页面前必须申请 `review_lock`。
- 软锁成功后，episode 才可进入 `in_review`。
- 软锁失败时，当前用户只能只读查看或稍后再试。
- 锁释放时机：提交成功、主动退出、超时过期、管理员强制解锁。

### 18. 持久化标准
#### `episode`
- 保存当前 QC 状态与当前生效结果引用。

#### `qc_result`
- 保存当前对外生效的最终 QC 结论。

#### `qc_review_revision`
- 保存每次人工提交的完整历史快照。

#### `batch_qc_summary`
- 保存批次级统计，如 pass_rate、fail_count、top primary reason codes。

#### `review_lock`
- 保存当前软锁状态。

### 19. 提交后端标准动作
1. 写入一条 `qc_review_revision`
2. 失活上一条当前 `qc_result`
3. 写入或更新新的 active `qc_result`
4. 更新 `episode.current_qc_result_id`
5. 将 `episode.qc_status` 改为 `done`
6. 释放 `review_lock`
7. 刷新或触发重算 `batch_qc_summary`

### 20. 异常处理标准
- 提交接口失败：不丢表单内容，允许重试。
- 汇总刷新失败：不回滚主 QC 结果，改为异步补偿。
- 锁冲突：进入只读或提示被占用。
- processed 缺失：禁止进入人工 QC，提示先转换。
- 原因码版本不匹配：后端拒绝提交并返回明确错误。

### 21. 审计与追溯标准
- 每次人工提交都必须生成 revision。
- 任何重新质检都不能覆盖历史，只能新增版本。
- 对外展示默认只看 active `qc_result`；审计页面可查看全部 revision。
- 自动复查模式必须保留自动原结果快照，保证“机器怎么判、人工怎么改”全链路可追溯。

### 22. 批次与报表联动标准
- 单条 episode 提交成功后，batch 统计必须更新或进入待重算队列。
- Dashboard / Batch Detail / Report 统一读取同一口径：
  - `episode_total`
  - `sampled_episode_count`
  - `sample_coverage_rate`
  - `qc_done_count`
  - `sample_review_completion_rate`
  - `pass_count`
  - `fail_count`
  - `pass_rate`
  - `top_primary_reason_codes`
- 失败原因排行只统计 `primary_reason_code`。

### 23. 公司产品级判定标准
- 到此为止，人工 QC 链路已经具备产品级业务规范所需的核心要素：
  - 明确入口
  - 明确角色
  - 明确页面职责
  - 明确检查顺序
  - 明确表单规则
  - 明确原因码规则
  - 明确状态机
  - 明确锁机制
  - 明确持久化模型
  - 明确审计链路
  - 明确 batch 联动
  - 明确异常处理
- 因此后续工程实现时，不需要再发明新业务流程，只需要按本规范展开 API、前端页面和数据库表设计。

### 24. 本链路结论
- 人工 check 链路到这里视为已完成业务逻辑闭环。
- 后续如继续深入，应属于工程实现细化，而不再是业务逻辑缺口。

## Open Questions

- Current target node: 架构细化
- Current target edge: None

## Stable Assumptions

- QC 对象为 processed 数据
- Converter 为适配功能，非 QC 核心路径

## Verification Status

- 人工 QC 主链路业务逻辑已完成产品级闭环梳理
- 其余模块待继续讨论
