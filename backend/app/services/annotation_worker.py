"""Annotation generation worker — processes VLM jobs from persistent queue."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from datetime import datetime

from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import (
    AnnotationAiRun,
    AnnotationGenerationJob,
    AnnotationTask,
    Episode,
    EpisodeAnnotation,
    EpisodeSubGoalInstance,
    GeneralConfig,
    SubGoalSchema,
)
from app.services.annotation import active_qualified_episode_query, create_draft
from app.services.annotation_generation_queue import (
    cancel_pending_jobs_for_task,
    claim_next_job,
    complete_job,
    fail_job,
    heartbeat_job,
    should_cancel_job,
)
from app.services.annotation_vlm import (
    FRAME_SAMPLER_VERSION,
    PROMPT_VERSION,
    build_generation_prompt,
    normalize_occurrences,
    normalize_task_outcome,
    parse_vlm_payload,
    uniform_sample_steps,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _worker_id() -> str:
    return f'{socket.gethostname()}:{os.getpid()}'


def _looks_like_meta_instruction(text: str) -> bool:
    """Filter thinking-model prose / schema placeholders that are not real instructions."""
    lowered = text.strip().lower()
    if not lowered:
        return True
    if len(lowered) > 240:
        return True
    markers = (
        'we are given',
        'you are labeling',
        'return only',
        'json object',
        'sub-goal',
        'sub goal',
        'definitions',
        'frame_count',
        'sample steps',
        'occurrence',
        'the task is to label',
        'steps to follow',
        'maxoccurrences',
        'short imperative',
        'optional chinese',
        'one of ',
        'annotationSchemaVersion'.lower(),
        'canonicalinstruction',
        'field names',
        'schema prose',
        'allowed_',
    )
    return any(marker in lowered for marker in markers)


def _parsed_has_usable_fields(parsed: dict) -> bool:
    if not isinstance(parsed, dict):
        return False
    instr = str(
        parsed.get('canonicalInstructionEn')
        or parsed.get('canonical_instruction_en')
        or ''
    ).strip()
    if instr and not _looks_like_meta_instruction(instr):
        return True
    occ = parsed.get('occurrences') or parsed.get('subGoals') or []
    return isinstance(occ, list) and len(occ) > 0


def _build_json_convert_prompt(
    *,
    analysis_text: str,
    definition_codes: list[str],
    frame_count: int,
    task_description: str,
) -> str:
    codes = definition_codes or ['reach_object']
    example_code = codes[0]
    # Keep short: long analysis re-triggers thinking dumps without JSON.
    analysis = (analysis_text or '').strip()
    if len(analysis) > 1800:
        analysis = analysis[:900] + '\n...\n' + analysis[-800:]
    return (
        'Emit exactly one JSON object. No other text.\n'
        f'task={task_description}\n'
        f'frame_count={frame_count}\n'
        f'codes={codes}\n'
        'Required keys: canonicalInstructionEn, canonicalInstructionZh, taskOutcome, '
        'annotationSchemaVersion, occurrences.\n'
        f'Example: {{"canonicalInstructionEn":"Collect one radish.",'
        f'"canonicalInstructionZh":"采集一根萝卜","taskOutcome":"completed_normally",'
        f'"annotationSchemaVersion":"1.0","occurrences":[{{"definitionCode":"{example_code}",'
        f'"occurrenceNo":1,"status":"observed","startStep":0,"endStepExclusive":10,'
        f'"representativeStep":5,"failureReason":null,"notes":null}}]}}\n'
        f'Ranges: 0<=start<end<={frame_count}. Weak evidence => not_observed + null steps.\n'
        f'Notes from vision:\n{analysis}\n'
        'JSON:'
    )


def _validate_job_eligibility(db, job: AnnotationGenerationJob) -> str | None:
    task = db.query(AnnotationTask).filter(AnnotationTask.id == job.annotation_task_id).first()
    if not task:
        return 'annotation task no longer exists'
    if task.work_status == 'invalidated':
        return 'annotation task invalidated'
    episode = active_qualified_episode_query(db).filter(Episode.id == task.episode_id).first()
    if not episode:
        return 'episode left active qualified scope'
    if task.sub_goal_schema_id != job.sub_goal_schema_id:
        return f'task schema changed ({task.sub_goal_schema_id} != {job.sub_goal_schema_id})'
    if task.sub_goal_schema_content_hash != job.sub_goal_schema_content_hash:
        return 'task schema content hash changed'
    return None


def _load_job_snapshot(db, job: AnnotationGenerationJob) -> dict:
    settings = get_settings()
    gen_cfg = GeneralConfig.get_params(db)
    task = (
        db.query(AnnotationTask)
        .options(
            joinedload(AnnotationTask.episode),
            joinedload(AnnotationTask.schema).joinedload(SubGoalSchema.definitions),
        )
        .filter(AnnotationTask.id == job.annotation_task_id)
        .first()
    )
    if task is None:
        raise RuntimeError('annotation task missing for generation job')
    schema = task.schema
    definitions = list(schema.definitions) if schema else []
    frame_count = int(task.episode.frame_count or 0) if task.episode else 0
    sample_steps = uniform_sample_steps(frame_count)
    # Cap pixels sent to VLM for latency/VRAM; keep full sample_steps in prompt text.
    media_sample_steps = sample_steps if len(sample_steps) <= 6 else uniform_sample_steps(frame_count, max_samples=6)
    media_frames: list[dict] = []
    media_camera = ''
    media_object_key = ''
    media_error = ''
    episode_id = task.episode_id if task.episode is not None else ''
    if episode_id and media_sample_steps:
        try:
            from app.services.annotation_frame_sampler import resolve_rgb_video, sample_rgb_frames_b64

            resolved = resolve_rgb_video(db, episode_id)
            if resolved is not None:
                bucket, object_key = resolved
                media_object_key = object_key
                episode_duration = None
                if task.episode is not None:
                    try:
                        episode_duration = float(task.episode.duration_sec or 0) or None
                    except Exception:
                        episode_duration = None
                media_frames = sample_rgb_frames_b64(
                    bucket=bucket,
                    object_key=object_key,
                    sample_steps=media_sample_steps,
                    frame_count=frame_count,
                    duration_sec=episode_duration,
                )
                if media_frames:
                    media_camera = str(media_frames[0].get('camera') or '')
            else:
                media_error = 'no rgb video object'
        except Exception as exc:
            media_error = f'{type(exc).__name__}: {exc}'
            logger.exception('media sampling failed task=%s', job.annotation_task_id)
    media_frame_steps = [int(item['step']) for item in media_frames]
    prompt = build_generation_prompt(
        job_type=job.job_type,
        task_description=job.task_description_snapshot,
        schema_id=job.sub_goal_schema_id,
        schema_version=job.sub_goal_schema_version,
        definitions=definitions,
        frame_count=frame_count,
        sample_steps=sample_steps,
        media_frame_steps=media_frame_steps,
        media_camera=media_camera or None,
    )
    return {
        'annotation_task_id': job.annotation_task_id,
        'job_type': job.job_type,
        'task_description_snapshot': job.task_description_snapshot,
        'sub_goal_schema_id': job.sub_goal_schema_id,
        'sub_goal_schema_version': job.sub_goal_schema_version,
        'attempt_count': job.attempt_count,
        'model_name': str(gen_cfg.get('ai_model_name') or settings.ollama_model),
        'host': str(gen_cfg.get('ai_model_host') or '127.0.0.1'),
        'port': int(gen_cfg.get('ai_model_port') or 11434),
        'frame_count': frame_count,
        'sample_steps': sample_steps,
        'definition_codes': [item.code for item in definitions],
        'prompt': prompt,
        'images_b64': [item['b64'] for item in media_frames],
        'media_frame_steps': media_frame_steps,
        'media_camera': media_camera,
        'media_object_key': media_object_key,
        'media_image_count': len(media_frames),
        'media_error': media_error,
        'media_bytes_total': sum(int(item.get('bytes') or 0) for item in media_frames),
    }


def execute_generation_job(job_id: str, worker_id: str) -> None:
    settings = get_settings()
    snapshot: dict | None = None
    db = SessionLocal()
    try:
        job = (
            db.query(AnnotationGenerationJob)
            .filter(AnnotationGenerationJob.id == job_id)
            .with_for_update()
            .first()
        )
        if job is None or job.status != 'running' or job.lease_owner != worker_id:
            return
        disqualify = _validate_job_eligibility(db, job)
        if disqualify is not None:
            job.status = 'superseded'
            job.error_detail = disqualify
            job.lease_owner = ''
            job.lease_expires_at = None
            job.finished_at = _utcnow()
            cancel_pending_jobs_for_task(db, annotation_task_id=job.annotation_task_id)
            db.commit()
            return
        snapshot = _load_job_snapshot(db, job)
    finally:
        db.close()

    if snapshot is None:
        return

    try:
        from app.ai_qc.llm_client import call_ollama

        base_url = f'http://{snapshot["host"]}:{snapshot["port"]}'
        if snapshot['host'] in {'127.0.0.1', 'localhost'}:
            base_url = settings.ollama_base_url or base_url
        start = time.monotonic()
        images_b64 = list(snapshot.get('images_b64') or [])
        # Pass 1: vision (or text) with large budget. Thinking VLMs often dump analysis
        # into thinking/content and never emit schema JSON before num_predict ends.
        result = call_ollama(
            snapshot['prompt'],
            base_url=base_url,
            model=snapshot['model_name'],
            timeout_seconds=settings.annotation_vlm_timeout_seconds,
            format='json',
            temperature=0.1,
            num_predict=8192,
            images_b64=images_b64 or None,
        )
        raw_parts: list[str] = []
        if result and result.text:
            raw_parts.append(result.text)
        parsed = parse_vlm_payload(result.text) if result and result.text else {}
        usable = _parsed_has_usable_fields(parsed)
        # Pass 2: text-only conversion when pass 1 only produced analysis prose.
        if result and not usable:
            convert_prompt = _build_json_convert_prompt(
                analysis_text=result.text,
                definition_codes=list(snapshot.get('definition_codes') or []),
                frame_count=int(snapshot.get('frame_count') or 0),
                task_description=str(snapshot.get('task_description_snapshot') or ''),
            )
            from app.ai_qc.llm_client import call_ollama_generate

            # /api/generate + think=false puts JSON in response (chat path often empties content).
            convert = call_ollama_generate(
                convert_prompt,
                base_url=base_url,
                model=snapshot['model_name'],
                timeout_seconds=min(180, settings.annotation_vlm_timeout_seconds),
                format='json',
                temperature=0.0,
                num_predict=1024,
                think=False,
            )
            if convert and convert.text:
                raw_parts.append('---json_convert---\n' + convert.text)
                converted = parse_vlm_payload(convert.text)
                if _parsed_has_usable_fields(converted):
                    parsed = converted
                    usable = True
        latency_ms = int((time.monotonic() - start) * 1000)
        raw_text = '\n'.join(raw_parts)
        run_status = 'succeeded' if result else 'failed'
        error_detail = '' if result else 'VLM returned None'

        db = SessionLocal()
        try:
            run = AnnotationAiRun(
                annotation_task_id=snapshot['annotation_task_id'],
                annotation_generation_job_id=job_id,
                attempt_no=snapshot['attempt_count'],
                model_name=snapshot['model_name'],
                prompt_version=PROMPT_VERSION,
                frame_sampler_version=FRAME_SAMPLER_VERSION,
                input_summary_json=json.dumps(
                    {
                        'job_type': snapshot['job_type'],
                        'base_url': base_url,
                        'frame_count': snapshot['frame_count'],
                        'sample_steps': snapshot['sample_steps'],
                        'definition_codes': snapshot['definition_codes'],
                        'frame_sampler_version': FRAME_SAMPLER_VERSION,
                        'prompt_version': PROMPT_VERSION,
                        'media_image_count': snapshot.get('media_image_count', 0),
                        'media_frame_steps': snapshot.get('media_frame_steps') or [],
                        'media_camera': snapshot.get('media_camera') or '',
                        'media_object_key': snapshot.get('media_object_key') or '',
                        'media_bytes_total': snapshot.get('media_bytes_total') or 0,
                        'media_error': snapshot.get('media_error') or '',
                    },
                    ensure_ascii=False,
                ),
                raw_response_text=raw_text,
                parsed_response_json=json.dumps(parsed, ensure_ascii=False),
                run_status=run_status,
                error_detail=error_detail,
                duration_ms=latency_ms,
                created_at=_utcnow(),
                finished_at=_utcnow(),
            )
            db.add(run)
            if not result:
                fail_job(db, job_id=job_id, worker_id=worker_id, error=error_detail)
                db.commit()
                return
            db.commit()
            ai_run_id = run.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        _publish_generation_result(
            job_id=job_id,
            worker_id=worker_id,
            ai_run_id=ai_run_id,
            parsed=parsed,
        )
    except Exception as exc:
        db = SessionLocal()
        try:
            fail_job(db, job_id=job_id, worker_id=worker_id, error=f'{type(exc).__name__}: {exc}')
            db.commit()
        finally:
            db.close()


def _publish_generation_result(*, job_id: str, worker_id: str, ai_run_id: int, parsed: dict) -> None:
    del ai_run_id  # retained for future candidate linkage
    db = SessionLocal()
    try:
        job = (
            db.query(AnnotationGenerationJob)
            .filter(
                AnnotationGenerationJob.id == job_id,
                AnnotationGenerationJob.status == 'running',
                AnnotationGenerationJob.lease_owner == worker_id,
            )
            .with_for_update()
            .first()
        )
        if job is None:
            return
        if job.cancel_requested_at is not None:
            job.status = 'cancelled'
            job.lease_owner = ''
            job.lease_expires_at = None
            job.finished_at = _utcnow()
            job.error_detail = job.error_detail or 'cancelled before publish'
            db.commit()
            return
        disqualify = _validate_job_eligibility(db, job)
        if disqualify is not None:
            job.status = 'superseded'
            job.error_detail = disqualify
            job.lease_owner = ''
            job.lease_expires_at = None
            job.finished_at = _utcnow()
            cancel_pending_jobs_for_task(db, annotation_task_id=job.annotation_task_id)
            db.commit()
            return
        # Lock only the task row. joinedload + FOR UPDATE on outer joins
        # fails on PostgreSQL: "FOR UPDATE cannot be applied to the nullable side".
        task = (
            db.query(AnnotationTask)
            .filter(AnnotationTask.id == job.annotation_task_id)
            .with_for_update(of=AnnotationTask)
            .first()
        )
        if task is None:
            raise RuntimeError('task missing at publish')
        # Eager-load related rows after the row lock (no FOR UPDATE on joins).
        task = (
            db.query(AnnotationTask)
            .options(
                joinedload(AnnotationTask.episode),
                joinedload(AnnotationTask.schema).joinedload(SubGoalSchema.definitions),
                joinedload(AnnotationTask.annotation).joinedload(EpisodeAnnotation.sub_goal_instances),
            )
            .filter(AnnotationTask.id == job.annotation_task_id)
            .first()
        )
        if task is None:
            raise RuntimeError('task missing at publish')
        annotation = task.annotation or create_draft(db, task)
        is_blank_instruction = not (annotation.canonical_instruction_en or '').strip()
        has_instances = bool(list(annotation.sub_goal_instances or []))
        allow_auto_apply = (
            job.job_type in {'initial', 'all', 'sub_goals'}
            and not annotation.human_modified
        )
        mutated = False
        if allow_auto_apply and job.job_type in {'initial', 'all'} and is_blank_instruction:
            instruction_en = str(
                parsed.get('canonicalInstructionEn')
                or parsed.get('canonical_instruction_en')
                or ''
            ).strip()
            # Reject meta/reasoning fallback text that is not a real instruction.
            if instruction_en and _looks_like_meta_instruction(instruction_en):
                instruction_en = ''
            instruction_zh = parsed.get('canonicalInstructionZh')
            if instruction_zh is not None:
                instruction_zh = str(instruction_zh).strip() or None
            task_outcome = normalize_task_outcome(parsed.get('taskOutcome') or parsed.get('task_outcome'))
            schema_version = str(
                parsed.get('annotationSchemaVersion')
                or parsed.get('annotation_schema_version')
                or '1.0'
            )
            if instruction_en:
                annotation.canonical_instruction_en = instruction_en
                mutated = True
            if instruction_zh is not None:
                annotation.canonical_instruction_zh = instruction_zh
                mutated = True
            if task_outcome:
                annotation.task_outcome = task_outcome
                mutated = True
            annotation.annotation_schema_version = schema_version
        if allow_auto_apply and job.job_type in {'initial', 'all', 'sub_goals'} and not has_instances:
            frame_count = int(task.episode.frame_count or 0) if task.episode else 0
            definitions = list(task.schema.definitions) if task.schema else []
            occurrences = normalize_occurrences(
                parsed.get('occurrences') or parsed.get('subGoals') or [],
                definitions=definitions,
                frame_count=frame_count,
            )
            if occurrences:
                for item in occurrences:
                    annotation.sub_goal_instances.append(
                        EpisodeSubGoalInstance(
                            episode_annotation_id=annotation.id,
                            sub_goal_definition_id=item['definitionId'],
                            occurrence_no=item['occurrenceNo'],
                            status=item['status'],
                            start_step=item['startStep'],
                            end_step_exclusive=item['endStepExclusive'],
                            representative_step=item['representativeStep'],
                            failure_reason=item['failureReason'],
                            notes=item['notes'],
                            source=item['source'],
                        )
                    )
                mutated = True
        if mutated:
            annotation.row_version += 1
            task.row_version += 1
        if not complete_job(db, job_id=job_id, worker_id=worker_id):
            raise RuntimeError('job lease was lost during publication')
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_worker_forever() -> None:
    settings = get_settings()
    worker_id = _worker_id()
    logger.info('annotation worker started id=%s', worker_id)
    while True:
        db = SessionLocal()
        try:
            job = claim_next_job(db, worker_id=worker_id, lease_seconds=settings.annotation_worker_lease_seconds)
            db.commit()
            claimed_job_id = job.id if job is not None else None
        except Exception:
            db.rollback()
            logger.exception('failed to claim annotation generation job')
            claimed_job_id = None
        finally:
            db.close()
        if claimed_job_id is None:
            time.sleep(max(0.2, settings.annotation_worker_poll_seconds))
            continue

        start = time.monotonic()
        last_heartbeat = 0.0
        try:
            while True:
                elapsed = time.monotonic() - start
                if elapsed >= settings.annotation_job_timeout_seconds:
                    db = SessionLocal()
                    try:
                        fail_job(
                            db,
                            job_id=claimed_job_id,
                            worker_id=worker_id,
                            error='job wall-clock timeout',
                            timed_out=True,
                        )
                        db.commit()
                    finally:
                        db.close()
                    break
                if elapsed - last_heartbeat >= settings.annotation_worker_heartbeat_seconds:
                    db = SessionLocal()
                    try:
                        cancelled = should_cancel_job(db, job_id=claimed_job_id, worker_id=worker_id)
                        if not cancelled:
                            heartbeat_job(
                                db,
                                job_id=claimed_job_id,
                                worker_id=worker_id,
                                lease_seconds=settings.annotation_worker_lease_seconds,
                            )
                        db.commit()
                    finally:
                        db.close()
                    last_heartbeat = elapsed
                    if cancelled:
                        break
                execute_generation_job(job_id=claimed_job_id, worker_id=worker_id)
                break
        except Exception:
            logger.exception('annotation worker loop error job_id=%s', claimed_job_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_worker_forever()


if __name__ == '__main__':
    main()
