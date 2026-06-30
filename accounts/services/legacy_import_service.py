from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models.choices import UserType

User = get_user_model()


class LegacyImportService:
    """
    Imports basic identity from Access.

    Access is used only to validate legacy username/password
    and provide basic user information.

    It does not provide:
    - groups
    - user type rules
    - modules
    - permissions
    """

    @transaction.atomic
    def import_user_from_legacy_payload(self, payload: dict, raw_password: str):
        legacy_user = payload.get("legacy_user") or {}

        username = (
            legacy_user.get("username")
            or legacy_user.get("legacy_username")
        )

        if not username:
            raise ValueError(
                f"Legacy payload does not contain a username. Payload: {payload}"
            )

        full_name = legacy_user.get("full_name") or username
        email = legacy_user.get("email") or self._build_placeholder_email(username)

        last_legacy_login_at = self._parse_datetime(
            legacy_user.get("last_legacy_login_at")
        )

        password_hash = make_password(raw_password)

        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                "name": full_name,
                "email": email,
                "password": password_hash,
                "user_type": UserType.EMPLOYEE,
                "group": None,
                "user_origin": User.LEGACY_ORIGIN,
                "legacy_username": username,
                "legacy_group_name": "",
                "is_migrated_from_access": True,
                "last_legacy_login_at": last_legacy_login_at or timezone.now(),
                "last_legacy_sync_at": timezone.now(),
                "legacy_sync_enabled": False,
                "is_active": True,
            },
        )

        return user

    def _build_placeholder_email(self, username: str):
        return f"{username}@legacy.local"

    def _parse_datetime(self, value):
        if not value:
            return None

        parsed = parse_datetime(value)

        if not parsed:
            return None

        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed)

        return parsed