from __future__ import annotations

from collections import deque

from app.services.list_snapshot import EPISODE_PATTERN
from app.services.scan_v3_types import (
    NamespaceCandidate,
    NamespaceDiscoveryResult,
    PrefixObservation,
)


def normalize_prefix(prefix: str) -> str:
    value = prefix.strip('/')
    return f'{value}/' if value else ''


def prefix_depth(prefix: str) -> int:
    return len([part for part in prefix.strip('/').split('/') if part])


def _direct_prefixes(service, bucket: str, prefix: str) -> list[str]:
    normalized = normalize_prefix(prefix)
    children: set[str] = set()
    for item in service.list_objects(bucket, prefix=normalized, recursive=False):
        object_name = str(getattr(item, 'object_name', '') or '')
        if not object_name or object_name == normalized:
            continue
        relative = object_name[len(normalized):] if object_name.startswith(normalized) else object_name
        segment = relative.split('/', 1)[0]
        if not segment:
            continue
        is_dir = bool(getattr(item, 'is_dir', False)) or '/' in relative
        if is_dir:
            children.add(f'{normalized}{segment}/')
    return sorted(children)


def _episode_prefixes(service, bucket: str, scope_prefix: str) -> list[str]:
    return [
        child
        for child in _direct_prefixes(service, bucket, scope_prefix)
        if EPISODE_PATTERN.fullmatch(child.rstrip('/').split('/')[-1])
    ]


def discover_namespaces(
    service,
    bucket: str,
    *,
    root_prefix: str = '',
    max_depth: int = 32,
    max_prefixes: int = 100_000,
) -> NamespaceDiscoveryResult:
    """Discover List roots without descending into episode object trees."""
    queue = deque([normalize_prefix(root_prefix)])
    visited: set[str] = set()
    candidates: list[NamespaceCandidate] = []
    observations: list[PrefixObservation] = []

    while queue:
        prefix = queue.popleft()
        if prefix in visited:
            continue
        visited.add(prefix)
        if len(visited) > max_prefixes:
            raise RuntimeError(f'namespace discovery exceeded {max_prefixes} prefixes')

        depth = prefix_depth(prefix)
        if depth > max_depth:
            continue
        direct_children = _direct_prefixes(service, bucket, prefix)
        raw_prefix = f'{prefix}raw/'
        processed_prefix = f'{prefix}processed/'
        has_raw = raw_prefix in direct_children
        has_processed = processed_prefix in direct_children
        raw_episodes = _episode_prefixes(service, bucket, raw_prefix) if has_raw else []
        processed_episodes = _episode_prefixes(service, bucket, processed_prefix) if has_processed else []
        is_candidate = bool(raw_episodes or processed_episodes)

        observations.append(PrefixObservation(
            prefix=prefix,
            depth=depth,
            has_raw_child=has_raw,
            has_processed_child=has_processed,
            has_episode_grandchild=is_candidate,
            is_list_candidate=is_candidate,
        ))
        if is_candidate:
            candidates.append(NamespaceCandidate(
                prefix=prefix,
                has_raw=bool(raw_episodes),
                has_processed=bool(processed_episodes),
                raw_episode_count=len(raw_episodes),
                processed_episode_count=len(processed_episodes),
            ))

        # raw/processed contents are terminal for discovery. Other branches may
        # contain nested Lists and remain eligible even below a List root.
        for child in direct_children:
            if child not in {raw_prefix, processed_prefix}:
                queue.append(child)

    return NamespaceDiscoveryResult(
        candidates=tuple(sorted(candidates, key=lambda item: item.prefix)),
        observations=tuple(sorted(observations, key=lambda item: (item.depth, item.prefix))),
        enumeration_complete=True,
    )
