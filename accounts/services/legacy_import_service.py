from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import UserGroup
from accounts.models.choices import UserType

User = get_user_model()


class LegacyImportService:
    """Import authenticated Access users, including their legacy group."""

    @staticmethod
    def _legacy_group_name(payload):
        groups = payload.get("groups") or []
        for group in groups:
            if isinstance(group, dict):
                name = group.get("legacy_name") or group.get("name")
            elif isinstance(group, str):
                name = group
            else:
                continue
            if name and str(name).strip():
                return str(name).strip()
        return ""

    @staticmethod
    def _resolve_group(group_name):
        if not group_name:
            return None
        # Reuse the existing permissions group (case-insensitive) whenever possible.
        # Unknown Access groups are created without permissions; never assign
        # an unrelated privileged group as a fallback.
        group = UserGroup.objects.filter(
            user_type=UserType.EMPLOYEE, name__iexact=group_name
        ).first()
        if group:
            return group
        group, _ = UserGroup.objects.get_or_create(
            user_type=UserType.EMPLOYEE,
            name=group_name[:50],
            defaults={"description": "Grupo importado do Access (sem permissões automáticas)."},
        )
        return group

    @transaction.atomic
    def synchronize_existing_user_group(self, user, payload):
        if (
                user.user_origin != User.LEGACY_ORIGIN
                and not user.is_migrated_from_access
        ):
            return False

        group_name = self._legacy_group_name(payload)

        if not group_name:
            return False

        update_fields = []

        if user.legacy_group_name != group_name:
            user.legacy_group_name = group_name
            update_fields.append("legacy_group_name")

        if not user.group_id:
            user.group = self._resolve_group(group_name)
            update_fields.append("group")

        if not update_fields:
            return False

        user.last_legacy_sync_at = timezone.now()
        update_fields.extend([
            "last_legacy_sync_at",
            "updated_at",
        ])

        user.save(update_fields=update_fields)
        return True

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

        group_name = self._legacy_group_name(payload)
        group = self._resolve_group(group_name)
        password_hash = make_password(raw_password)

        user, _ = User.objects.update_or_create(
            username=username,
            defaults={
                "name": full_name,
                "email": email,
                "password": password_hash,
                "user_type": UserType.EMPLOYEE,
                "group": group,
                "user_origin": User.LEGACY_ORIGIN,
                "legacy_username": username,
                "legacy_group_name": group_name,
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