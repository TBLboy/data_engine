# AI QC Explain — 本地大模型辅助质检解释 设计文档

## 1. 功能目标

在 manual QC 页面中，利用本地部署的大模型（Ollama），将 L3 v2 引擎产出的 12 项结构化指标结果翻译成质检员可读的中文自然语言解释。降低质检员的判读门槛，减少"数字多、理解难"的问题。

## 2. 不做什么

- 不让 LLM 修改质量分或 pass/fail 结论
- 不让 LLM 替代 L3 指标计算
- 不让 LLM 直接分析视频或图片
- 不引入云端模型 API
- AI 解读失败不影响质检员提交 QC 结论

## 3. 模块结构

```text
backend/app/ai_qc/
  __init__.py           # 模块说明
  schemas.py            # Pydantic 请求/响应模型
  facts_builder.py      # 确定性 facts 生成器
  template_renderer.py  # 规则模板 fallback
  prompt_builder.py     # LLM prompt 构造
  llm_client.py         # Ollama HTTP 客户端
  validator.py          # LLM 输出校验
  service.py            # 主服务编排
```

## 4. 核心流程

```text
POST /api/ai/explain
  │
  ├─ 1. build_qc_facts(metrics) → 确定性事实结构
  │     - 判断 capTriggered
  │     - 提取 topIssues (score < 5 优先)
  │     - 提取 normalEvidence
  │
  ├─ 2. render_template(facts) → 规则模板文本 (fallback base)
  │
  ├─ 3. if AI_EXPLAIN_ENABLED=true:
  │      ├─ build_prompt(facts) → prompt
  │      ├─ call_ollama(prompt) → llm_text | None
  │      ├─ validate(llm_text, facts) → valid?
  │      └─ 通过 → 返回 llm_text
  │          失败 → 返回 template_text (fallbackUsed=true)
  │
  └─ 4. 返回 AiExplainResponse
```

## 5. API 说明

### POST /api/ai/explain

**Request:**
```json
{
  "episodeId": "xxx",
  "qMotionScore": 3.0,
  "qMotionLevel": "bad",
  "weightedScoreBeforeCap": 7.7,
  "metrics": [...],
  "timelineSegments": [...]
}
```

**Response:**
```json
{
  "enabled": true,
  "source": "llm | template | unavailable",
  "model": "qwen2.5:7b",
  "latencyMs": 1320,
  "explanation": "本段数据整体质量较差...",
  "fallbackUsed": false,
  "mentionedMetricIds": ["DI-02"],
  "warnings": []
}
```

## 6. Fallback 策略

```
LLM 调用失败 → fallback
LLM 超时 → fallback
LLM 返回空 → fallback
LLM 输出校验失败 → fallback
AI_EXPLAIN_ENABLED=false → 直接 template（不视为 fallback）
```

优先级：template 总是可用，LLM 失败静默退化。

## 7. Prompt 设计

核心约束：
- 只能使用传入的【事实数据】，不得编造
- 输出中文 120-200 字
- 不输出 pass/fail 判定
- capTriggered=true 时必须解释封顶规则
- 不要 Markdown/列表/JSON 格式

## 8. 环境变量

```env
AI_EXPLAIN_ENABLED=false       # 默认关闭 LLM
AI_EXPLAIN_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
AI_EXPLAIN_TIMEOUT_SECONDS=10
```

## 9. 如何本地测试

```bash
# 1. 环境核查
python scripts/check_ai_runtime.py

# 2. 运行测试 (不需要 Ollama)
./backend/.conda-env/bin/python tests/test_ai_qc_explain.py

# 3. 启动 Ollama 后测试 API
curl -X POST http://localhost:8000/api/ai/explain \
  -H 'Content-Type: application/json' \
  -d '{"episodeId":"test","qMotionScore":3.0,"qMotionLevel":"bad","metrics":[...]}'

# 4. 启用 LLM
export AI_EXPLAIN_ENABLED=true
# 重启 backend
```

## 10. 后续多模态阶段预留

当前模块通过 `AiExplainService` 抽象了 LLM 调用，后续升级到多模态时：
- `llm_client.py` 可扩展为多模态客户端（添加 base64 image 参数）
- `prompt_builder.py` 可添加 vision prompt 构造
- 保持现有 facts_builder / template_renderer / validator 不变
- 前端卡片基础组件可复用
