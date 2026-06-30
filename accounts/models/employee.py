from django.core.exceptions import ValidationError
from django.db import models

from accounts.models.choices import EmployeeGroup, UserType


class Employee(models.Model):
    id = models.BigAutoField(
        primary_key=True,
        db_column="id_colaborador",
    )

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        db_column="id_usuario",
        related_name="employee_profile",
    )

    employee_subgroup = models.CharField(
        max_length=30,
        choices=EmployeeGroup.choices,
        db_column="subgrupo_colaborador",
    )

    department = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_column="departamento",
    )

    position = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_column="cargo",
    )

    is_active = models.BooleanField(
        default=True,
        db_column="ativo",
    )

    class Meta:
        db_table = "colaboradores"
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ["user__name"]

    def __str__(self):
        return self.user.name

    def clean(self):
        super().clean()

        if self.user.user_type != UserType.EMPLOYEE:
            raise ValidationError({
                "user": "The linked user must be of type COLABORADOR."
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)