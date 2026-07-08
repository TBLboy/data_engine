"""通用配置持久化模型."""

import json
from sqlalchemy import Column, Integer, Text, DateTime, func
from app.core.db import Base


def default_general_config() -> dict:
    return {
        'batch_reject_threshold': 0.10,
        'ai_model_host': '127.0.0.1',
        'ai_model_port': 11434,
        'ai_model_name': 'qwen2.5:7b',
    }


class GeneralConfig(Base):
    __tablename__ = 'general_config'

    id = Column(Integer, primary_key=True, default=1)
    params_json = Column(Text, nullable=False, default='{}')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Text, nullable=True)

    @classmethod
    def get_params(cls, db) -> dict:
        row = db.query(cls).filter(cls.id == 1).first()
        if not row:
            return default_general_config()
        try:
            stored = json.loads(row.params_json)
        except (json.JSONDecodeError, TypeError):
            return default_general_config()
        defaults = default_general_config()
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
