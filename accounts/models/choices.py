from django.db import models


class UserType(models.TextChoices):
    CLIENT = "CLIENTE", "Cliente"
    EMPLOYEE = "COLABORADOR", "Colaborador"
    SUPPLIER = "FORNECEDOR", "Fornecedor"


class ClientGroup(models.TextChoices):
    BOARD = "DIRETORIA", "Diretoria"
    OPERATIONAL = "OPERACIONAL", "Operacional"


class EmployeeGroup(models.TextChoices):
    BOARD = "DIRETORIA", "Diretoria"
    ADMINISTRATIVE = "ADMINISTRATIVO", "Administrativo"
    ENGINEERING = "ENGENHARIA", "Engenharia"
    WORKS = "OBRAS", "Obras"
    FINANCIAL = "FINANCEIRO", "Financeiro"
    PURCHASES = "COMPRAS", "Compras"