from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ClassificationRule, TaskType

RULE_SPECS = [
    {'pattern': 'huangguakuai', 'task_type_id': 'task_type:huangguakuai', 'candidate_label': 'huangguakuai', 'priority': 120, 'is_authoritative': True},
    {'pattern': 'tudoutiao', 'task_type_id': 'task_type:tudoutiao', 'candidate_label': 'tudoutiao', 'priority': 120, 'is_authoritative': True},
    {'pattern': 'huanggua', 'task_type_id': 'task_type:huanggua', 'candidate_label': 'huanggua', 'priority': 100, 'is_authoritative': True},
    {'pattern': 'tudou', 'task_type_id': 'task_type:tudou', 'candidate_label': 'tudou', 'priority': 100, 'is_authoritative': True},
    {'pattern': 'luobo', 'task_type_id': 'task_type:luobo', 'candidate_label': 'luobo', 'priority': 90, 'is_authoritative': True},
    {'pattern': 'fanqieluobo', 'task_type_id': 'task_type:fanqie_luobo', 'candidate_label': 'fanqie_luobo', 'priority': 80, 'is_authoritative': False},
    {'pattern': 'huanggualuobo', 'task_type_id': 'task_type:huanggua_luobo', 'candidate_label': 'huanggua_luobo', 'priority': 80, 'is_authoritative': False},
    {'pattern': 'misezhuobu_tudoutiao', 'task_type_id': 'task_type:misezhuobu_tudoutiao', 'candidate_label': 'misezhuobu_tudoutiao', 'priority': 70, 'is_authoritative': False},
    {'pattern': 'fengqintudou', 'task_type_id': 'task_type:fengqin_tudou', 'candidate_label': 'fengqin_tudou', 'priority': 70, 'is_authoritative': False},
    {'pattern': 'tiaoliaoping', 'task_type_id': 'task_type:tiaoliaoping', 'candidate_label': 'tiaoliaoping', 'priority': 60, 'is_authoritative': False},
]

TASK_TYPE_SPECS = [
    {'id': 'task_type:unclassified', 'name': '待分类', 'description': '尚未完成任务类型确认的采集任务', 'is_active': True},
    {'id': 'task_type:huanggua', 'name': '黄瓜', 'description': '单一黄瓜食材采集任务', 'is_active': True},
    {'id': 'task_type:huangguakuai', 'name': '黄瓜块', 'description': '黄瓜块食材采集任务', 'is_active': True},
    {'id': 'task_type:tudou', 'name': '土豆', 'description': '单一土豆食材采集任务', 'is_active': True},
    {'id': 'task_type:tudoutiao', 'name': '土豆条', 'description': '土豆条食材采集任务', 'is_active': True},
    {'id': 'task_type:luobo', 'name': '萝卜', 'description': '单一萝卜食材采集任务', 'is_active': True},
    {'id': 'task_type:fanqie_luobo', 'name': '番茄萝卜', 'description': '番茄与萝卜复合采集任务', 'is_active': True},
    {'id': 'task_type:huanggua_luobo', 'name': '黄瓜萝卜', 'description': '黄瓜与萝卜复合采集任务', 'is_active': True},
    {'id': 'task_type:misezhuobu_tudoutiao', 'name': '米色桌布土豆条', 'description': '带场景前缀的土豆条流程任务', 'is_active': True},
    {'id': 'task_type:fengqin_tudou', 'name': '风琴土豆', 'description': '风琴土豆流程任务', 'is_active': True},
    {'id': 'task_type:tiaoliaoping', 'name': '调料瓶', 'description': '调料瓶相关采集任务', 'is_active': True},
]


def seed_classification_rules(db: Session, *, created_by: str = 'system') -> None:
    existing_task_types = {item.id: item for item in db.query(TaskType).all()}
    for spec in TASK_TYPE_SPECS:
        task_type = existing_task_types.get(spec['id'])
        if not task_type:
            task_type = TaskType(
                id=spec['id'],
                name=spec['name'],
                description=spec['description'],
                is_active=bool(spec.get('is_active', True)),
            )
            db.add(task_type)
            existing_task_types[spec['id']] = task_type
        else:
            task_type.name = spec['name']
            task_type.description = spec['description']
            task_type.is_active = bool(spec.get('is_active', True))

    now = datetime.utcnow()
    for spec in RULE_SPECS:
        rule = db.query(ClassificationRule).filter(ClassificationRule.pattern == spec['pattern']).first()
        if not rule:
            rule = ClassificationRule(
                pattern=spec['pattern'],
                target_task_type_id=spec['task_type_id'],
                candidate_label=spec['candidate_label'],
                match_scope='basename',
                priority=spec['priority'],
                is_authoritative=spec['is_authoritative'],
                is_active=True,
                created_by=created_by,
                created_at=now,
            )
            db.add(rule)
            continue
        rule.target_task_type_id = spec['task_type_id']
        rule.candidate_label = spec['candidate_label']
        rule.match_scope = 'basename'
        rule.priority = spec['priority']
        rule.is_authoritative = spec['is_authoritative']
        rule.is_active = True
