from rest_framework.pagination import PageNumberPagination


class SupplyPagination(PageNumberPagination):
    """Paginação limitada para impedir respostas excessivamente grandes."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class SupplyAutocompletePagination(PageNumberPagination):
    """Páginas menores para carregamento incremental do autocomplete."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50

class BudgetStagePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class BudgetSheetPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100