from __future__ import annotations

from app.models import User


def ensure_active_user(user: User) -> User:
    if not user.is_active:
        raise PermissionError('账号已停用')
    return user


def require_roles(user: User, *roles: str) -> User:
    ensure_active_user(user)
    if roles and user.role not in roles:
        raise PermissionError('无权限执行该操作')
    return user
