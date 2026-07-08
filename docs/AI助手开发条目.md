# Robot QC V1：评分圈 AI 助手入口与交互式 QC Copilot 设计实现 Instruction

## 0. 你的角色

你是本项目的前后端工程实现 Agent，负责在现有 Robot QC V1 的 manual QC 页面中，实现一个高质量、轻量、可交互的 AI 质检助手入口。

该助手不是替代人工质检员，也不是替代 L3 v2 自动评分引擎，而是作为：

```text
当前 episode 的 AI 解释入口
当前检测结果的对话式问答助手
当前质检页面的智能辅助交互组件
```

请始终遵守：

```text
L3 引擎负责判断
AI 助手负责解释
人工质检员负责最终 pass/fail 结论
```

---

## 1. 功能目标

在 manual QC 页面右侧评分卡片区域中，将现有评分圈附近的空白区域设计为一个高动态、高颜值、轻量常驻的 AI 助手入口。

当前 UI 中评分圈显示类似：

```text
RDDQF 训练质量评分

       9.2
Training Quality

该 episode 的训练数据质量较好，当前主要短板为：可学习性。
```

目标是在评分圈缺口或评分圈附近嵌入一个 AI 助手锚点。

默认状态下只显示一个小型动态助手形象，不弹出聊天框，不干扰质检员查看视频、曲线和指标。

用户点击助手后，展开一个聊天式 AI Copilot 面板，支持：

```text
1. 访问当前正在检测的 episode 上下文
2. 支持自由聊天提问
3. 支持一键快捷请求
4. 支持解释当前检测结果
5. 支持定位主要异常时间段
6. 支持解释指标含义和截断逻辑
7. 后端可连接本地 Ollama / vLLM，也可支持第三方 OpenAI-compatible API
```

---

## 2. 当前阶段范围

当前阶段只实现第一版 QC Copilot：

```text
评分圈 AI 助手入口
  → 点击展开聊天面板
  → 快捷问题按钮
  → 当前 episode 上下文注入
  → 本地/第三方模型统一调用接口
  → AI 回复展示
  → 失败 fallback
```

当前阶段不做：

```text
不让 AI 改分
不让 AI 直接决定 pass/fail
不让 AI 替代 L3 v2 指标计算
不直接让 AI 读取原始 telemetry.npz 大数组
不直接让 AI 判断视频/曲线图中的新异常
不默认启用云端 API
不让聊天面板默认弹出
不影响现有 manual QC 页面主流程
```

---

## 3. 产品形态

### 3.1 总体交互

请实现如下交互状态：

```text
待机态：
  页面只显示一个小型 AI 助手形象，位于评分圈缺口或评分圈附近。

悬停态：
  助手轻微放大、发光增强，并显示 tooltip：
  “AI 解读”
  “点击查看本条 episode 解释”

点击态：
  弹出 AI 聊天面板。

思考态：
  助手显示扫描、呼吸或流光动画；
  聊天面板显示“正在分析当前 episode...”。

回复态：
  聊天面板展示 AI 回复；
  如果回复涉及异常时间段，提供“跳转到该时间段”的 UI 预留能力。

关闭态：
  聊天面板收起，助手回到待机态。
```

---

## 4. AI 助手视觉设计要求

### 4.1 推荐形象方向

优先实现“未来感智能核心 / AI 能量球”形象。

不要做普通客服头像，不要做夸张卡通人物，不要影响工业质检页面的专业感。

视觉关键词：

```text
未来感
轻量
高动态
科技感
玻璃感
蓝绿色发光
智能核心
数据扫描
不喧宾夺主
```

推荐造型：

```text
一个 28-40px 的小型智能核心
外层有细圆环
内部有发光核心点
周围有轻微扫描线或粒子感
待机时缓慢呼吸
hover 时轻微放大
thinking 时外环旋转或流光扫描
```

---

### 4.2 状态颜色建议

```text
idle：青蓝 / 青绿
hover：增强青蓝光晕
thinking：蓝紫流光
warning：橙黄提示
error：灰红弱提示
```

注意：状态色只用于 AI 助手本身，不要改变原有评分圈的业务颜色语义。

---

### 4.3 实现技术建议

第一版可以使用：

```text
SVG + CSS animation
```

后续可升级为：

```text
Rive 状态机动画
Lottie 动画
Three.js / Spline 3D 智能核心
```

当前阶段优先保证：

```text
性能稳定
实现简单
和现有 Vue 3 页面集成容易
动画自然
不影响页面加载速度
```

---

## 5. 前端组件设计

请在前端新增或拆分以下组件。文件名可根据项目结构调整，但请保持职责清晰。

### 5.1 AiAssistantAnchor.vue

职责：

```text
显示评分圈附近的小型 AI 助手入口
处理 hover / active / thinking / error 状态
点击后打开聊天面板
展示 tooltip
不直接处理复杂聊天逻辑
```

Props 建议：

```ts
episodeId: string
status: 'idle' | 'hover' | 'thinking' | 'error'
active: boolean
```

Emits 建议：

```ts
open
close
```

视觉行为：

```text
idle：呼吸动画
hover：放大 1.05-1.10 倍
thinking：外环旋转或扫描
error：弱提示，不要弹窗打扰用户
```

---

### 5.2 AiAssistantPanel.vue

职责：

```text
显示 AI 聊天面板
显示快捷问题按钮
显示聊天消息
显示输入框
处理用户发送消息
展示 loading / error / fallback
```

面板建议尺寸：

```text
宽度：360-420px
高度：420-560px
位置：评分卡片附近浮层，或右侧 drawer
```

顶部内容：

```text
标题：AI 质检助手
副标题：已接入当前 episode 上下文
标签：Local / Ollama / API / Template
提示：AI 解读仅解释自动质检结果，不代替人工结论
```

快捷按钮建议：

```text
解释本条检测结果
为什么被降分
总结主要异常
推荐先看哪几秒
灵巧手有问题吗
解释 Q_motion 截断规则
帮我写人工复核备注
```

底部输入框：

```text
placeholder: 向 AI 询问当前 episode 的检测结果...
```

---

### 5.3 AiAssistantMessageList.vue

职责：

```text
展示对话消息
区分 user / assistant / system
支持 loading 消息
支持引用指标和时间段
```

消息中如果出现异常时间段，预留操作按钮：

```text
跳转到 8.0s
高亮 DI-02
查看异常段
```

第一版可以只展示按钮，不必完全实现跳转联动；如果当前项目已有时间轴跳转函数，则接入。

---

### 5.4 AiQuickActionBar.vue

职责：

```text
展示快捷问题按钮
点击后自动发送对应 prompt
```

快捷问题不要写得太抽象，应尽量贴近质检员语言。

推荐内置 prompt：

```text
帮我解释一下这条轨迹的检测结果。
这条 episode 为什么是当前这个分数？
这条数据最主要的问题是什么？
我应该优先看哪几个时间段？
有没有数据完整性问题？
灵巧手相关数据有没有明显异常？
请帮我生成一段人工复核备注。
```

---

### 5.5 useAiAssistant.ts

职责：

```text
维护 AI 助手状态
维护聊天记录
维护当前 episode 上下文
调用后端 API
处理 loading / error / fallback
控制面板开关
```

建议状态：

```ts
isOpen: boolean
isThinking: boolean
messages: AiMessage[]
episodeId: string
providerStatus: 'template' | 'ollama' | 'api' | 'unavailable'
lastError: string | null
```

---

## 6. 前端接入位置

请在 manual QC 页面中找到评分圈组件所在位置。

在评分圈容器中添加 AI 助手锚点。

推荐结构：

```vue
<div class="score-ring-wrapper">
  <ScoreRing :score="score" />

  <AiAssistantAnchor
    class="score-ring-ai-anchor"
    :episode-id="episodeId"
    :status="aiStatus"
    :active="aiPanelOpen"
    @open="openAiPanel"
  />
</div>

<AiAssistantPanel
  v-if="aiPanelOpen"
  :episode-id="episodeId"
  :context-summary="currentEpisodeContext"
  @close="closeAiPanel"
/>
```

CSS 位置建议：

```css
.score-ring-wrapper {
  position: relative;
}

.score-ring-ai-anchor {
  position: absolute;
  top: 18px;
  right: 26px;
  z-index: 10;
}
```

具体位置需要根据现有评分环尺寸微调，目标是让助手“嵌在评分圈缺口附近”，而不是像普通按钮一样孤立存在。

---

## 7. 后端设计目标

后端需要新增 AI Assistant 服务，不要污染现有 L3 v2 评分逻辑。

推荐新增模块：

```text
backend/
  app/
    ai_assistant/
      __init__.py
      schemas.py
      context_builder.py
      prompt_builder.py
      providers/
        __init__.py
        base.py
        ollama_provider.py
        openai_compatible_provider.py
      chat_service.py
      validator.py
      router.py
```

如果当前项目目录不同，请遵循现有结构，但保持 AI Assistant 独立。

---

## 8. 后端 API 设计

### 8.1 聊天接口

推荐接口：

```text
POST /api/ai-assistant/chat
```

请求：

```json
{
  "episodeId": "episode_xxx",
  "message": "帮我解释一下这条轨迹的检测结果",
  "conversationId": "optional_conversation_id",
  "useCurrentContext": true
}
```

响应：

```json
{
  "conversationId": "conv_xxx",
  "source": "ollama",
  "model": "qwen2.5:14b",
  "answer": "本条 episode 整体质量较好，当前主要短板为可学习性……",
  "latencyMs": 1320,
  "fallbackUsed": false,
  "references": [
    {
      "type": "metric",
      "metricId": "LQ-01",
      "name": "动作密度"
    }
  ],
  "suggestedActions": [
    {
      "type": "jump_to_time",
      "label": "查看 8-15 秒",
      "startSec": 8.0,
      "endSec": 15.0
    }
  ],
  "warnings": []
}
```

---

### 8.2 快捷解释接口，可选

如果已有 `/api/ai/explain`，可以复用。

推荐：

```text
POST /api/ai-assistant/explain-current
```

用途：

```text
一键生成当前 episode 的解释
不需要用户输入自由文本
更适合快捷按钮“解释检测结果”
```

---

## 9. Episode 上下文构建

不要把前端页面上的所有原始数据直接丢给模型。

请实现 `context_builder.py`，将当前 episode 信息整理为模型可读的摘要。

上下文建议包括：

```json
{
  "episode": {
    "episodeId": "xxx",
    "durationSec": 42.5,
    "fps": 30,
    "robot": "dual-arm",
    "armDof": 7,
    "handDof": 6
  },
  "quality": {
    "score": 9.2,
    "level": "good",
    "summary": "该 episode 的训练数据质量较好，当前主要短板为：可学习性。",
    "weightedScoreBeforeCap": 9.2,
    "capTriggered": false,
    "capReason": null
  },
  "metrics": [
    {
      "metricId": "LQ-01",
      "name": "动作密度",
      "score": 7.8,
      "level": "warn",
      "description": "有效动作占比略低"
    }
  ],
  "topIssues": [
    {
      "metricId": "LQ-01",
      "name": "动作密度",
      "score": 7.8,
      "reason": "可学习性相对其他维度偏弱"
    }
  ],
  "timelineSegments": [
    {
      "startSec": 8.0,
      "endSec": 15.0,
      "label": "停滞",
      "level": "warn",
      "sourceMetricId": "LQ-02"
    }
  ]
}
```

注意：

```text
上下文必须来自已有 L3 指标和页面数据
不要让模型自己重新计算分数
不要让模型访问未授权数据
不要把大体积 telemetry 原始数组直接塞进 prompt
```

---

## 10. Provider 抽象

后端需要支持多种模型来源。

配置建议：

```env
AI_ASSISTANT_ENABLED=false
AI_ASSISTANT_PROVIDER=ollama

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

OPENAI_COMPATIBLE_BASE_URL=
OPENAI_COMPATIBLE_API_KEY=
OPENAI_COMPATIBLE_MODEL=

AI_ASSISTANT_TIMEOUT_SECONDS=8
AI_ASSISTANT_MAX_HISTORY=10
AI_ASSISTANT_MAX_OUTPUT_CHARS=800
```

默认要求：

```text
AI_ASSISTANT_ENABLED=false
```

只有显式开启时才调用模型。

Provider 需要支持：

```text
ollama
openai_compatible
template
```

当模型不可用时，自动降级为 template 或返回友好错误。

---

## 11. Prompt 设计

请实现系统 prompt。

核心原则：

```text
你是 Robot QC V1 的 AI 质检助手。
你只能解释已有自动检测结果，不能重新评分。
你不能直接给出 pass/fail 结论。
你必须基于当前 episode 上下文回答。
不知道的信息要明确说明“不确定”。
不要编造不存在的指标、时间段、传感器故障或硬件原因。
如果用户询问是否通过，只能给出“建议人工重点关注哪些问题”，不能替质检员下结论。
```

推荐 system prompt：

```text
你是 Robot QC V1 的 AI 质检助手，服务于机器人遥操作数据人工质检页面。

你的职责：
1. 解释当前 episode 的自动检测结果。
2. 帮助质检员理解 MQ、LQ、DI、DX 等指标。
3. 指出已有指标中最值得关注的问题。
4. 根据已有 timelineSegments 建议优先查看的时间段。
5. 帮助生成客观的人工复核备注。

严格限制：
1. 你不能重新计算评分。
2. 你不能修改 L3 指标结果。
3. 你不能直接决定 pass/fail。
4. 你不能编造上下文中不存在的指标、分数、异常时间段或硬件原因。
5. 如果信息不足，请明确说明需要人工结合视频和曲线判断。
6. 如果用户问“这条能不能过”，请回答为“从自动检测结果看，需要重点关注……最终结论仍由质检员判断”。

回答风格：
1. 中文。
2. 简洁、专业、客观。
3. 优先引用指标 ID、指标名称、分数和时间段。
4. 面向质检员，不要写成论文解释。
```

---

## 12. 快捷按钮 Prompt

请为快捷按钮准备固定 prompt。

### 12.1 解释检测结果

```text
请解释当前 episode 的自动检测结果，说明整体质量、主要短板、是否存在数据完整性问题，以及质检员应该优先关注什么。
```

### 12.2 为什么被降分

```text
请说明当前 episode 为什么不是满分，哪些指标拉低了总分，是否触发了 Q_motion 截断规则。
```

### 12.3 总结主要异常

```text
请总结当前 episode 中最主要的 1-3 个异常或风险点，并引用对应指标和时间段。
```

### 12.4 推荐查看时间段

```text
请根据当前 episode 的 timelineSegments，告诉我应该优先查看哪些时间段，并说明原因。
```

### 12.5 灵巧手检查

```text
请根据当前 episode 的指标和上下文，说明灵巧手相关数据是否有需要关注的问题。如果当前上下文没有灵巧手专项指标，请明确说明。
```

### 12.6 生成人工复核备注

```text
请帮我生成一段客观、简短的人工复核备注，只描述自动检测结果和建议关注点，不直接写 pass/fail 结论。
```

---

## 13. 输出校验

请实现 `validator.py`，对模型回复进行基本校验。

至少检查：

```text
回复不能为空
回复长度不能超过配置上限
不能出现“建议直接通过”“建议判 fail”“必须 fail”等越权结论
不能出现上下文中不存在的 metricId
如果用户问截断，回答应包含“截断”或“封顶”
不能出现明显占位符，如 <xxx>、{xxx}
```

如果校验失败：

```text
返回 template fallback
warnings 中记录原因
```

---

## 14. Fallback 策略

模型不可用时，AI 面板不能崩溃。

降级策略：

```text
1. 如果 AI_ASSISTANT_ENABLED=false：
   返回 template 模式的简短解释。

2. 如果 provider 连接失败：
   返回“AI 助手暂不可用，请以指标、视频和人工判断为准。”

3. 如果 LLM 输出不合规：
   返回规则模板解释。

4. 如果当前 episode 上下文缺失：
   提示“当前 episode 上下文不足，无法生成完整解释。”
```

前端失败文案：

```text
AI 解读暂不可用，请以指标、视频和人工判断为准。
```

---

## 15. 时间轴联动预留

AI 回复中如果 references 或 suggestedActions 包含时间段，前端应预留按钮：

```text
跳转到 8.0s
查看 8-15s
高亮 DI-02
```

第一阶段可以只完成 UI 和事件 emit：

```ts
emit('jump-to-time', { startSec, endSec })
emit('highlight-metric', metricId)
```

如果 manual QC 页面已有对应函数，则直接接入。

---

## 16. 安全与隐私要求

必须满足：

```text
默认使用本地模型
默认不启用第三方 API
第三方 API 必须由配置显式开启
不能把数据上传到未配置的外部服务
不能在前端暴露 API key
API key 只能保存在后端环境变量
日志中不能打印完整 API key
日志中不要打印大体积 episode 原始数据
```

---

## 17. 测试要求

请新增测试，至少覆盖：

```text
1. AI_ASSISTANT_ENABLED=false 时返回 template 或 unavailable
2. Ollama 不可用时不影响接口返回
3. 快捷按钮 prompt 能正常发送
4. 模型回复出现 pass/fail 越权结论时被拦截
5. 上下文中不存在的 metricId 不允许出现在最终回答中
6. 当前 episode 上下文能正确包含 score、summary、metrics、timelineSegments
7. 前端点击助手入口后聊天面板正常打开和关闭
8. 前端请求失败时页面不崩溃
```

推荐文件：

```text
tests/test_ai_assistant_chat.py
tests/test_ai_assistant_context.py
```

前端测试按现有项目测试框架执行。

---

## 18. 文档要求

请新增文档：

```text
docs/ai_assistant_design.md
```

内容包括：

```text
1. 功能目标
2. 产品交互说明
3. 前端组件结构
4. 后端模块结构
5. API 说明
6. Provider 配置说明
7. Prompt 设计
8. Fallback 策略
9. 安全与隐私说明
10. 后续升级方向
```

---

## 19. 验收标准

完成后应满足：

```text
1. manual QC 页面评分圈附近出现 AI 助手入口
2. 默认只显示助手入口，不自动弹出聊天框
3. hover 有轻微动态反馈
4. click 后聊天面板正常展开
5. 面板中有快捷问题按钮
6. 支持自由输入问题
7. 后端能接收 episodeId 和 message
8. 后端能构建当前 episode 上下文
9. 后端能根据配置调用 Ollama 或 OpenAI-compatible provider
10. 模型不可用时页面不崩溃
11. AI 不输出 pass/fail 最终结论
12. 不修改现有 L3 评分逻辑
13. 不影响现有质检提交流程
14. 有基础测试
15. 有设计文档
```

---

## 20. 推荐实施顺序

请按以下顺序执行：

```text
Step 1：阅读 manual QC 页面和评分圈组件结构
Step 2：确认当前 episode 数据在前端的获取方式
Step 3：设计 AiAssistantAnchor.vue 并嵌入评分圈附近
Step 4：实现 AiAssistantPanel.vue 和快捷问题按钮
Step 5：新增 useAiAssistant.ts 管理聊天状态
Step 6：新增后端 ai_assistant 模块
Step 7：实现 context_builder.py
Step 8：实现 provider 抽象和 ollama provider
Step 9：实现 /api/ai-assistant/chat
Step 10：实现 prompt_builder 和 validator
Step 11：接通前后端聊天流程
Step 12：增加 fallback
Step 13：增加基础测试
Step 14：补充 docs/ai_assistant_design.md
Step 15：输出变更总结和未完成风险
```

---

## 21. 后续升级方向

当前阶段完成后，可继续规划：

```text
1. Rive / Lottie 高质量助手动画
2. 时间轴跳转和异常段高亮
3. AI 回复引用指标卡片
4. 多轮对话记忆
5. 支持 vLLM 部署
6. 支持多模态曲线截图辅助检查
7. 支持 telemetry 摘要工具调用
8. 支持生成质检备注草稿
9. 支持不同质检员偏好的提示词配置
```

---

## 22. 最终交付说明

实现完成后，请输出：

```text
1. 新增了哪些文件
2. 修改了哪些文件
3. 前端入口在哪里
4. 后端接口如何调用
5. 环境变量如何配置
6. 如何开启 Ollama
7. 如何切换第三方 OpenAI-compatible API
8. fallback 如何验证
9. 现有功能是否受影响
10. 未完成事项和风险
```

---

## 23. 最重要的原则

请始终记住：

```text
这个 AI 助手不是一个普通聊天机器人。
它是嵌入 Robot QC V1 manual QC 页面中的质检 Copilot。
它应该轻量、专业、可折叠、可解释、可追溯。
它应该帮助质检员更快理解当前 episode，而不是替质检员做决定。
```
