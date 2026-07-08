# Robot QC V1 — QC Agent 设计方案

版本：v1.0  
定位：Persistent Multimodal QC Copilot Agent  
主模型建议：Qwen3-VL-32B-Thinking  
适用页面：Robot QC V1 manual QC 页面  
核心目标：帮助质检员理解自动检测结果背后的原因，而不是复述结果或替代人工结论。

---

## 1. 背景与目标

Robot QC V1 当前已经具备 L3 v2 自动质检能力，能够基于 telemetry、视频、时间戳、动作轨迹等数据计算 MQ、LQ、DI、DX 等指标，并在 manual QC 页面中展示评分、指标、曲线、异常段和人工 pass/fail 提交流程。

当前 AI 助手的目标应从“结果解释卡片”升级为“真正的 QC Copilot Agent”。

它不应该只是回答：

> 当前分数是 9.2，主要短板是可学习性。

而应该能回答：

> 为什么 LQ-02 停滞检测扣分？  
> 这个停滞是任务自然等待，还是动作质量问题？  
> 为什么 DI-02 传感器同步这么低？  
> 为什么总分被截断？  
> 当前 episode 和上一条 episode 的异常是否类似？  
> 我应该优先看哪几秒的视频和曲线？

因此，QC Agent 的核心价值是：

```text
基于 L3 指标、NPZ 数据摘要、曲线图、视频关键帧、历史对话和相邻 episode 结果，
帮助质检员理解“为什么自动检测结果会这样”，并给出可追溯的复核建议。
```

---

## 2. 核心原则

QC Agent 必须遵守以下原则：

```text
L3 引擎负责计算和判断
QC Agent 负责解释和辅助理解
人工质检员负责最终 pass/fail 结论
```

严格边界：

1. 不重新计算 L3 分数。
2. 不修改 L3 指标结果。
3. 不直接给出 pass/fail 最终结论。
4. 不编造不存在的指标、时间段、硬件故障或传感器异常。
5. 不直接把大体积 telemetry.npz 原始数组塞给模型。
6. 不默认上传数据到外部 API。
7. 所有关键结论必须能追溯到指标、时间段、工具结果、曲线图或视频帧。
8. 如果证据不足，必须明确说明“不确定，需要人工结合视频和曲线判断”。

---

## 3. Agent 角色定义

### 3.1 不是普通聊天机器人

QC Agent 不是客服，不是闲聊机器人，不是简单知识库问答。

它是嵌入 Robot QC manual QC 页面中的质检辅助智能体，主要职责是：

```text
解释当前 episode 的自动检测结果
分析某个指标异常背后的数据原因
结合曲线、关键帧和工具结果辅助判断
对比当前与历史 episode
生成客观人工复核备注
帮助质检员更快定位应该查看的位置
```

### 3.2 推荐角色名称

内部工程名：

```text
QC Agent
```

前端展示名：

```text
AI 质检助手
```

产品定位文案：

```text
已接入当前 episode 上下文
AI 解读仅解释自动检测结果，不代替人工结论
```

---

## 4. 总体架构

推荐架构：

```text
Manual QC Frontend
  |
  | 用户问题 + 当前页面状态
  v
AI Assistant API
  |
  +--> Conversation Store      持久化聊天记录
  +--> Memory Service          episode / user / project 级记忆摘要
  +--> Intent Router           判断用户问题意图
  +--> Evidence Builder        构建证据包
  |       |
  |       +--> Metric Tools    指标与时间段工具
  |       +--> NPZ Tools       telemetry 摘要与曲线渲染
  |       +--> Video Tools     抽帧、短片段生成
  |       +--> Image Tools     当前页面截图、图表截图
  |       +--> Compare Tools   episode 对比
  |
  +--> Context Budgeter        控制模型输入窗口
  +--> Prompt Builder          构建 Agent Prompt
  +--> Qwen3-VL-32B-Thinking   多模态推理
  +--> Validator               越权、幻觉、引用检查
  +--> Response Formatter      文本 + 引用 + suggestedActions
  |
  v
Frontend Panel
```

一句话总结：

```text
模型负责推理和表达，工具负责取数和计算，Evidence Pack 负责把证据组织成模型可用输入。
```

---

## 5. 模型选择

### 5.1 主模型

推荐主模型：

```text
Qwen3-VL-32B-Thinking
```

适用原因：

1. 中文能力强。
2. 支持图像、文本、视频等多模态输入。
3. Thinking 版本更适合复杂原因分析。
4. 32B 规模比 7B 更稳定，适合牺牲推理时间换质量。
5. 适合处理“指标 + 曲线图 + 视频关键帧 + 历史上下文”的综合解释任务。

### 5.2 备选模型

生产稳妥备选：

```text
Qwen2.5-VL-32B-Instruct
```

轻量 fallback：

```text
GLM-4.1V-9B-Thinking
Qwen3-VL-8B-Thinking
Gemma 3 27B
```

### 5.3 模型使用原则

不要让模型直接裸看完整视频或原始 NPZ。

应提供：

```text
结构化 L3 指标
+ 当前用户问题
+ 页面状态
+ 历史对话摘要
+ 工具计算结果
+ 曲线图
+ 异常段关键帧
+ 可选短视频 clip
```

---

## 6. Context 与记忆设计

用户明确要求：

> 聊天窗口关闭后，模型不能失忆。  
> 模型要记得同一条轨迹之前问过的问题。  
> 也要能记得上一条或之前几条检测结果，支持交叉对比。

因此不能只依赖模型的上下文窗口，应设计“分层记忆”。

### 6.1 四层上下文

#### 第一层：当前请求上下文

每次用户发问时包含：

```json
{
  "currentQuestion": "为什么 LQ-02 低？",
  "episodeId": "episode_001",
  "pageState": {
    "selectedMetricId": "LQ-02",
    "currentVideoTimeSec": 12.4,
    "selectedTimelineSegmentId": "seg_003",
    "visibleChart": "left_arm_qpos"
  }
}
```

作用：解决“这里为什么异常”“这个指标什么意思”等指代问题。

---

#### 第二层：当前会话短期上下文

当前 conversation 最近 N 条消息：

```json
{
  "recentMessages": [
    {
      "role": "user",
      "content": "这条有没有触发截断？"
    },
    {
      "role": "assistant",
      "content": "没有触发 DI 截断，主要短板是 LQ-02 停滞检测。"
    }
  ]
}
```

作用：维持当前聊天连续性。

---

#### 第三层：episode 级长期记忆

针对同一条 episode 的历史摘要：

```json
{
  "episodeMemory": {
    "importantFindings": [
      "质检员重点关注过 LQ-02 停滞片段",
      "AI 曾建议查看 12.3s-18.7s"
    ],
    "openQuestions": [
      "该停滞是否属于任务自然等待尚未确认"
    ],
    "relatedMetrics": ["LQ-02", "LQ-01"]
  }
}
```

作用：同一 episode 关闭面板后再打开，仍能恢复之前的分析重点。

---

#### 第四层：跨 episode 记忆

最近几条或相关 episode 的摘要：

```json
{
  "relatedEpisodeMemory": [
    {
      "episodeId": "episode_000",
      "score": 8.7,
      "similarIssue": "LQ-02 停滞偏高",
      "summary": "上一条轨迹也出现 10s 左右无动作片段"
    }
  ]
}
```

作用：支持用户问：

```text
这条和上一条有什么区别？
这几条是不是同类问题？
为什么上一条能高分，这条低？
```

---

### 6.2 不要无限保留完整上下文

推荐策略：

```text
最近 8-12 条完整消息
+ 当前 episode 记忆摘要
+ 最近 3-5 条 episode 摘要
+ 按需检索相关历史
```

避免将全部聊天历史塞进模型，导致上下文污染、成本过高和响应变慢。

---

## 7. 数据库存储设计

### 7.1 ai_conversations

记录聊天会话。

```sql
CREATE TABLE ai_conversations (
    id UUID PRIMARY KEY,
    project_id TEXT,
    episode_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMP
);
```

说明：

- 一个 episode 可以有一个默认 conversation。
- 也可以允许多个 conversation，例如“DI-02 分析”“LQ 停滞复核”。

---

### 7.2 ai_messages

记录每条消息。

```sql
CREATE TABLE ai_messages (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES ai_conversations(id),
    episode_id TEXT NOT NULL,
    user_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    content_json JSONB,
    provider TEXT,
    model TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

role 可选：

```text
system
user
assistant
tool
```

content_json 可存：

```json
{
  "references": [],
  "suggestedActions": [],
  "warnings": [],
  "toolRuns": []
}
```

---

### 7.3 ai_tool_runs

记录工具调用。

```sql
CREATE TABLE ai_tool_runs (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES ai_conversations(id),
    message_id UUID,
    episode_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_input JSONB,
    tool_output JSONB,
    status TEXT NOT NULL,
    error_message TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

作用：

1. 追溯 AI 为什么这么回答。
2. 调试工具和模型问题。
3. 支持后续审计和评测。

---

### 7.4 ai_memory_summaries

记录长期记忆摘要。

```sql
CREATE TABLE ai_memory_summaries (
    id UUID PRIMARY KEY,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    user_id TEXT,
    project_id TEXT,
    summary TEXT NOT NULL,
    important_findings JSONB,
    open_questions JSONB,
    related_metric_ids JSONB,
    related_episode_ids JSONB,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

scope_type：

```text
episode
user
project
```

建议优先实现 episode 级记忆，后续再做 user / project 级。

---

### 7.5 ai_generated_assets

记录生成的曲线图、关键帧和短视频片段。

```sql
CREATE TABLE ai_generated_assets (
    id UUID PRIMARY KEY,
    episode_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    path TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP
);
```

asset_type：

```text
curve_image
video_frame
video_clip
panel_snapshot
```

---

## 8. 工具调用设计

QC Agent 应具备简单但可靠的工具调用能力。

推荐原则：

```text
工具负责确定性计算
模型负责解释工具结果
```

不要让模型直接处理大数组，不要让模型自己猜检测逻辑。

---

## 9. 工具分类

### 9.1 Metric Tools

#### get_metric_detail

获取某个指标详情。

输入：

```json
{
  "episodeId": "episode_001",
  "metricId": "LQ-02"
}
```

输出：

```json
{
  "metricId": "LQ-02",
  "name": "停滞检测",
  "score": 6.5,
  "level": "warn",
  "description": "12.3s-18.7s 存在低动作幅度片段",
  "timelineSegments": [
    {
      "startSec": 12.3,
      "endSec": 18.7,
      "label": "停滞",
      "level": "warn",
      "sourceMetricId": "LQ-02"
    }
  ]
}
```

---

#### get_episode_quality_summary

获取当前 episode 质量摘要。

输出：

```json
{
  "episodeId": "episode_001",
  "score": 9.2,
  "level": "good",
  "summary": "训练数据质量较好，主要短板为可学习性",
  "capTriggered": false,
  "capReason": null,
  "topIssues": [
    {
      "metricId": "LQ-02",
      "name": "停滞检测",
      "score": 6.5
    }
  ]
}
```

---

### 9.2 NPZ Tools

#### inspect_npz_metadata

读取 telemetry.npz 的结构和基础健康状态。

输入：

```json
{
  "episodeId": "episode_001"
}
```

输出：

```json
{
  "arrays": [
    {
      "name": "qpos",
      "shape": [1280, 26],
      "dtype": "float32",
      "nanCount": 0,
      "infCount": 0,
      "stdZeroDims": []
    },
    {
      "name": "actions",
      "shape": [1280, 26],
      "dtype": "float32",
      "nanCount": 0,
      "infCount": 0
    }
  ],
  "durationSec": 42.6,
  "fpsEstimated": 30.0
}
```

---

#### analyze_motion_segment

分析某个时间段的动作幅度、静止比例和可能原因。

输入：

```json
{
  "episodeId": "episode_001",
  "startSec": 12.3,
  "endSec": 18.7,
  "signals": ["qpos", "actions", "qvel"]
}
```

输出：

```json
{
  "startSec": 12.3,
  "endSec": 18.7,
  "motionEnergy": 0.13,
  "stationaryRatio": 0.72,
  "maxJointDelta": 0.018,
  "meanActionDelta": 0.011,
  "interpretationHint": "该时间段动作幅度较低，符合 LQ-02 停滞检测扣分依据"
}
```

---

#### analyze_action_qpos_lag

分析 action 与 qpos 的滞后和跟踪误差。

输入：

```json
{
  "episodeId": "episode_001",
  "startSec": 0,
  "endSec": 42.6,
  "jointRange": "all"
}
```

输出：

```json
{
  "bestLagMs": 83,
  "rmsErrorBeforeAlign": 0.21,
  "rmsErrorAfterAlign": 0.09,
  "affectedDims": [3, 4, 5],
  "interpretationHint": "action 与 qpos 存在约 83ms 滞后，对跟踪误差有贡献"
}
```

---

#### render_npz_curve

将 NPZ 数据渲染为曲线图，供前端展示和多模态模型分析。

输入：

```json
{
  "episodeId": "episode_001",
  "startSec": 12.3,
  "endSec": 18.7,
  "signals": ["qpos", "actions"],
  "dims": [0, 1, 2, 3],
  "title": "LQ-02 停滞段 qpos/actions 曲线"
}
```

输出：

```json
{
  "assetId": "asset_curve_001",
  "imagePath": "/generated/episode_001_lq02_12_18.png",
  "description": "12.3s-18.7s qpos/actions 对比曲线"
}
```

---

### 9.3 Video Tools

#### extract_video_frames

从异常段抽取关键帧。

输入：

```json
{
  "episodeId": "episode_001",
  "camera": "rgb_front",
  "startSec": 12.3,
  "endSec": 18.7,
  "strategy": "start_middle_end"
}
```

输出：

```json
{
  "frames": [
    {
      "assetId": "frame_001",
      "timeSec": 12.3,
      "path": "/generated/episode_001_frame_12_3.jpg"
    },
    {
      "assetId": "frame_002",
      "timeSec": 15.5,
      "path": "/generated/episode_001_frame_15_5.jpg"
    },
    {
      "assetId": "frame_003",
      "timeSec": 18.7,
      "path": "/generated/episode_001_frame_18_7.jpg"
    }
  ]
}
```

---

#### extract_video_clip

按需生成短视频片段。

输入：

```json
{
  "episodeId": "episode_001",
  "camera": "rgb_front",
  "startSec": 12.3,
  "endSec": 18.7,
  "maxDurationSec": 8
}
```

输出：

```json
{
  "assetId": "clip_001",
  "path": "/generated/episode_001_12_18.mp4",
  "durationSec": 6.4
}
```

使用原则：

```text
默认抽关键帧
必要时生成短 clip
不要默认把完整 episode 视频输入模型
```

---

### 9.4 Image / Chart Tools

#### render_metric_panel_snapshot

生成当前指标面板截图。

输出：

```json
{
  "assetId": "panel_snapshot_001",
  "path": "/generated/episode_001_metric_panel.png",
  "description": "当前评分面板和指标列表截图"
}
```

---

#### render_timeline_snapshot

生成异常时间轴截图。

输出：

```json
{
  "assetId": "timeline_snapshot_001",
  "path": "/generated/episode_001_timeline.png",
  "description": "当前 episode 异常时间段分布"
}
```

---

### 9.5 Compare Tools

#### get_recent_episode_summaries

获取最近几条 episode 摘要。

输入：

```json
{
  "projectId": "project_001",
  "limit": 5
}
```

输出：

```json
{
  "episodes": [
    {
      "episodeId": "episode_000",
      "score": 8.7,
      "topIssues": ["LQ-02"],
      "summary": "存在轻微停滞片段"
    }
  ]
}
```

---

#### compare_episodes

对比两条 episode 的指标、异常段和 AI 记忆摘要。

输入：

```json
{
  "episodeIds": ["episode_001", "episode_000"],
  "focusMetricIds": ["LQ-02", "DI-02"]
}
```

输出：

```json
{
  "comparison": [
    {
      "metricId": "LQ-02",
      "episodeA": {
        "score": 6.5,
        "segments": ["12.3s-18.7s"]
      },
      "episodeB": {
        "score": 8.4,
        "segments": ["10.0s-11.0s"]
      },
      "differenceHint": "当前 episode 停滞时间更长，扣分更明显"
    }
  ]
}
```

---

## 10. Evidence Pack 设计

Evidence Pack 是 QC Agent 的核心。

模型不直接面对原始数据，而是面对后端整理后的证据包。

### 10.1 Evidence Pack 示例

```json
{
  "question": "为什么 LQ-02 停滞检测扣分？",
  "currentEpisode": {
    "episodeId": "episode_001",
    "score": 9.2,
    "summary": "训练数据质量较好，主要短板为可学习性"
  },
  "focusedMetric": {
    "metricId": "LQ-02",
    "name": "停滞检测",
    "score": 6.5,
    "description": "12.3s-18.7s 存在低动作幅度片段"
  },
  "computedEvidence": {
    "stationaryRatio": 0.72,
    "motionEnergy": 0.13,
    "maxJointDelta": 0.018,
    "interpretationHint": "该时间段动作幅度较低，符合 LQ-02 扣分依据"
  },
  "visualEvidence": [
    {
      "type": "curve",
      "assetId": "asset_curve_001",
      "description": "12.3s-18.7s qpos/actions 对比曲线"
    },
    {
      "type": "video_frame",
      "assetId": "frame_002",
      "timeSec": 15.5,
      "description": "异常段中间帧"
    }
  ],
  "historyContext": {
    "recentMessagesSummary": "用户之前询问过是否触发 DI 截断，AI 已说明未触发。",
    "episodeMemory": "本条 episode 主要关注 LQ-02 停滞片段。",
    "relatedEpisodes": []
  },
  "constraints": [
    "只能解释已有检测结果和工具证据",
    "不能重新评分",
    "不能直接给 pass/fail 结论",
    "不能编造硬件故障原因"
  ]
}
```

### 10.2 Evidence Pack 的价值

1. 让模型有足够证据，而不是猜。
2. 控制上下文长度。
3. 降低幻觉风险。
4. 支持引用和审计。
5. 让回答更贴近质检员实际问题。

---

## 11. Intent Router 设计

用户问题先进入 Intent Router。

### 11.1 常见意图

```text
explain_metric          解释某个指标
explain_score           解释总分
explain_cap             解释截断 / 封顶
locate_issue            推荐查看时间段
analyze_segment         分析当前时间段
compare_episode         和上一条 / 某条 episode 对比
generate_qc_note        生成人工复核备注
explain_concept         解释指标含义或规则
free_chat               普通问答
```

### 11.2 示例

用户问：

```text
为什么 DI-02 这么低？是不是深度相机坏了？
```

Intent Router 输出：

```json
{
  "intent": "explain_metric",
  "focusedMetricId": "DI-02",
  "needTools": [
    "get_metric_detail",
    "get_timeline_segments",
    "analyze_sensor_sync",
    "render_sync_curve",
    "extract_video_frames"
  ],
  "riskFlags": [
    "hardware_cause_speculation"
  ]
}
```

模型回答时必须避免直接判断“深度相机坏了”，只能说：

```text
从当前证据看，问题表现为深度相机与关节数据时间戳不同步。
是否为硬件故障还不能仅凭当前证据确认，建议人工检查 8.0s-15.0s 的同步曲线和视频帧。
```

---

## 12. 上下文预算 Context Budgeter

Qwen3-VL-32B-Thinking 虽然上下文能力强，但仍要控制输入。

推荐每次请求模型的上下文优先级：

```text
P0 当前用户问题
P0 当前 episode 核心指标
P0 focused metric 详情
P0 工具计算证据
P0 相关 timelineSegments
P1 当前页面状态
P1 最近 8 条消息
P1 episode 记忆摘要
P2 最近 3 条 episode 摘要
P2 视觉证据缩略图 / 曲线图
P3 更早历史对话
```

如果超预算：

1. 保留 focused metric。
2. 保留工具证据。
3. 保留关键图像。
4. 压缩聊天历史为摘要。
5. 丢弃无关历史。

---

## 13. Prompt 设计

### 13.1 System Prompt

```text
你是 Robot QC V1 的 AI 质检助手，服务于机器人遥操作数据人工质检页面。

你的目标不是复述检测结果，而是帮助质检员理解自动检测结果背后的原因。

你可以基于以下证据进行解释：
1. L3 自动质检指标结果
2. timelineSegments 异常时间段
3. NPZ 工具计算结果
4. 曲线图
5. 视频关键帧或短视频片段
6. 当前页面状态
7. 当前 episode 的历史对话摘要
8. 最近或相关 episode 的对比摘要

严格限制：
1. 你不能重新计算评分。
2. 你不能修改 L3 指标结果。
3. 你不能直接决定 pass/fail。
4. 你不能编造上下文中不存在的指标、分数、异常时间段、传感器故障或硬件原因。
5. 如果证据不足，请明确说明“不确定，需要人工结合视频和曲线判断”。
6. 如果用户问“这条能不能过”，请回答为“从自动检测结果看，需要重点关注……最终结论仍由质检员判断”。
7. 所有关键结论必须引用依据，例如 metricId、时间段、工具结果、曲线图或视频帧。
8. 不要输出与当前 episode 无关的泛泛建议。

回答风格：
1. 中文。
2. 简洁、专业、客观。
3. 面向质检员。
4. 优先说明“现象是什么、依据是什么、可能原因是什么、建议看哪里”。
```

---

### 13.2 User Prompt 模板

```text
用户问题：
{user_message}

当前页面状态：
{page_state}

当前 episode 证据包：
{evidence_pack}

请基于以上证据回答。请不要直接给 pass/fail 结论。
```

---

## 14. 回复格式设计

推荐模型输出结构化 JSON，再由后端格式化。

```json
{
  "answer": "LQ-02 扣分主要与 12.3s-18.7s 的低动作幅度片段有关……",
  "keyPoints": [
    {
      "title": "主要现象",
      "text": "12.3s-18.7s 静止比例较高，stationaryRatio=0.72"
    },
    {
      "title": "依据",
      "text": "对应 LQ-02 停滞检测，分数 6.5"
    },
    {
      "title": "建议",
      "text": "建议人工查看该时间段视频和 qpos/actions 曲线，确认是否为任务自然等待"
    }
  ],
  "references": [
    {
      "type": "metric",
      "metricId": "LQ-02",
      "name": "停滞检测"
    },
    {
      "type": "timeline_segment",
      "startSec": 12.3,
      "endSec": 18.7
    },
    {
      "type": "tool_result",
      "toolName": "analyze_motion_segment"
    },
    {
      "type": "visual_asset",
      "assetId": "asset_curve_001"
    }
  ],
  "suggestedActions": [
    {
      "type": "jump_to_time",
      "label": "查看 12.3s-18.7s",
      "startSec": 12.3,
      "endSec": 18.7
    },
    {
      "type": "highlight_metric",
      "metricId": "LQ-02"
    },
    {
      "type": "open_curve",
      "chart": "qpos_actions",
      "startSec": 12.3,
      "endSec": 18.7
    }
  ],
  "warnings": []
}
```

---

## 15. Validator 与 Guardrails

必须对模型输出做校验。

### 15.1 校验项

至少检查：

```text
回复不能为空
回复长度不超过配置上限
不能直接输出 pass/fail 结论
不能出现“建议直接通过”“建议判 fail”“必须 fail”等越权判断
不能引用 evidence pack 中不存在的 metricId
不能引用不存在的时间段
不能编造不存在的工具结果
不能编造明确硬件故障原因
如果用户问截断，回答必须包含“截断”或“封顶”
不能出现明显占位符，如 <xxx>、{xxx}
```

### 15.2 不合规处理

如果模型输出不合规：

```text
1. 记录 validator warning
2. 尝试让模型修正一次
3. 仍不合规则返回 template fallback
```

---

## 16. API 设计

### 16.1 创建或恢复会话

```http
POST /api/ai-assistant/conversations
```

请求：

```json
{
  "episodeId": "episode_001",
  "reuseLatest": true
}
```

响应：

```json
{
  "conversationId": "conv_001",
  "episodeId": "episode_001",
  "messages": [],
  "episodeMemory": {
    "summary": "本条 episode 暂无历史 AI 分析。"
  }
}
```

---

### 16.2 获取消息历史

```http
GET /api/ai-assistant/conversations/{conversationId}/messages
```

响应：

```json
{
  "conversationId": "conv_001",
  "messages": [
    {
      "id": "msg_001",
      "role": "user",
      "content": "为什么 LQ-02 低？",
      "createdAt": "2026-01-01T10:00:00Z"
    },
    {
      "id": "msg_002",
      "role": "assistant",
      "content": "LQ-02 低主要与 12.3s-18.7s 的停滞片段有关……",
      "references": [],
      "suggestedActions": []
    }
  ]
}
```

---

### 16.3 发送消息

```http
POST /api/ai-assistant/chat
```

请求：

```json
{
  "conversationId": "conv_001",
  "episodeId": "episode_001",
  "message": "为什么 LQ-02 低？",
  "pageState": {
    "selectedMetricId": "LQ-02",
    "currentVideoTimeSec": 12.4,
    "selectedTimelineSegmentId": "seg_003",
    "visibleChart": "left_arm_qpos"
  },
  "useHistory": true,
  "useTools": true,
  "useVisualEvidence": true,
  "stream": true
}
```

响应：

```json
{
  "messageId": "msg_002",
  "conversationId": "conv_001",
  "status": "completed",
  "answer": "LQ-02 扣分主要与 12.3s-18.7s 的低动作幅度片段有关……",
  "references": [],
  "suggestedActions": [],
  "toolRuns": [],
  "latencyMs": 8200,
  "model": "Qwen3-VL-32B-Thinking",
  "warnings": []
}
```

---

### 16.4 获取工具运行详情

```http
GET /api/ai-assistant/messages/{messageId}/tool-runs
```

作用：调试、审计、展示 AI 依据。

---

### 16.5 获取生成资产

```http
GET /api/ai-assistant/assets/{assetId}
```

用于返回曲线图、关键帧、短视频片段。

---

## 17. 异步与流式响应

Qwen3-VL-32B-Thinking 可能较慢，尤其加入图片和视频后。

建议支持：

```text
SSE / WebSocket 流式输出
后台任务队列
阶段性状态反馈
```

前端状态示例：

```text
正在读取 L3 指标...
正在分析 LQ-02 时间段...
正在渲染 qpos/actions 曲线...
正在抽取视频关键帧...
正在生成解释...
```

请求流程：

```text
POST /chat
  -> 创建 user message
  -> 创建 assistant pending message
  -> 后台执行工具和模型
  -> 前端通过 SSE 接收状态和最终回答
```

---

## 18. 缓存设计

建议缓存：

```text
NPZ metadata
metric detail
timelineSegments
常用曲线图
异常段关键帧
短视频 clip
episode 质量摘要
AI 解释结果
memory summary
```

缓存 key：

```text
episodeId + toolName + inputHash
```

好处：

1. 减少重复抽帧和画图。
2. 提高二次提问速度。
3. 支持关闭聊天后快速恢复上下文。

---

## 19. 前端设计

### 19.1 面板入口

在评分表盘右侧放置 AI 助手视觉对象，例如：

```text
黑曜机械 AI Core
嵌入式智能模块
点击后展开 AI 质检助手面板
```

### 19.2 面板结构

```text
AI 质检助手
已接入当前 episode 上下文
AI 解读仅解释自动质检结果，不代替人工结论

[快捷问题按钮]
- 解释本条检测结果
- 为什么被降分
- 总结主要异常
- 推荐先看哪几秒
- 灵巧手有问题吗
- 解释 Q_motion 截断规则
- 帮我写人工复核备注

[聊天消息列表]
[引用卡片 / 时间段按钮 / 工具结果摘要]
[输入框]
```

### 19.3 页面状态注入

每次发送消息时，前端应带上：

```json
{
  "selectedMetricId": "LQ-02",
  "currentVideoTimeSec": 12.4,
  "selectedTimelineSegmentId": "seg_003",
  "visibleChart": "left_arm_qpos",
  "openedMetricPanel": "LQ"
}
```

这样 AI 才知道用户说的“这个”“这里”“刚才那段”指哪里。

---

## 20. 前端组件建议

```text
AiAssistantAnchor.vue
AiAssistantPanel.vue
AiAssistantMessageList.vue
AiQuickActionBar.vue
AiReferenceCards.vue
AiToolRunTimeline.vue
useAiAssistant.ts
useAiConversation.ts
```

### 20.1 AiReferenceCards

展示 AI 回答依据：

```text
LQ-02 停滞检测
12.3s - 18.7s
analyze_motion_segment
qpos/actions 曲线图
```

### 20.2 AiToolRunTimeline

展示模型分析过程：

```text
已读取指标
已渲染曲线
已抽取关键帧
已生成解释
```

---

## 21. Suggested Actions

AI 回复应支持操作按钮：

```json
[
  {
    "type": "jump_to_time",
    "label": "查看 12.3s-18.7s",
    "startSec": 12.3,
    "endSec": 18.7
  },
  {
    "type": "highlight_metric",
    "metricId": "LQ-02"
  },
  {
    "type": "open_curve",
    "chart": "qpos_actions",
    "startSec": 12.3,
    "endSec": 18.7
  },
  {
    "type": "compare_episode",
    "episodeId": "episode_000"
  }
]
```

这能让 AI 从“回答问题”升级为“辅助操作”。

---

## 22. 后端模块结构

推荐目录：

```text
backend/app/ai_assistant/
  __init__.py
  schemas.py
  router.py

  chat/
    chat_service.py
    conversation_store.py
    memory_service.py
    summary_service.py

  context/
    context_builder.py
    evidence_builder.py
    context_budgeter.py
    retrieval.py

  tools/
    __init__.py
    base.py
    registry.py
    metric_tools.py
    npz_tools.py
    video_tools.py
    image_tools.py
    chart_tools.py
    compare_tools.py

  providers/
    __init__.py
    base.py
    openai_compatible_provider.py
    qwen_vl_provider.py
    template_provider.py

  guardrails/
    prompt_builder.py
    validator.py
    citation_checker.py
    policy.py

  assets/
    asset_store.py
    cache.py
```

---

## 23. 配置项

```env
AI_ASSISTANT_ENABLED=true
AI_ASSISTANT_PROVIDER=openai_compatible

OPENAI_COMPATIBLE_BASE_URL=http://localhost:8000/v1
OPENAI_COMPATIBLE_API_KEY=local
OPENAI_COMPATIBLE_MODEL=Qwen3-VL-32B-Thinking

AI_ASSISTANT_TIMEOUT_SECONDS=60
AI_ASSISTANT_MAX_HISTORY_MESSAGES=12
AI_ASSISTANT_MAX_OUTPUT_CHARS=1600
AI_ASSISTANT_ENABLE_TOOLS=true
AI_ASSISTANT_ENABLE_VISUAL_EVIDENCE=true
AI_ASSISTANT_ENABLE_MEMORY=true

AI_ASSISTANT_ASSET_DIR=/data/ai_assistant_assets
AI_ASSISTANT_CACHE_TTL_SECONDS=86400
AI_ASSISTANT_MAX_VIDEO_CLIP_SECONDS=8
AI_ASSISTANT_MAX_FRAMES_PER_REQUEST=6
```

默认建议：

```text
AI_ASSISTANT_ENABLED=false
```

只有显式开启时才调用模型。

---

## 24. 安全与隐私

必须满足：

1. 默认本地模型。
2. 默认不启用第三方 API。
3. API key 仅在后端环境变量中保存。
4. 前端不暴露 API key。
5. 日志中不打印完整 API key。
6. 日志中不打印完整 NPZ 原始数组。
7. 生成的关键帧、曲线图、短视频应按项目权限访问。
8. 聊天记录按 user / project / episode 隔离。
9. 如果接入外部 OpenAI-compatible API，必须显式配置并在系统文档中说明数据边界。
10. AI 不能访问未授权 episode 数据。

---

## 25. 失败与 fallback

### 25.1 常见失败场景

```text
模型不可用
模型响应超时
工具执行失败
NPZ 缺失
视频缺失
图像生成失败
模型输出越权
模型引用不存在指标
上下文过长
```

### 25.2 Fallback 策略

```text
模型不可用：
  返回模板解释，不影响人工质检

工具失败：
  告知某项证据不可用，但继续基于已有指标回答

视觉证据不可用：
  退化为结构化指标解释

模型输出不合规：
  validator 拦截，返回安全模板

episode 上下文缺失：
  提示当前 episode 上下文不足，无法完整分析
```

前端文案：

```text
AI 深度分析暂不可用，请以指标、视频和人工判断为准。
```

---

## 26. 测试要求

### 26.1 后端测试

至少覆盖：

```text
创建 / 恢复 conversation
关闭聊天后再次打开能恢复历史
episode memory summary 正确生成
最近消息按 max history 截断
Intent Router 能识别 metric / score / cap / compare
Evidence Builder 能包含 score、metrics、timelineSegments
NPZ metadata 工具能正确解析 shape / dtype / NaN
render_npz_curve 能生成图片资产
extract_video_frames 能按时间段抽帧
compare_episodes 能输出指标差异
模型不可用时 fallback
工具失败时不影响整体响应
模型输出 pass/fail 被拦截
模型引用不存在 metricId 被拦截
```

### 26.2 前端测试

至少覆盖：

```text
点击 AI 入口打开面板
关闭后再次打开恢复聊天记录
快捷问题可发送
thinking 状态可展示
工具执行状态可展示
AI 回复引用卡片可展示
jump_to_time 可触发时间轴跳转
highlight_metric 可高亮指标
请求失败时页面不崩溃
```

---

## 27. 分阶段实施路线

### Phase 1：持久化聊天 + 基础上下文

目标：

```text
聊天记录持久化
conversation 恢复
当前 episode 指标上下文
Qwen3-VL 文本模式解释
template fallback
```

交付：

```text
ai_conversations
ai_messages
POST /conversations
GET /messages
POST /chat
context_builder
prompt_builder
validator
```

---

### Phase 2：工具调用与 Evidence Pack

目标：

```text
Metric Tools
NPZ metadata
motion segment analysis
action/qpos lag analysis
曲线图生成
tool_runs 记录
```

交付：

```text
npz_tools.py
metric_tools.py
chart_tools.py
evidence_builder.py
ai_tool_runs
ai_generated_assets
```

---

### Phase 3：多模态视觉证据

目标：

```text
视频关键帧
短视频 clip
曲线图输入 Qwen3-VL
视觉证据引用
```

交付：

```text
video_tools.py
image_tools.py
Qwen3-VL multimodal provider
visualEvidence in evidence pack
```

---

### Phase 4：跨 episode 对比与长期记忆

目标：

```text
episode memory summary
recent episode context
compare_episodes
相似问题检索
```

交付：

```text
ai_memory_summaries
memory_service.py
summary_service.py
compare_tools.py
retrieval.py
```

---

### Phase 5：产品化增强

目标：

```text
SSE / WebSocket 流式输出
工具执行时间线
引用卡片
suggestedActions 完整联动
评测集和质量看板
```

---

## 28. 评测方案

建议准备一个小型 QC Agent 评测集。

### 28.1 Case 类型

```text
正常高分 episode
LQ-02 停滞扣分
DI-02 同步异常
DI 截断导致总分封顶
MQ-03 高频抖动
DX-01 跟踪误差
灵巧手维度异常
视频看起来正常但指标异常
指标正常但用户怀疑异常
```

### 28.2 评测问题

```text
这个指标为什么低？
主要问题在哪个时间段？
这条和上一条有什么不同？
是否触发 Q_motion 截断？
这个异常可能是什么原因？
有没有数据完整性问题？
能不能帮我写人工复核备注？
```

### 28.3 评分维度

```text
是否准确引用指标
是否准确引用时间段
是否正确解释截断
是否避免 pass/fail 越权
是否编造不存在证据
是否说到质检员真正关心的问题
是否给出可执行查看建议
```

---

## 29. 典型交互示例

### 29.1 用户问 LQ-02

用户：

```text
为什么 LQ-02 停滞检测扣分？我看视频好像没什么问题。
```

Agent 理想回答：

```text
LQ-02 扣分主要来自 12.3s-18.7s 的低动作幅度片段。

依据：
1. LQ-02 停滞检测分数为 6.5，异常段标记为 12.3s-18.7s。
2. NPZ 工具分析显示该时间段 stationaryRatio=0.72，motionEnergy=0.13，说明关节变化幅度明显低于其他时间段。
3. qpos/actions 曲线中该段变化较平缓，与 LQ-02 的停滞判断一致。

目前不能仅凭这些证据判断这是“无效停滞”还是“任务自然等待”。建议人工重点查看 12.3s-18.7s 的视频和 qpos/actions 曲线，确认机器人是否处于合理等待状态。
```

Suggested Actions：

```text
查看 12.3s-18.7s
高亮 LQ-02
打开 qpos/actions 曲线
```

---

### 29.2 用户问 DI-02

用户：

```text
DI-02 为什么这么低？是不是深度相机坏了？
```

Agent 理想回答：

```text
DI-02 低分反映的是传感器同步异常，而不是直接证明深度相机损坏。

依据：
1. DI-02 传感器同步分数为 1.6。
2. 异常时间段集中在 8.0s-15.0s。
3. 同步分析工具显示深度帧时间戳与关节数据最大偏移约 67ms，超过 30ms 阈值。
4. 当前证据更支持“深度相机与关节数据存在时间对齐问题”。

是否为硬件故障还不能仅凭自动检测结果确认。建议人工查看 8.0s-15.0s 的同步曲线和视频关键帧，并结合采集日志确认是否存在设备延迟或时间戳写入问题。
```

---

### 29.3 用户问是否能过

用户：

```text
这条能不能过？
```

Agent 理想回答：

```text
我不能替代质检员给出 pass/fail 结论。

从自动检测结果看，本条需要重点关注：
1. LQ-02 停滞检测分数偏低，异常段集中在 12.3s-18.7s。
2. 该片段是否属于任务自然等待，需要人工结合视频和曲线判断。
3. 数据完整性指标未显示严重截断风险。

建议先查看 12.3s-18.7s，再结合任务语义做最终判断。
```

---

## 30. 最终验收标准

完成后应满足：

```text
1. 聊天窗口关闭后，重新打开能恢复当前 episode 的历史对话。
2. 同一 episode 的历史分析能被新问题引用。
3. 能记住最近几条 episode 的检测摘要，用于简单对比。
4. 能调用 NPZ 工具读取 metadata 和分析指定时间段。
5. 能生成曲线图、视频关键帧作为视觉证据。
6. 能把 evidence pack 输入 Qwen3-VL-32B-Thinking。
7. AI 回复能引用指标、时间段、工具结果和视觉资产。
8. AI 能输出 suggestedActions，如跳转时间段和高亮指标。
9. 聊天内容、工具调用、AI 回复都持久化到后端。
10. 模型不可用或工具失败时不影响 manual QC 主流程。
11. AI 不直接输出 pass/fail 最终结论。
12. AI 不编造不存在的指标、时间段和硬件原因。
13. 有基础测试和回归评测集。
```

---

## 31. 最重要的设计判断

这个 QC Agent 的成败不取决于“模型是否足够大”，而取决于是否把问题拆成正确的系统工程：

```text
Qwen3-VL-32B-Thinking
负责多模态推理和解释

L3 v2
负责评分和指标判断

Tools
负责取数、抽帧、画图、计算证据

Evidence Pack
负责组织上下文

Memory
负责保留 episode 和跨 episode 的历史

Validator
负责控制风险

Human QC
负责最终 pass/fail
```

最终要实现的不是：

```text
AI 复述检测结果
```

而是：

```text
AI 基于证据帮助质检员理解结果原因，并告诉质检员下一步该看哪里。
```
