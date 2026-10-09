import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone


class PartyType(models.TextChoices):
    INTERESTED = "INTERESTED", "Interessado"
    CLIENT = "CLIENT", "Cliente"


class PersonType(models.TextChoices):
    INDIVIDUAL = "INDIVIDUAL", "Pessoa física"
    COMPANY = "COMPANY", "Pessoa jurídica"


class ProposalStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Solicitada"
    BUDGETING = "BUDGETING", "Orçamento em elaboração"
    SENT = "SENT", "Enviada"
    ACCEPTED = "ACCEPTED", "Aceita"
    REJECTED = "REJECTED", "Recusada"
    CANCELLED = "CANCELLED", "Cancelada"


class ProposalContactContext(models.TextChoices):
    CLIENT = "CLIENT", "Cliente"
    WORK = "WORK", "Obra"


class InstallmentStatus(models.TextChoices):
    OPEN = "OPEN", "Em aberto"
    PAID = "PAID", "Quitada"
    CANCELLED = "CANCELLED", "Cancelada"
    UNKNOWN = "UNKNOWN", "Não informada"


class InstallmentSource(models.TextChoices):
    HUB = "HUB", "Hub"
    LEGACY_INSTALLMENTS = "LEGACY_INSTALLMENTS", "Pagamento parcelado"
    LEGACY_PAYMENT_PLAN = "LEGACY_PAYMENT_PLAN", "Plano de pagamento"


class CatalogOrigin(models.TextChoices):
    LEGACY = "LEGACY", "Legado"
    HUB = "HUB", "Hub"


class CommercialCatalog(models.Model):
    origin = models.CharField(
        max_length=10,
        choices=CatalogOrigin.choices,
        default=CatalogOrigin.LEGACY,
    )
    legacy_id = models.IntegerField(unique=True, blank=True, null=True)
    # Identidade de sincronização do registro no Access. Não é usada como FK.
    legacy_key = models.CharField(max_length=64, unique=True, blank=True, null=True)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    legacy_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("name", "id")

    def __str__(self):
        return self.name


class BusinessSegment(CommercialCatalog):
    class Meta(CommercialCatalog.Meta):
        db_table = "commercial_business_segments"
        verbose_name = "Ramo empresarial"
        verbose_name_plural = "Ramos empresariais"


class CompanyType(CommercialCatalog):
    class Meta(CommercialCatalog.Meta):
        db_table = "commercial_company_types"
        verbose_name = "Tipo de empresa"
        verbose_name_plural = "Tipos de empresa"


class Division(CommercialCatalog):
    code = models.CharField(max_length=20, unique=True)

    class Meta(CommercialCatalog.Meta):
        db_table = "commercial_divisions"
        verbose_name = "Divisão"
        verbose_name_plural = "Divisões"


class Department(CommercialCatalog):
    division = models.ForeignKey(
        Division,
        on_delete=models.PROTECT,
        related_name="departments",
        blank=True,
        null=True,
    )
    abbreviation = models.CharField(max_length=20, blank=True)

    class Meta(CommercialCatalog.Meta):
        db_table = "commercial_departments"
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"


class Project(CommercialCatalog):
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="projects",
        blank=True,
        null=True,
    )

    class Meta(CommercialCatalog.Meta):
        db_table = "commercial_projects"
        verbose_name = "Projeto/serviço"
        verbose_name_plural = "Projetos/serviços"


class ProposalType(CommercialCatalog):
    class Meta(CommercialCatalog.Meta):
        db_table = "commercial_proposal_types"
        verbose_name = "Tipo de proposta"
        verbose_name_plural = "Tipos de proposta"


class Party(models.Model):
    origin = models.CharField(
        max_length=10,
        choices=CatalogOrigin.choices,
        default=CatalogOrigin.HUB,
    )
    legacy_id = models.IntegerField(unique=True, blank=True, null=True)
    legacy_key = models.CharField(max_length=64, unique=True, blank=True, null=True)
    legacy_payload = models.JSONField(default=dict, blank=True)
    party_type = models.CharField(max_length=12, choices=PartyType.choices, default=PartyType.INTERESTED)
    person_type = models.CharField(max_length=12, choices=PersonType.choices)
    legal_name = models.CharField(max_length=180)
    trade_name = models.CharField(max_length=150, blank=True)
    # O legado contém documentos repetidos; identidade de sync é legacy_id/legacy_key.
    document = models.CharField(max_length=20, db_index=True, blank=True, null=True)
    state_registration = models.CharField(max_length=30, blank=True)
    business_segment = models.ForeignKey(
        BusinessSegment,
        on_delete=models.PROTECT,
        related_name="parties",
        blank=True,
        null=True,
    )
    company_type = models.ForeignKey(
        CompanyType,
        on_delete=models.PROTECT,
        related_name="parties",
        blank=True,
        null=True,
    )
    last_service = models.CharField(max_length=180, blank=True)
    referred_by = models.CharField(max_length=180, blank=True)
    website = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    converted_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="parties_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="parties_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commercial_parties"
        ordering = ("legal_name", "id")
        indexes = [models.Index(fields=("party_type", "is_active"))]

    def __str__(self):
        return self.trade_name or self.legal_name


class Address(models.Model):
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=80, default="Principal")
    postal_code = models.CharField(max_length=9)
    street = models.CharField(max_length=180)
    number = models.CharField(max_length=20)
    complement = models.CharField(max_length=120, blank=True)
    district = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commercial_addresses"
        ordering = ("-is_primary", "label", "id")

    def __str__(self):
        return f"{self.street}, {self.number} — {self.city}/{self.state}"


class Contact(models.Model):
    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=150)
    position = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    mobile = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commercial_contacts"
        ordering = ("-is_primary", "name", "id")

    def __str__(self):
        return self.name


class Proposal(models.Model):
    origin = models.CharField(
        max_length=10,
        choices=CatalogOrigin.choices,
        default=CatalogOrigin.HUB,
    )
    legacy_id = models.IntegerField(unique=True, blank=True, null=True)
    legacy_key = models.CharField(max_length=64, unique=True, blank=True, null=True)
    legacy_payload = models.JSONField(default=dict, blank=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    party = models.ForeignKey(Party, on_delete=models.PROTECT, related_name="proposals")
    work_address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name="proposals",
        blank=True,
        null=True,
    )
    requester_contact = models.ForeignKey(
        Contact,
        on_delete=models.PROTECT,
        related_name="proposals",
        blank=True,
        null=True,
    )
    entry_date = models.DateField()
    division = models.ForeignKey(
        Division,
        on_delete=models.PROTECT,
        related_name="proposals",
        blank=True,
        null=True,
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="proposals",
        blank=True,
        null=True,
    )
    work_name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    execution_days = models.PositiveIntegerField(blank=True, null=True)
    expected_delivery_date = models.DateField(blank=True, null=True)
    proposal_type = models.ForeignKey(
        ProposalType,
        on_delete=models.PROTECT,
        related_name="proposals",
        blank=True,
        null=True,
    )
    technical_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="technical_proposals",
        blank=True,
        null=True,
    )
    issuer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_proposals",
        blank=True,
        null=True,
    )
    issuer_name = models.CharField(max_length=180, blank=True)
    contract_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    additional_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=ProposalStatus.choices, default=ProposalStatus.REQUESTED)
    accepted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commercial_proposals"
        ordering = ("-entry_date", "-id")
        indexes = [models.Index(fields=("status", "entry_date")), models.Index(fields=("party", "status"))]

    def clean(self):
        errors = {}

        if self.work_address_id and self.party_id and self.work_address.party_id != self.party_id:
            errors["work_address"] = "O endereço deve pertencer ao interessado/cliente selecionado."

        if self.requester_contact_id and self.party_id and self.requester_contact.party_id != self.party_id:
            errors["requester_contact"] = "O contato deve pertencer ao interessado/cliente selecionado."

        if self.department_id and self.division_id and self.department.division_id not in (None, self.division_id):
            errors["department"] = "O departamento deve pertencer à divisão selecionada."

        if errors:
            raise ValidationError(errors)

    @property
    def total_value(self):
        return self.contract_value + self.additional_value

    @classmethod
    def current_pc_prefix(cls) -> str:
        return f"PC{timezone.localdate():%y}"

    @classmethod
    def normalize_pc_code(cls, value: object) -> str:
        return re.sub(r"\s+", "", str(value or "")).upper()

    @classmethod
    def last_current_year_code(cls) -> str | None:
        prefix = cls.current_pc_prefix()

        return (
            cls.objects
            .filter(code__regex=rf"^{prefix}\d{{3}}$")
            .order_by("-code")
            .values_list("code", flat=True)
            .first()
        )

    @classmethod
    def next_available_code(cls) -> str:
        prefix = cls.current_pc_prefix()
        last_code = cls.last_current_year_code()
        current_sequence = int(last_code[-3:]) if last_code else 0
        next_sequence = current_sequence + 1

        if next_sequence > 999:
            raise ValidationError(
                {
                    "code": (
                        "A sequência anual de PCs atingiu o limite de 999 "
                        f"para o prefixo {prefix}."
                    )
                }
            )

        return f"{prefix}{next_sequence:03d}"

    @classmethod
    def validate_new_code(cls, value: object) -> str:
        code = cls.normalize_pc_code(value)
        prefix = cls.current_pc_prefix()

        if not re.fullmatch(rf"{prefix}\d{{3}}", code):
            raise ValidationError(
                {
                    "code": (
                        "O PC deve seguir o formato "
                        f"{prefix}NNN para o ano atual."
                    )
                }
            )

        if cls.objects.filter(code=code).exists():
            raise ValidationError({"code": f"O PC {code} já existe."})

        next_code = cls.next_available_code()

        if code < next_code:
            raise ValidationError(
                {
                    "code": (
                        f"O PC {code} é anterior ao próximo PC disponível "
                        f"({next_code})."
                    )
                }
            )

        return code

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        if not is_new:
            if self.origin == CatalogOrigin.HUB and self.pk:
                original_code = (
                    type(self).objects
                    .filter(pk=self.pk)
                    .values_list("code", flat=True)
                    .first()
                )

                if original_code and self.code != original_code:
                    raise ValidationError(
                        {
                            "code": (
                                "O PC de uma proposta já cadastrada não pode ser alterado."
                            )
                        }
                    )

            self.full_clean()
            return super().save(*args, **kwargs)

        # A importação do legado preserva o PC original, inclusive anos anteriores.
        if self.origin != CatalogOrigin.HUB:
            self.full_clean()
            return super().save(*args, **kwargs)

        try:
            with transaction.atomic():
                # O banco já possui propostas importadas. Travar sempre o mesmo
                # registro serializa a escolha do próximo PC entre requisições.
                (
                    type(self).objects
                    .select_for_update()
                    .order_by("id")
                    .first()
                )

                if self.code:
                    self.code = type(self).validate_new_code(self.code)
                else:
                    self.code = type(self).next_available_code()

                self.full_clean()
                return super().save(*args, **kwargs)

        except IntegrityError as error:
            raise ValidationError(
                {"code": "O PC informado já existe. Consulte o próximo PC disponível."}
            ) from error


class ProposalRequestedService(models.Model):
    proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="requested_services",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="proposal_items",
    )
    area = models.DecimalField(max_digits=14, decimal_places=4, blank=True, null=True)
    proposed_value = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    contracted_value = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    position = models.CharField(max_length=80, blank=True)
    completion_date = models.DateField(blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    origin = models.CharField(max_length=10, choices=CatalogOrigin.choices, default=CatalogOrigin.HUB)
    legacy_id = models.IntegerField(unique=True, blank=True, null=True)
    legacy_key = models.CharField(max_length=64, unique=True, blank=True, null=True)
    legacy_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commercial_proposal_requested_services"
        ordering = ("sort_order", "id")


class ProposalContact(models.Model):
    proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="proposal_contacts",
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.PROTECT,
        related_name="proposal_links",
    )
    context = models.CharField(
        max_length=10,
        choices=ProposalContactContext.choices,
        default=ProposalContactContext.CLIENT,
    )
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    origin = models.CharField(max_length=10, choices=CatalogOrigin.choices, default=CatalogOrigin.HUB)
    legacy_key = models.CharField(max_length=64, unique=True, blank=True, null=True)
    legacy_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commercial_proposal_contacts"
        ordering = ("context", "sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("proposal", "contact", "context"),
                name="commercial_unique_contact_per_context",
            )
        ]

    def clean(self):
        if self.proposal_id and self.contact_id and self.contact.party_id != self.proposal.party_id:
            raise ValidationError({"contact": "O contato deve pertencer ao cliente/interessado da proposta."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ProposalInstallment(models.Model):
    proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="installments",
    )
    label = models.CharField(max_length=30)
    sequence = models.PositiveIntegerField(blank=True, null=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    due_date = models.DateField(blank=True, null=True)
    paid_at = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=12,
        choices=InstallmentStatus.choices,
        default=InstallmentStatus.UNKNOWN,
    )
    source = models.CharField(
        max_length=24,
        choices=InstallmentSource.choices,
        default=InstallmentSource.HUB,
    )
    legacy_id = models.IntegerField(blank=True, null=True)
    legacy_key = models.CharField(max_length=64, unique=True, blank=True, null=True)
    legacy_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commercial_proposal_installments"
        ordering = ("sequence", "due_date", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("proposal", "sequence"),
                condition=models.Q(sequence__isnull=False),
                name="commercial_unique_installment_sequence",
            )
        ]
