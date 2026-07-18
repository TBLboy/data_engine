from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ObjectSnapshot:
    object_key: str
    object_scope: str
    object_role: str
    size_bytes: int
    content_hash: str
    last_modified: datetime | None


@dataclass(frozen=True, slots=True)
class EpisodeSnapshot:
    episode_name: str
    raw_prefix: str
    processed_prefix: str
    raw_object_count: int
    processed_object_count: int
    raw_total_size_bytes: int
    processed_total_size_bytes: int
    raw_content_fingerprint: str
    processed_content_fingerprint: str
    latest_object_modified_at: datetime | None
    selective_objects: tuple[ObjectSnapshot, ...]
    manifest: dict | None = None
    manifest_error: str = ''


@dataclass(frozen=True, slots=True)
class ListSnapshot:
    bucket: str
    list_prefix: str
    episodes: tuple[EpisodeSnapshot, ...]
    object_count: int
    enumeration_complete: bool
    started_at: datetime
    finished_at: datetime
    range_start: str = ''
    range_end: str = ''

    @property
    def is_full_coverage(self) -> bool:
        return not self.range_start and not self.range_end


@dataclass(frozen=True, slots=True)
class NamespaceCandidate:
    prefix: str
    has_raw: bool
    has_processed: bool
    raw_episode_count: int
    processed_episode_count: int


@dataclass(frozen=True, slots=True)
class PrefixObservation:
    prefix: str
    depth: int
    has_raw_child: bool
    has_processed_child: bool
    has_episode_grandchild: bool
    is_list_candidate: bool


@dataclass(frozen=True, slots=True)
class NamespaceDiscoveryResult:
    candidates: tuple[NamespaceCandidate, ...]
    observations: tuple[PrefixObservation, ...]
    enumeration_complete: bool


@dataclass(slots=True)
class ResolutionResult:
    list_id: str
    batch_id: str
    new_episode_count: int = 0
    changed_episode_count: int = 0
    recovered_episode_count: int = 0
    suspect_episode_count: int = 0
    missing_episode_count: int = 0
    needs_missing_confirmation: bool = False
    touched_batch_ids: set[str] = field(default_factory=set)
