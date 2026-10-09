from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q

from rest_framework import serializers

from commercial.models import (
    Address,
    BusinessSegment,
    CompanyType,
    Contact,
    Department,
    Division,
    Party,
    PartyType,
    PersonType,
    Proposal,
    ProposalContact,
    ProposalInstallment,
    ProposalRequestedService,
    ProposalType,
    Project,
)
from commercial.services.parties import (
    create_client_full,
    update_client_full,
)


User = get_user_model()


def _only_digits(value: object) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def _is_valid_cpf(value: str) -> bool:
    digits = _only_digits(value)

    if len(digits) != 11 or len(set(digits)) == 1:
        return False

    numbers = [int(char) for char in digits]

    total = sum(numbers[index] * (10 - index) for index in range(9))
    remainder = total % 11
    first_digit = 0 if remainder < 2 else 11 - remainder

    if numbers[9] != first_digit:
        return False

    total = sum(numbers[index] * (11 - index) for index in range(10))
    remainder = total % 11
    second_digit = 0 if remainder < 2 else 11 - remainder

    return numbers[10] == second_digit


def _is_valid_cnpj(value: str) -> bool:
    digits = _only_digits(value)

    if len(digits) != 14 or len(set(digits)) == 1:
        return False

    numbers = [int(char) for char in digits]

    first_weights = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    total = sum(number * weight for number, weight in zip(numbers[:12], first_weights))
    remainder = total % 11
    first_digit = 0 if remainder < 2 else 11 - remainder

    if numbers[12] != first_digit:
        return False

    second_weights = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    total = sum(number * weight for number, weight in zip(numbers[:13], second_weights))
    remainder = total % 11
    second_digit = 0 if remainder < 2 else 11 - remainder

    return numbers[13] == second_digit



class CommercialCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        fields = (
            "id",
            "legacy_id",
            "legacy_key",
            "name",
            "origin",
            "is_active",
        )
        read_only_fields = fields


class BusinessSegmentSerializer(CommercialCatalogSerializer):
    class Meta(CommercialCatalogSerializer.Meta):
        model = BusinessSegment


class CompanyTypeSerializer(CommercialCatalogSerializer):
    class Meta(CommercialCatalogSerializer.Meta):
        model = CompanyType


class DivisionSerializer(CommercialCatalogSerializer):
    class Meta(CommercialCatalogSerializer.Meta):
        model = Division
        fields = CommercialCatalogSerializer.Meta.fields + ("code",)


class DepartmentSerializer(CommercialCatalogSerializer):
    division_name = serializers.CharField(source="division.name", read_only=True)
    division_code = serializers.CharField(source="division.code", read_only=True)

    class Meta(CommercialCatalogSerializer.Meta):
        model = Department
        fields = CommercialCatalogSerializer.Meta.fields + (
            "division",
            "division_name",
            "division_code",
            "abbreviation",
        )


class ProjectSerializer(CommercialCatalogSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta(CommercialCatalogSerializer.Meta):
        model = Project
        fields = CommercialCatalogSerializer.Meta.fields + (
            "department",
            "department_name",
        )


class ProposalTypeSerializer(CommercialCatalogSerializer):
    class Meta(CommercialCatalogSerializer.Meta):
        model = ProposalType


class PartyAutocompleteSerializer(serializers.ModelSerializer):
    label = serializers.CharField(
        source="__str__",
        read_only=True,
    )
    party_type_label = serializers.CharField(
        source="get_party_type_display",
        read_only=True,
    )

    class Meta:
        model = Party
        fields = (
            "id",
            "label",
            "legal_name",
            "trade_name",
            "document",
            "party_type",
            "party_type_label",
        )


class AddressSerializer(serializers.ModelSerializer):
    label_display = serializers.CharField(
        source="__str__",
        read_only=True,
    )

    class Meta:
        model = Address
        fields = "__all__"


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = "__all__"


class PartySerializer(serializers.ModelSerializer):
    business_segment = serializers.PrimaryKeyRelatedField(
        queryset=BusinessSegment.objects.filter(
            is_active=True
        ),
        allow_null=True,
        required=False,
    )

    company_type = serializers.PrimaryKeyRelatedField(
        queryset=CompanyType.objects.filter(
            is_active=True
        ),
        allow_null=True,
        required=False,
    )

    addresses = AddressSerializer(
        many=True,
        read_only=True,
    )

    contacts = ContactSerializer(
        many=True,
        read_only=True,
    )

    business_segment_name = serializers.CharField(
        source="business_segment.name",
        read_only=True,
    )

    company_type_name = serializers.CharField(
        source="company_type.name",
        read_only=True,
    )

    class Meta:
        model = Party
        fields = "__all__"

        read_only_fields = (
            "origin",
            "legacy_id",
            "legacy_key",
            "legacy_payload",
            "converted_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        instance = self.instance

        person_type = attrs.get(
            "person_type",
            getattr(instance, "person_type", None),
        )

        business_segment = attrs.get(
            "business_segment",
            getattr(instance, "business_segment", None),
        )

        company_type = attrs.get(
            "company_type",
            getattr(instance, "company_type", None),
        )

        person_type_value = (
            person_type.value
            if hasattr(person_type, "value")
            else person_type
        )

        if (
            person_type_value == PersonType.INDIVIDUAL.value
            and (
                business_segment is not None
                or company_type is not None
            )
        ):
            raise serializers.ValidationError(
                {
                    "person_type": (
                        "Pessoa física não pode possuir "
                        "ramo empresarial ou tipo de empresa."
                    )
                }
            )

        return attrs


class ClientAddressWriteSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(
        required=False,
    )

    class Meta:
        model = Address
        fields = (
            "id",
            "label",
            "postal_code",
            "street",
            "number",
            "complement",
            "district",
            "city",
            "state",
            "is_primary",
            "is_active",
        )
        extra_kwargs = {
            "postal_code": {"required": True, "allow_blank": False},
            "street": {"required": True, "allow_blank": False},
            "number": {"required": True, "allow_blank": False},
            "complement": {"required": False, "allow_blank": True},
            "district": {"required": True, "allow_blank": False},
            "city": {"required": True, "allow_blank": False},
            "state": {"required": True, "allow_blank": False},
        }

    def validate_postal_code(self, value):
        digits = _only_digits(value)
        if len(digits) != 8:
            raise serializers.ValidationError("Informe um CEP válido com 8 dígitos.")
        return digits


class ClientContactWriteSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(
        required=False,
    )

    class Meta:
        model = Contact
        fields = (
            "id",
            "name",
            "position",
            "phone",
            "mobile",
            "email",
            "is_primary",
            "is_active",
        )
        extra_kwargs = {
            "phone": {"required": True, "allow_blank": False},
            "mobile": {"required": True, "allow_blank": False},
            "email": {"required": True, "allow_blank": False},
        }

    def validate_phone(self, value):
        digits = _only_digits(value)
        if len(digits) not in (10, 11):
            raise serializers.ValidationError("Informe um telefone válido com DDD.")
        return digits

    def validate_mobile(self, value):
        digits = _only_digits(value)
        if len(digits) != 11 or digits[2] != "9":
            raise serializers.ValidationError("Informe um celular válido com DDD.")
        return digits


class ClientFullSerializer(serializers.ModelSerializer):
    """
    Serializer de leitura/escrita do cadastro completo de cliente.

    - Party + endereços + contatos são persistidos em uma única transação.
    - `party_type` é sempre CLIENT neste endpoint.
    - Dados importados do Access que ainda não viraram Address/Contact
      são expostos através de `legacy_address_fallback` e
      `legacy_contact_fallback`.
    """

    legal_name = serializers.CharField(
        required=True,
        allow_blank=False,
    )

    document = serializers.CharField(
        required=True,
        allow_blank=False,
    )

    business_segment = serializers.PrimaryKeyRelatedField(
        queryset=BusinessSegment.objects.filter(
            is_active=True
        ),
        allow_null=False,
        required=True,
    )

    company_type = serializers.PrimaryKeyRelatedField(
        queryset=CompanyType.objects.filter(
            is_active=True
        ),
        allow_null=False,
        required=True,
    )

    business_segment_name = serializers.CharField(
        source="business_segment.name",
        read_only=True,
    )

    company_type_name = serializers.CharField(
        source="company_type.name",
        read_only=True,
    )

    addresses = ClientAddressWriteSerializer(
        many=True,
        required=True,
        allow_empty=False,
    )

    contacts = ClientContactWriteSerializer(
        many=True,
        required=True,
        allow_empty=False,
    )

    legacy_address_fallback = serializers.SerializerMethodField()
    legacy_contact_fallback = serializers.SerializerMethodField()

    class Meta:
        model = Party
        fields = (
            "id",
            "origin",
            "legacy_id",
            "legacy_key",
            "party_type",
            "person_type",
            "legal_name",
            "trade_name",
            "document",
            "state_registration",
            "business_segment",
            "business_segment_name",
            "company_type",
            "company_type_name",
            "last_service",
            "referred_by",
            "website",
            "notes",
            "converted_at",
            "is_active",
            "addresses",
            "contacts",
            "legacy_address_fallback",
            "legacy_contact_fallback",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "origin",
            "legacy_id",
            "legacy_key",
            "party_type",
            "converted_at",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
            "legacy_address_fallback",
            "legacy_contact_fallback",
        )

    def get_legacy_address_fallback(self, instance):
        if instance.addresses.filter(
            is_active=True
        ).exists():
            return None

        payload = instance.legacy_payload or {}

        values = {
            "postal_code": str(
                payload.get("postal_code") or ""
            ).strip(),
            "street": str(
                payload.get("address") or ""
            ).strip(),
            "number": "",
            "complement": "",
            "district": str(
                payload.get("district") or ""
            ).strip(),
            "city": str(
                payload.get("city") or ""
            ).strip(),
            "state": str(
                payload.get("state") or ""
            ).strip(),
        }

        if not any(values.values()):
            return None

        return values

    def get_legacy_contact_fallback(self, instance):
        if instance.contacts.filter(
            is_active=True
        ).exists():
            return None

        payload = instance.legacy_payload or {}

        phone = str(
            payload.get("phone") or ""
        ).strip()

        email = str(
            payload.get("email") or ""
        ).strip()

        if not phone and not email:
            return None

        return {
            "phone": phone,
            "mobile": "",
            "email": email,
        }

    def validate(self, attrs):
        instance = self.instance

        person_type = attrs.get(
            "person_type",
            getattr(instance, "person_type", None),
        )

        document = attrs.get(
            "document",
            getattr(instance, "document", None),
        )

        document_digits = _only_digits(document)
        errors = {}

        business_segment = attrs.get(
            "business_segment",
            getattr(instance, "business_segment", None),
        )
        company_type = attrs.get(
            "company_type",
            getattr(instance, "company_type", None),
        )

        if business_segment is None:
            errors["business_segment"] = "Ramo empresarial é obrigatório."

        if company_type is None:
            errors["company_type"] = "Tipo de empresa é obrigatório."

        # Em PATCH, endereços/contatos podem ser omitidos somente quando o
        # registro já possui dados ativos completos.
        if instance is not None and "addresses" not in attrs:
            if not instance.addresses.filter(is_active=True).exists():
                errors["addresses"] = "Endereço é obrigatório."

        if instance is not None and "contacts" not in attrs:
            if not instance.contacts.filter(is_active=True).exists():
                errors["contacts"] = "Telefone, celular e e-mail são obrigatórios."

        if person_type == PersonType.INDIVIDUAL:
            if not document_digits:
                errors["document"] = "CPF é obrigatório para pessoa física."
            elif not _is_valid_cpf(document_digits):
                errors["document"] = "CPF inválido."

        elif person_type == PersonType.COMPANY:
            if not document_digits:
                errors["document"] = "CNPJ é obrigatório para pessoa jurídica."
            elif not _is_valid_cnpj(document_digits):
                errors["document"] = "CNPJ inválido."

        else:
            errors["person_type"] = "Tipo de pessoa inválido."

        if errors:
            raise serializers.ValidationError(errors)

        attrs["document"] = document_digits
        attrs["party_type"] = PartyType.CLIENT

        return attrs

    def create(self, validated_data):
        request = self.context["request"]

        return create_client_full(
            validated_data=validated_data,
            user=request.user,
        )

    def update(self, instance, validated_data):
        request = self.context["request"]

        return update_client_full(
            instance=instance,
            validated_data=validated_data,
            user=request.user,
        )


class ProposalRequestedServiceSerializer(serializers.ModelSerializer):
    project_summary = ProjectSerializer(source="project", read_only=True)

    class Meta:
        model = ProposalRequestedService
        fields = "__all__"
        read_only_fields = (
            "origin",
            "legacy_id",
            "legacy_key",
            "legacy_payload",
            "created_at",
            "updated_at",
        )


class ProposalContactSerializer(serializers.ModelSerializer):
    contact_summary = ContactSerializer(source="contact", read_only=True)
    context_label = serializers.CharField(source="get_context_display", read_only=True)

    class Meta:
        model = ProposalContact
        fields = "__all__"
        read_only_fields = (
            "origin",
            "legacy_key",
            "legacy_payload",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        instance = self.instance
        proposal = attrs.get("proposal", getattr(instance, "proposal", None))
        contact = attrs.get("contact", getattr(instance, "contact", None))

        if proposal and contact and contact.party_id != proposal.party_id:
            raise serializers.ValidationError(
                {"contact": "O contato deve pertencer ao cliente/interessado da proposta."}
            )

        return attrs


class ProposalInstallmentSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    source_label = serializers.CharField(source="get_source_display", read_only=True)

    class Meta:
        model = ProposalInstallment
        fields = "__all__"
        read_only_fields = (
            "source",
            "legacy_id",
            "legacy_key",
            "legacy_payload",
            "created_at",
            "updated_at",
        )
class ProposalWorkAutocompleteSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="work_name", read_only=True)
    client_id = serializers.IntegerField(source="party_id", read_only=True)
    cost_center = serializers.CharField(source="code", read_only=True)
    work_address_id = serializers.IntegerField(read_only=True, allow_null=True)
    address = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = (
            "id",
            "name",
            "client_id",
            "cost_center",
            "work_address_id",
            "address",
        )
        read_only_fields = fields

    def get_address(self, obj):
        if obj.work_address_id is None:
            return ""

        return str(obj.work_address)


class ProposalSerializer(serializers.ModelSerializer):
    code = serializers.CharField(required=False, allow_blank=True)

    client = serializers.SerializerMethodField()
    client_id = serializers.PrimaryKeyRelatedField(
        source="party",
        queryset=Party.objects.filter(is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )
    client_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=180,
    )

    division = DivisionSerializer(read_only=True)
    division_id = serializers.PrimaryKeyRelatedField(
        source="division",
        queryset=Division.objects.filter(is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )

    department = DepartmentSerializer(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        source="department",
        queryset=Department.objects.filter(is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )

    proposal_type = ProposalTypeSerializer(read_only=True)
    proposal_type_id = serializers.PrimaryKeyRelatedField(
        source="proposal_type",
        queryset=ProposalType.objects.filter(is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )

    issuer = serializers.SerializerMethodField()
    issuer_id = serializers.PrimaryKeyRelatedField(
        source="issuer",
        queryset=User.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    issuer_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=180,
    )

    requester = ContactSerializer(source="requester_contact", read_only=True)
    requester_id = serializers.PrimaryKeyRelatedField(
        source="requester_contact",
        queryset=Contact.objects.filter(is_active=True),
        write_only=True,
        required=False,
        allow_null=True,
    )
    requester_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=150,
    )

    technical_responsible = serializers.SerializerMethodField()
    technical_responsible_id = serializers.PrimaryKeyRelatedField(
        source="technical_responsible",
        queryset=User.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    work = serializers.SerializerMethodField()
    work_id = serializers.IntegerField(
        write_only=True,
        required=False,
        allow_null=True,
    )
    work_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        max_length=180,
    )

    client_address = serializers.SerializerMethodField()
    work_address = serializers.SerializerMethodField()

    execution_deadline = serializers.IntegerField(
        source="execution_days",
        required=False,
        allow_null=True,
    )
    delivery_date = serializers.DateField(
        source="expected_delivery_date",
        required=False,
        allow_null=True,
    )

    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    requested_services = ProposalRequestedServiceSerializer(
        many=True,
        read_only=True,
    )
    proposal_contacts = ProposalContactSerializer(
        many=True,
        read_only=True,
    )
    installments = ProposalInstallmentSerializer(
        many=True,
        read_only=True,
    )
    total_value = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    contacts_count = serializers.SerializerMethodField()
    requested_services_count = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = (
            "id",
            "code",
            "entry_date",
            "status",
            "status_label",
            "client",
            "client_id",
            "client_name",
            "client_address",
            "work",
            "work_id",
            "work_name",
            "work_address",
            "division",
            "division_id",
            "department",
            "department_id",
            "proposal_type",
            "proposal_type_id",
            "issuer",
            "issuer_id",
            "issuer_name",
            "requester",
            "requester_id",
            "requester_name",
            "technical_responsible",
            "technical_responsible_id",
            "description",
            "execution_deadline",
            "delivery_date",
            "contract_value",
            "additional_value",
            "total_value",
            "accepted_at",
            "requested_services",
            "proposal_contacts",
            "installments",
            "contacts_count",
            "requested_services_count",
            "origin",
            "legacy_id",
            "legacy_key",
            "legacy_payload",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "accepted_at",
            "origin",
            "legacy_id",
            "legacy_key",
            "legacy_payload",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        try:
            with transaction.atomic():
                validated_data = self._prepare_relations(
                    validated_data,
                    instance=None,
                )
                return super().create(validated_data)
        except DjangoValidationError as error:
            self._raise_django_validation(error)

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                validated_data = self._prepare_relations(
                    validated_data,
                    instance=instance,
                )
                return super().update(
                    instance,
                    validated_data,
                )
        except DjangoValidationError as error:
            self._raise_django_validation(error)

    def validate_code(self, value):
        normalized = Proposal.normalize_pc_code(value)

        if self.instance is not None:
            if normalized != self.instance.code:
                raise serializers.ValidationError(
                    "O PC de uma proposta cadastrada não pode ser alterado."
                )

            return self.instance.code

        if not normalized:
            return ""

        try:
            return Proposal.validate_new_code(normalized)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                self._django_validation_message(
                    error,
                    "code",
                )
            ) from error

    def validate(self, attrs):
        instance = self.instance
        errors = {}

        client_name = str(
            attrs.get("client_name") or ""
        ).strip()

        requester_name = str(
            attrs.get("requester_name") or ""
        ).strip()

        issuer_name = str(
            attrs.get(
                "issuer_name",
                getattr(instance, "issuer_name", ""),
            )
            or ""
        ).strip()

        work_name = str(
            attrs.get(
                "work_name",
                getattr(instance, "work_name", ""),
            )
            or ""
        ).strip()

        party = attrs.get(
            "party",
            getattr(instance, "party", None),
        )

        division = attrs.get(
            "division",
            getattr(instance, "division", None),
        )

        department = attrs.get(
            "department",
            getattr(instance, "department", None),
        )

        issuer = attrs.get(
            "issuer",
            getattr(instance, "issuer", None),
        )

        work_id = attrs.get("work_id")

        if instance is None and party is None and not client_name:
            errors["client_id"] = (
                "Selecione um cliente/interessado ou informe um nome."
            )

        if (
            instance is not None
            and "party" in attrs
            and party is None
            and not client_name
        ):
            errors["client_id"] = (
                "Selecione um cliente/interessado ou informe um nome."
            )

        if instance is None and work_id is None and not work_name:
            errors["work_id"] = (
                "Selecione uma obra existente ou informe o nome da obra."
            )

        if (
            division
            and department
            and department.division_id not in (
                None,
                division.id,
            )
        ):
            errors["department_id"] = (
                "O departamento deve pertencer à divisão selecionada."
            )

        if issuer is not None:
            attrs["issuer_name"] = ""
        else:
            attrs["issuer_name"] = issuer_name

        attrs["client_name"] = client_name
        attrs["requester_name"] = requester_name

        if "work_name" in attrs:
            attrs["work_name"] = work_name

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def _prepare_relations(
        self,
        validated_data,
        *,
        instance,
    ):
        client_name = validated_data.pop(
            "client_name",
            "",
        ).strip()

        requester_name = validated_data.pop(
            "requester_name",
            "",
        ).strip()

        work_id = validated_data.pop(
            "work_id",
            None,
        )

        party = validated_data.get(
            "party",
            getattr(instance, "party", None),
        )

        if party is None and client_name:
            party = self._resolve_or_create_interested(
                client_name
            )
            validated_data["party"] = party

        if party is None:
            raise serializers.ValidationError(
                {
                    "client_id": (
                        "Selecione um cliente/interessado "
                        "ou informe um nome."
                    )
                }
            )

        requester_contact = validated_data.get(
            "requester_contact",
            getattr(
                instance,
                "requester_contact",
                None,
            ),
        )

        if requester_contact is None and requester_name:
            requester_contact = (
                self._resolve_or_create_contact(
                    party,
                    requester_name,
                )
            )
            validated_data[
                "requester_contact"
            ] = requester_contact

        if (
            requester_contact is not None
            and requester_contact.party_id
            != party.id
        ):
            raise serializers.ValidationError(
                {
                    "requester_id": (
                        "O contato deve pertencer ao "
                        "cliente/interessado selecionado."
                    )
                }
            )

        if work_id is not None:
            source_work = (
                Proposal.objects
                .select_related(
                    "work_address",
                    "party",
                )
                .filter(pk=work_id)
                .first()
            )

            if source_work is None:
                raise serializers.ValidationError(
                    {
                        "work_id": (
                            "A obra selecionada não foi encontrada."
                        )
                    }
                )

            if source_work.party_id != party.id:
                raise serializers.ValidationError(
                    {
                        "work_id": (
                            "A obra selecionada não pertence ao "
                            "cliente/interessado."
                        )
                    }
                )

            validated_data[
                "work_name"
            ] = source_work.work_name

            validated_data[
                "work_address"
            ] = source_work.work_address

        elif "work_name" in validated_data:
            free_work_name = str(
                validated_data.get(
                    "work_name"
                )
                or ""
            ).strip()

            if not free_work_name:
                if instance is None:
                    raise serializers.ValidationError(
                        {
                            "work_name": (
                                "Informe o nome da obra."
                            )
                        }
                    )
            else:
                validated_data[
                    "work_name"
                ] = free_work_name

                # Uma obra digitada livremente ainda não possui
                # endereço cadastrado/selecionado.
                validated_data[
                    "work_address"
                ] = None

        issuer = validated_data.get(
            "issuer",
            getattr(instance, "issuer", None),
        )

        if issuer is not None:
            validated_data[
                "issuer_name"
            ] = ""

        return validated_data

    @staticmethod
    def _resolve_or_create_interested(
        name,
    ):
        normalized_name = str(
            name or ""
        ).strip()

        if not normalized_name:
            raise serializers.ValidationError(
                {
                    "client_name": (
                        "Informe o nome do cliente/interessado."
                    )
                }
            )

        party = (
            Party.objects
            .filter(is_active=True)
            .filter(
                Q(
                    legal_name__iexact=
                    normalized_name
                )
                |
                Q(
                    trade_name__iexact=
                    normalized_name
                )
            )
            .order_by("id")
            .first()
        )

        if party is not None:
            return party

        return Party.objects.create(
            party_type=PartyType.INTERESTED,
            person_type=PersonType.COMPANY,
            legal_name=normalized_name[:180],
            is_active=True,
        )

    @staticmethod
    def _resolve_or_create_contact(
        party,
        name,
    ):
        normalized_name = str(
            name or ""
        ).strip()

        if not normalized_name:
            return None

        contact = (
            Contact.objects
            .filter(
                party=party,
                is_active=True,
                name__iexact=normalized_name,
            )
            .order_by("id")
            .first()
        )

        if contact is not None:
            return contact

        has_active_contact = (
            Contact.objects
            .filter(
                party=party,
                is_active=True,
            )
            .exists()
        )

        return Contact.objects.create(
            party=party,
            name=normalized_name[:150],
            is_primary=not has_active_contact,
            is_active=True,
        )

    def get_client(self, obj):
        party = obj.party
        label = str(party)

        return {
            "id": party.id,
            "name": label,
            "label": label,
            "legal_name": party.legal_name,
            "trade_name": party.trade_name,
            "document": party.document,
            "party_type": party.party_type,
            "party_type_label": (
                party.get_party_type_display()
            ),
        }

    def get_client_address(self, obj):
        addresses = [
            address
            for address
            in obj.party.addresses.all()
            if address.is_active
        ]

        if not addresses:
            return ""

        primary = next(
            (
                address
                for address
                in addresses
                if address.is_primary
            ),
            addresses[0],
        )

        return str(primary)

    def get_work_address(self, obj):
        if obj.work_address_id is None:
            return ""

        return str(obj.work_address)

    def get_work(self, obj):
        return {
            "id": obj.id,
            "name": obj.work_name,
            "client_id": obj.party_id,
            "cost_center": obj.code,
            "work_address_id": obj.work_address_id,
            "address": (
                str(obj.work_address)
                if obj.work_address_id
                else ""
            ),
        }

    def get_issuer(self, obj):
        if obj.issuer is not None:
            return self._user_summary(
                obj.issuer
            )

        issuer_name = str(
            obj.issuer_name or ""
        ).strip()

        if not issuer_name:
            return None

        return {
            "id": None,
            "name": issuer_name,
            "email": None,
        }

    def get_technical_responsible(self, obj):
        return self._user_summary(
            obj.technical_responsible
        )

    def get_contacts_count(self, obj):
        return obj.proposal_contacts.count()

    def get_requested_services_count(
        self,
        obj,
    ):
        return obj.requested_services.count()

    @staticmethod
    def _user_summary(user):
        if user is None:
            return None

        full_name = (
            user.get_full_name().strip()
            if hasattr(user, "get_full_name")
            else ""
        )

        username = str(
            getattr(user, "username", "") or ""
        ).strip()

        email = str(
            getattr(user, "email", "") or ""
        ).strip() or None

        return {
            "id": user.pk,
            "name": full_name or username,
            "email": email,
        }


    @staticmethod
    def _raise_django_validation(
        error,
    ):
        if hasattr(
            error,
            "message_dict",
        ):
            raise serializers.ValidationError(
                error.message_dict
            ) from error

        raise serializers.ValidationError(
            error.messages
        ) from error

    @staticmethod
    def _django_validation_message(
        error,
        field,
    ):
        if hasattr(
            error,
            "message_dict",
        ):
            messages = (
                error.message_dict.get(
                    field
                )
                or error.messages
            )
        else:
            messages = error.messages

        return (
            messages[0]
            if messages
            else "Valor inválido."
        )
