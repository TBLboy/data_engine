# RDDQF v1.1 设计规范

本压缩包为 RDDQF v1.1 正式设计规范交付包，用于指导灵机启物 L3 v2 训练数据质量评估体系的指标设计、证据解释、引擎实现、总分融合与前端诊断展示。

## 文件清单

1. `RDDQF_v1_1_design_specification.pdf`
   - 正式 PDF 文档。
   - 包含封面、目录、训练数据质量标准、质量本体、证据规范、指标库、L3MetricsEngine v2 架构、总体架构、v1.1 指标修订与工程实现要求。

2. `RDDQF_v1_1_design_specification.tex`
   - PDF 对应的 LaTeX 源码。
   - 可用于后续版本维护、重新编译和内容修订。

3. `README.md`
   - 当前交付包说明。

## 版本信息

- 文档版本：v1.1
- 适用对象：L3 v2 训练数据质量评估系统
- 核心范围：MQ / LQ / DI / DX 指标体系、证据层、Timeline、Data Integrity 可靠性上限、Camera Temporal Continuity、Training Quality Score Fusion
- 生成日期：2026-06-29

## 编译说明

PDF 使用 XeLaTeX 编译生成。源码依赖常见 TeX Live 宏包以及 CJK 字体支持。
