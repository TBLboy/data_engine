"""通用配置持久化模型."""

import json
from sqlalchemy import Column, Integer, Text, DateTime, func
from app.core.db import Base


def _ollama_host_port_from_settings() -> tuple[str, int, str]:
    """Prefer env/settings defaults so Docker can reach host Ollama without UI setup."""
    try:
        from app.core.config import get_settings
        settings = get_settings()
        model = settings.ollama_model or 'qwen2.5:7b'
        base = (settings.ollama_base_url or 'http://127.0.0.1:11434').rstrip('/')
        if '://' in base:
            base = base.split('://', 1)[1]
        host, _, port_text = base.partition(':')
        host = host or '127.0.0.1'
        try:
            port = int(port_text or '11434')
        except ValueError:
            port = 11434
        return host, port, model
    except Exception:
        return '127.0.0.1', 11434, 'qwen2.5:7b'


def default_general_config() -> dict:
    host, port, model = _ollama_host_port_from_settings()
    return {
        'batch_reject_threshold': 0.10,
        'ai_model_host': host,
        'ai_model_port': port,
        'ai_model_name': model,
        'scan_worker_replicas': 1,
        'scan_cron_hour': 0,
        'scan_cron_minute': 0,
        'scan_full_cron_day_of_week': 'sun',
        'scan_full_cron_hour': 2,
        'scan_full_cron_minute': 0,
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
