from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models.choices import UserType


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("user_type", UserType.EMPLOYEE)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return super().create_superuser(
            username=username,
            email=email,
            password=password,
            **extra_fields,
        )


class User(AbstractUser):
    LEGACY_ORIGIN = "legacy"
    DJANGO_ORIGIN = "django"

    USER_ORIGIN_CHOICES = [
        (LEGACY_ORIGIN, "Imported from Access"),
        (DJANGO_ORIGIN, "Created in Django"),
    ]

    id = models.BigAutoField(
        primary_key=True,
        db_column="id_usuario",
    )

    name = models.CharField(
        max_length=150,
        db_column="nome",
    )

    email = models.EmailField(
        unique=True,
    )

    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.EMPLOYEE,
        db_column="tipo_usuario",
    )

    group = models.ForeignKey(
        "accounts.UserGroup",
        on_delete=models.PROTECT,
        db_column="id_grupo",
        related_name="users",
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
        db_column="ativo",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column="criado_em",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        db_column="atualizado_em",
    )

    user_origin = models.CharField(
        max_length=20,
        choices=USER_ORIGIN_CHOICES,
        default=DJANGO_ORIGIN,
    )

    legacy_id = models.IntegerField(
        unique=True,
        blank=True,
        null=True,
    )

    legacy_username = models.CharField(
        max_length=50,
        blank=True,
    )

    legacy_group_name = models.CharField(
        max_length=100,
        blank=True,
    )

    is_migrated_from_access = models.BooleanField(
        default=False,
    )

    migrated_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    last_legacy_login_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    last_legacy_sync_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    legacy_sync_enabled = models.BooleanField(
        default=False,
    )

    approval_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    can_access_dashboard = models.BooleanField(
        default=False,
    )

    can_access_deductibles = models.BooleanField(
        default=False,
    )

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["name", "email"]

    class Meta:
        db_table = "usuarios"
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["name"]

    def __str__(self):
        return self.name or self.username

    def clean(self):
        super().clean()

        if self.group and self.group.user_type != self.user_type:
            raise ValidationError({
                "group": "The selected group does not belong to this user type."
            })

    def save(self, *args, **kwargs):
        self.full_clean()

        if self.is_migrated_from_access and not self.migrated_at:
            self.migrated_at = timezone.now()

        super().save(*args, **kwargs)

    @property
    def group_name(self):
        if not self.group:
            return None

        return self.group.name

    def get_permission_codes(self):
        if not self.group:
            return []

        return list(
            self.group.group_permissions.filter(
                is_active=True,
                permission__is_active=True,
            )
            .values_list("permission__code", flat=True)
            .order_by("permission__code")
        )

    def has_permission_code(self, code: str) -> bool:
        if not self.group:
            return False

        return self.group.group_permissions.filter(
            is_active=True,
            permission__is_active=True,
            permission__code=code,
        ).exists()