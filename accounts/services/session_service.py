from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import UserSession

User = get_user_model()


def get_end_of_current_day():
    tz = ZoneInfo(settings.TIME_ZONE)

    now_local = timezone.now().astimezone(tz)
    tomorrow = now_local.date() + timedelta(days=1)

    end_of_day_local = datetime.combine(
        tomorrow,
        time.min,
        tzinfo=tz,
    )

    return end_of_day_local.astimezone(UTC)


def build_session_payload(session: UserSession) -> dict:
    return {
        "id": str(session.id),
        "expira_em": timezone.localtime(session.expires_at).isoformat(),
        "inatividade_minutos": settings.SESSION_IDLE_TIMEOUT_MINUTES,
    }


def create_user_session(user) -> UserSession:
    return UserSession.objects.create(
        user=user,
        expires_at=get_end_of_current_day(),
    )


def _get_remaining_session_lifetime(session: UserSession) -> timedelta:
    remaining = session.expires_at - timezone.now()

    if remaining <= timedelta(seconds=0):
        return timedelta(seconds=1)

    return remaining


def _get_access_lifetime(session: UserSession) -> timedelta:
    remaining = _get_remaining_session_lifetime(session)

    return min(
        api_settings.ACCESS_TOKEN_LIFETIME,
        remaining,
    )


def build_tokens_for_session(user, session: UserSession) -> dict:
    now = timezone.now()

    refresh = RefreshToken.for_user(user)

    refresh["sid"] = str(session.id)
    refresh["session_expires_at"] = int(session.expires_at.timestamp())
    refresh.set_exp(
        from_time=now,
        lifetime=_get_remaining_session_lifetime(session),
    )

    access = refresh.access_token

    access["sid"] = str(session.id)
    access["session_expires_at"] = int(session.expires_at.timestamp())
    access.set_exp(
        from_time=now,
        lifetime=_get_access_lifetime(session),
    )

    session.refresh_jti = str(refresh["jti"])
    session.save(update_fields=["refresh_jti"])

    return {
        "access_token": str(access),
        "refresh_token": str(refresh),
        "token_type": "bearer",
        "sessao": build_session_payload(session),
    }


def validate_user_session(
    user,
    token,
    update_activity: bool = True,
) -> UserSession:
    session_id = token.get("sid")

    if not session_id:
        raise AuthenticationFailed(
            "Sessão inválida.",
            code="invalid_session",
        )

    try:
        session = UserSession.objects.get(
            id=session_id,
            user=user,
            is_active=True,
        )
    except UserSession.DoesNotExist:
        raise AuthenticationFailed(
            "Sessão encerrada.",
            code="session_closed",
        )

    now = timezone.now()

    if session.expires_at <= now:
        session.close(UserSession.EndReason.END_OF_DAY)

        raise AuthenticationFailed(
            "Sessão expirada no fim do dia.",
            code="session_expired_end_of_day",
        )

    idle_limit = timedelta(
        minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES,
    )

    if session.last_activity_at + idle_limit <= now:
        session.close(UserSession.EndReason.IDLE)

        raise AuthenticationFailed(
            "Sessão expirada por inatividade.",
            code="session_expired_idle",
        )

    if update_activity:
        session.last_activity_at = now
        session.save(update_fields=["last_activity_at"])

    return session


def build_access_from_refresh_token(refresh_token: str) -> dict:
    try:
        refresh = RefreshToken(refresh_token)
    except TokenError:
        raise AuthenticationFailed(
            "Refresh token inválido ou expirado.",
            code="invalid_refresh_token",
        )

    user_id = refresh.get(api_settings.USER_ID_CLAIM)

    if not user_id:
        raise AuthenticationFailed(
            "Token sem usuário.",
            code="invalid_token_user",
        )

    try:
        user = User.objects.get(**{api_settings.USER_ID_FIELD: user_id})
    except User.DoesNotExist:
        raise AuthenticationFailed(
            "Usuário não encontrado.",
            code="user_not_found",
        )

    if not user.is_active:
        raise AuthenticationFailed(
            "Usuário inativo.",
            code="user_inactive",
        )

    session = validate_user_session(
        user=user,
        token=refresh,
        update_activity=True,
    )

    access = refresh.access_token

    access["sid"] = str(session.id)
    access["session_expires_at"] = int(session.expires_at.timestamp())
    access.set_exp(
        from_time=timezone.now(),
        lifetime=_get_access_lifetime(session),
    )

    return {
        "access_token": str(access),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "sessao": build_session_payload(session),
    }


def close_user_session(user, session_id, reason: str):
    if not session_id:
        return

    UserSession.objects.filter(
        id=session_id,
        user=user,
        is_active=True,
    ).update(
        is_active=False,
        ended_at=timezone.now(),
        end_reason=reason,
    )