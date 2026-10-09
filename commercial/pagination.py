from rest_framework.pagination import PageNumberPagination


class CommercialPagination(PageNumberPagination):
    """
    Paginação padrão para listagens do módulo comercial.

    Permite ao frontend controlar page_size, respeitando um limite
    máximo para evitar respostas excessivamente grandes.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class CommercialAutocompletePagination(PageNumberPagination):
    """
    Paginação menor para endpoints utilizados por autocomplete.

    O frontend pode utilizar page/page_size para implementar
    carregamento incremental (infinite scroll).
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50