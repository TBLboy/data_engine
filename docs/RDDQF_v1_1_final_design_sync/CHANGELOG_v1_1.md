# RDDQF v1.1 Synchronization Change Log

## Modified documents

- `02_Quality_Ontology/robot_demonstration_quality_ontology_v1.tex/pdf`
  - Added v1.1 ontology appendix for Camera Temporal Continuity, stale frame risk, camera frame timestamp integrity, and sensor-specific desynchronization.

- `03_Evidence_Specification/robot_demonstration_quality_evidence_specification_v1.tex/pdf`
  - Added v1.1 appendix for sensor-specific evidence, `camera_frame_index.json`, and reliability warnings.

- `04_Metric_Library/robot_demonstration_metric_library_v1.tex/pdf`
  - Added v1.1 appendix summarizing MQ/LQ/DI/DX/Fusion metric revisions.

- `05_L3MetricsEngine_v2_Architecture/l3metrics_engine_v2_architecture_design.tex/pdf`
  - Added v1.1 appendix for new Feature/Evidence/Metric/Timeline/API/UI requirements.

- `06_Overall_Architecture_v2/rddqf_overall_architecture_v2.tex/pdf`
  - Added v2.1 appendix clarifying the shift from scoring-only to diagnostic quality platform.

## New document

- `08_L3_v2_Metric_Revision_Update/l3_v2_metric_revision_update_v1_1.tex/pdf`
  - Consolidated implementation update with formulas, provisional thresholds, fusion rules, reliability cap, camera temporal continuity, and Agent task list.

## Key design decisions

- `TrainingQualityScore = f(MQ, LQ, DI)`.
- `ExecutionDiagnosticScore = f(DX)`.
- `DX` does not enter `TrainingQualityScore`.
- Severe temporal integrity issues trigger reliability warnings and score caps.
- Severe wrist camera desynchronization should be treated as high-risk training data if wrist camera is part of the model observation.
