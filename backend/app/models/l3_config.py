"""L3 指标超参数持久化模型."""

import json
from sqlalchemy import Column, Integer, Text, DateTime, func
from app.core.db import Base


class L3Config(Base):
    __tablename__ = 'l3_config'

    id = Column(Integer, primary_key=True, default=1)
    params_json = Column(Text, nullable=False, default='{}')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Text, nullable=True)

    @classmethod
    def get_params(cls, db):
        row = db.query(cls).filter(cls.id == 1).first()
        if not row:
            row = cls(id=1, params_json='{}')
            db.add(row)
            db.commit()
        try:
            return json.loads(row.params_json)
        except (json.JSONDecodeError, TypeError):
            return {}

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
