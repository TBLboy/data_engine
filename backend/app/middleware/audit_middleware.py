from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.db import SessionLocal
from app.models.audit import AuditEvent


SKIP_PATHS = {'/api/health', '/api/auth/session'}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000)

        path = request.url.path
        if path in SKIP_PATHS:
            return response

        try:
            self._write_audit(request, response, duration_ms)
        except Exception:
            pass

        return response

    @staticmethod
    def _write_audit(request: Request, response: Response, duration_ms: int) -> None:
        db = SessionLocal()
        try:
            user_id = ''
            user_name = ''
            user_obj = getattr(request.state, 'user', None)
            if user_obj:
                user_id = getattr(user_obj, 'id', '')
                user_name = getattr(user_obj, 'username', '')

            ip = request.client.host if request.client else ''
            ua = request.headers.get('user-agent', '')[:256]
            method = request.method
            path = request.url.path
            status = response.status_code
            severity = 'error' if status >= 400 else 'info'

            ts = int(datetime.utcnow().timestamp())
            audit_id = f'audit_api_{ts}_{user_id or "anon"}'

            audit = AuditEvent(
                id=audit_id,
                operator=user_name or 'anonymous',
                action=f'{method} {path}',
                target=path,
                detail=f'status={status} duration_ms={duration_ms}',
                time=datetime.utcnow(),
                event_type='api_request',
                severity=severity,
                operator_id=user_id or None,
                ip_address=ip,
                user_agent=ua,
                duration_ms=duration_ms,
            )
            db.add(audit)
            db.commit()
        finally:
            db.close()
