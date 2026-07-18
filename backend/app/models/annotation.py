from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex}'


def _utcnow() -> datetime:
    return datetime.utcnow()


class SubGoalSchema(Base):
    __tablename__ = 'sub_goal_schemas'
    __table_args__ = (
        UniqueConstraint('task_type_id', 'version_no', name='uq_sub_goal_schemas_task_type_version'),
        Index('ix_sub_goal_schemas_task_type_status', 'task_type_id', 'status'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _new_id('sgs'))
    task_type_id: Mapped[str] = mapped_column(ForeignKey('task_types.id'), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='draft', nullable=False, index=True)
    schema_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=_utcnow, nullable=False)
    published_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    retired_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    retirement_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    task_type = relationship('TaskType', foreign_keys=[task_type_id])
    definitions: Mapped[list['SubGoalDefinition']] = relationship(
        'SubGoalDefinition',
        back_populates='schema',
        order_by='SubGoalDefinition.sequence_no',
    )


class SubGoalDefinition(Base):
    __tablename__ = 'sub_goal_definitions'
    __table_args__ = (
        UniqueConstraint('sub_goal_schema_id', 'code', name='uq_sub_goal_definitions_schema_code'),
        UniqueConstraint('sub_goal_schema_id', 'sequence_no', name='uq_sub_goal_definitions_schema_sequence'),
        Index('ix_sub_goal_definitions_schema_id', 'sub_goal_schema_id'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _new_id('sgd'))
    sub_goal_schema_id: Mapped[str] = mapped_column(ForeignKey('sub_goal_schemas.id'), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_zh: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default='', nullable=False)
    action_verb: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_conditional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_occurrences: Mapped[int | None] = mapped_column(Integer, nullable=True)
    object_role_hints: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    schema = relationship('SubGoalSchema', back_populates='definitions')


class AnnotationTask(Base):
    __tablename__ = 'annotation_tasks'
    __table_args__ = (
        UniqueConstraint('episode_id', name='uq_annotation_tasks_episode_id'),
        Index('ix_annotation_tasks_work_status', 'work_status'),
        Index('ix_annotation_tasks_assignment', 'work_status', 'assigned_to'),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _new_id('ann'))
    episode_id: Mapped[str] = mapped_column(ForeignKey('episodes.id'), nullable=False)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), nullable=False, index=True)
    task_type_id: Mapped[str] = mapped_column(ForeignKey('task_types.id'), nullable=False, index=True)
    sub_goal_schema_id: Mapped[str] = mapped_column(ForeignKey('sub_goal_schemas.id'), nullable=False)
    sub_goal_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    sub_goal_schema_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    work_status: Mapped[str] = mapped_column(String(16), default='pending', nullable=False)
    status_before_invalidation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    invalidation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    assigned_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    assignment_note: Mapped[str] = mapped_column(Text, default='', nullable=False)
    public_claim_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    public_claim_enabled_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    public_claim_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    lock_owner: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    lock_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    current_revision_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    initial_source: Mapped[str] = mapped_column(String(16), default='manual', nullable=False)
    manual_from_scratch_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=_utcnow, onupdate=_utcnow, nullable=False)

    episode = relationship('Episode')
    batch = relationship('Batch')
    task_type = relationship('TaskType')
    schema = relationship('SubGoalSchema')
    assigned_user = relationship('User', foreign_keys=[assigned_to])
    lock_user = relationship('User', foreign_keys=[lock_owner])
    annotation: Mapped['EpisodeAnnotation'] = relationship(
        'EpisodeAnnotation', back_populates='task', uselist=False, cascade='all, delete-orphan'
    )
    revisions: Mapped[list['AnnotationRevision']] = relationship(
        'AnnotationRevision', back_populates='task', order_by='AnnotationRevision.revision_no'
    )


class EpisodeAnnotation(Base):
    __tablename__ = 'episode_annotations'
    __table_args__ = (UniqueConstraint('annotation_task_id', name='uq_episode_annotations_task_id'),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: _new_id('draft'))
    annotation_task_id: Mapped[str] = mapped_column(ForeignKey('annotation_tasks.id'), nullable=False)
    canonical_instruction_en: Mapped[str] = mapped_column(Text, default='', nullable=False)
    canonical_instruction_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    instruction_variants_en: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    episode_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    objects: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    task_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_sub_goal_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_successful_sub_goal_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    annotation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_modified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    annotation_schema_version: Mapped[str] = mapped_column(String(16), default='1.0', nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=_utcnow, onupdate=_utcnow, nullable=False)

    task: Mapped[AnnotationTask] = relationship('AnnotationTask', back_populates='annotation')
    sub_goal_instances: Mapped[list['EpisodeSubGoalInstance']] = relationship(
        'EpisodeSubGoalInstance',
        back_populates='annotation',
        order_by='EpisodeSubGoalInstance.sub_goal_definition_id, EpisodeSubGoalInstance.occurrence_no',
        cascade='all, delete-orphan',
    )


class EpisodeSubGoalInstance(Base):
    __tablename__ = 'episode_sub_goal_instances'
    __table_args__ = (
        UniqueConstraint(
            'episode_annotation_id', 'sub_goal_definition_id', 'occurrence_no',
            name='uq_episode_sub_goal_instances_occurrence',
        ),
        Index('ix_episode_sub_goal_instances_annotation_id', 'episode_annotation_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    episode_annotation_id: Mapped[str] = mapped_column(ForeignKey('episode_annotations.id'), nullable=False)
    sub_goal_definition_id: Mapped[str] = mapped_column(ForeignKey('sub_goal_definitions.id'), nullable=False)
    occurrence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='observed')
    start_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_step_exclusive: Mapped[int | None] = mapped_column(Integer, nullable=True)
    representative_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(24), default='human', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=_utcnow, onupdate=_utcnow, nullable=False)

    annotation: Mapped[EpisodeAnnotation] = relationship('EpisodeAnnotation', back_populates='sub_goal_instances')
    definition: Mapped[SubGoalDefinition] = relationship('SubGoalDefinition')


class AnnotationRevision(Base):
    __tablename__ = 'annotation_revisions'
    __table_args__ = (
        UniqueConstraint('annotation_task_id', 'revision_no', name='uq_annotation_revisions_task_revision'),
        Index('ix_annotation_revisions_episode_annotation_id', 'episode_annotation_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    annotation_task_id: Mapped[str] = mapped_column(ForeignKey('annotation_tasks.id'), nullable=False)
    episode_annotation_id: Mapped[str] = mapped_column(ForeignKey('episode_annotations.id'), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    annotation_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=_utcnow, nullable=False)

    task: Mapped[AnnotationTask] = relationship('AnnotationTask', back_populates='revisions')
    annotation: Mapped[EpisodeAnnotation] = relationship('EpisodeAnnotation')
