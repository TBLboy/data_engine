"""L3 v2 RDDQF 参数持久化模型."""

import json
from sqlalchemy import Column, Integer, Text, DateTime, func
from app.core.db import Base


def default_l3_v2_params() -> dict:
    return {
        # ── MQ-01 轨迹平滑度 ──
        'mq01_good': 0.006,
        'mq01_warn': 0.018,
        'mq01_bad': 0.045,
        'mq01_weight': 0.38,
        'mq01_spike_p98_floor': 0.035,

        # ── MQ-02 动作连续性 ──
        'mq02_good': 0.010,
        'mq02_warn': 0.030,
        'mq02_bad': 0.080,
        'mq02_weight': 0.32,
        'mq02_threshold_floor': 0.06,

        # ── MQ-03 运动稳定性 ──
        'mq03_osc_threshold': 0.03,
        'mq03_chat_threshold': 0.08,
        'mq03_osc_weight': 0.6,
        'mq03_chat_weight': 0.4,
        'mq03_good': 0.05,
        'mq03_warn': 0.15,
        'mq03_bad': 0.35,
        'mq03_weight': 0.30,

        # ── LQ-01 有效动作比 ──
        'lq01_eps_arm': 0.004,
        'lq01_eps_hand': 0.011764705882352941,
        'lq01_good': 0.50,
        'lq01_warn': 0.25,
        'lq01_bad': 0.08,
        'lq01_weight': 0.38,
        'lq01_min_dur': 1.0,
        'lq01_gap_merge': 0.3,

        # ── LQ-02 信息密度 ──
        'lq02_eps_arm': 0.004,
        'lq02_eps_hand': 0.011764705882352941,
        'lq02_coverage_weight': 0.7,
        'lq02_state_weight': 0.3,
        'lq02_good': 0.030,
        'lq02_warn': 0.012,
        'lq02_bad': 0.003,
        'lq02_weight': 0.34,

        # ── LQ-03 低价值片段 ──
        'lq03_eps_arm': 0.004,
        'lq03_eps_hand': 0.011764705882352941,
        'lq03_tau_q_floor': 0.0005,
        'lq03_min_seg_dur': 1.0,
        'lq03_good': 0.18,
        'lq03_warn': 0.38,
        'lq03_bad': 0.65,
        'lq03_weight': 0.28,

        # ── DI-01 时间戳规则性 ──
        'di01_jitter_weight': 0.5,
        'di01_gap_weight': 0.3,
        'di01_invalid_weight': 0.2,
        'di01_gap_multiplier': 2.0,
        'di01_good': 0.05,
        'di01_warn': 0.15,
        'di01_bad': 0.35,
        'di01_weight': 0.45,

        # ── DI-02 同步有效性 ──
        'di02_tau_warn_mult': 2.0,
        'di02_tau_warn_floor': 0.05,
        'di02_tau_bad_mult': 6.0,
        'di02_tau_bad_floor': 0.20,
        'di02_w_flag': 0.30,
        'di02_w_hard': 0.25,
        'di02_w_soft': 0.20,
        'di02_w_sync': 0.15,
        'di02_w_seg': 0.10,
        'di02_good': 0.06,
        'di02_warn': 0.15,
        'di02_bad': 0.35,
        'di02_weight': 0.55,

        # ── DX-01 执行诊断 ──
        'dx01_max_lag': 5,
        'dx01_lag_ratio': 10,
        'dx01_tau_warn': 0.20,
        'dx01_tau_bad': 0.35,
        'dx01_w_p95': 0.5,
        'dx01_w_mean': 0.3,
        'dx01_w_persist': 0.2,
        'dx01_arm_weight': 0.7,
        'dx01_hand_weight': 0.3,

        # ── 特征提取 ──
        'fe_osc_pct': 10,
        'fe_chat_pct': 10,

        # ── 质量融合 ──
        'qf_motion_weight': 0.40,
        'qf_learn_weight': 0.40,
        'qf_data_weight': 0.20,
        'qf_motion_softmin_ratio': 0.2,
        'qf_learn_softmin_ratio': 0.2,
        'qf_data_softmin_ratio': 0.4,
        'qf_data_cap_strict': 4.5,
        'qf_data_cap_moderate': 6.0,
        'qf_data_cap_strict_threshold': 3.0,
        'qf_data_cap_moderate_threshold': 5.0,

        # ── 评分等级 ──
        'sl_level_good': 7.5,
        'sl_level_warn': 5.0,
    }


class L3V2Config(Base):
    __tablename__ = 'l3_v2_config'

    id = Column(Integer, primary_key=True, default=1)
    params_json = Column(Text, nullable=False, default='{}')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Text, nullable=True)

    @classmethod
    def get_params(cls, db) -> dict:
        row = db.query(cls).filter(cls.id == 1).first()
        if not row:
            return default_l3_v2_params()
        try:
            stored = json.loads(row.params_json)
        except (json.JSONDecodeError, TypeError):
            return default_l3_v2_params()
        defaults = default_l3_v2_params()
        defaults.update(stored)
        return defaults

    @classmethod
    def save_params(cls, db, params: dict, updated_by: str = ''):
        row = db.query(cls).filter(cls.id == 1).first()
        if not row:
            row = cls(id=1)
            db.add(row)
        row.params_json = json.dumps(params, ensure_ascii=False)
        row.updated_by = updated_by
        db.commit()
        return row
