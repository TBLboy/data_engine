# RDDQF v1.1 Final Design Sync Package

This package is an updated, synchronized version of the RDDQF v1.0 final design package. It keeps the original theory documents, and adds the v1.1 implementation synchronization updates produced after metric-by-metric review and real camera synchronization issue analysis.

## What changed in v1.1

- Corrected MQ-01 Trajectory Smoothness to use joint jerk / third difference rather than second difference.
- Re-defined MQ-02 Motion Continuity as action second difference instead of action step magnitude.
- Re-defined MQ-03 Motion Stability as persistent oscillation and hand chatter with amplitude gating.
- Reworked LQ-01/LQ-02/LQ-03 into Effective Coverage, Information Density, and Low-value Segment Duration.
- Reworked DI-01/DI-02 into robust timestamp regularity and adaptive sensor synchronization diagnostics.
- Added DI-03 / OQ-01 Camera Temporal Continuity for wrist camera freeze, stale frame, dropped frame, and jump-after-freeze cases.
- Moved DX-01 Command Tracking Error out of Training Quality Score and into Execution Diagnostics.
- Updated score fusion: Motion 40%, Learnability 40%, Data Integrity 20%, with Data Integrity score caps and reliability warnings.
- Added camera-frame timestamp explanation requirements, including a recommended `camera_frame_index.json` sidecar.

## Document order

1. `01_Training_Data_Quality_Standard`  
   Defines what high-quality robot training data means.

2. `02_Quality_Ontology`  
   Defines the quality taxonomy and semantic structure. v1.1 appendix adds Camera Temporal Continuity nodes.

3. `03_Evidence_Specification`  
   Defines the evidence layer for explainable data quality assessment. v1.1 appendix adds sensor-specific evidence and camera frame index requirements.

4. `04_Metric_Library`  
   Defines the metric library organized by ontology nodes. v1.1 appendix summarizes all MQ/LQ/DI/DX/Fusion revisions.

5. `05_L3MetricsEngine_v2_Architecture`  
   Defines the engineering architecture for implementing L3 v2. v1.1 appendix adds required engine/API/UI capabilities.

6. `06_Overall_Architecture_v2`  
   Overall architecture book. v2.1 appendix emphasizes diagnostic explainability and reliability gating.

7. `07_Background_Context`  
   Original project background and upstream TeleDex data documentation.

8. `08_L3_v2_Metric_Revision_Update`  
   New consolidated v1.1 update document with formulas, thresholds, and agent implementation tasks.

9. `99_Render_Verification`  
   Render verification outputs and build notes.

## Recommended implementation priority

1. Apply MQ-01/MQ-02/MQ-03 fixes.
2. Apply LQ-01/LQ-02/LQ-03 fixes.
3. Apply DI-01/DI-02 fixes and sensor-specific sync diagnostics.
4. Add DI-03 / OQ-01 Camera Temporal Continuity.
5. Move DX-01 to diagnostic-only output.
6. Update score fusion and frontend explanation UI.
