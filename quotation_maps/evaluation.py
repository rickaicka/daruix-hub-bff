"""Indicadores verificáveis. Sem inventar notas quando faltam registros de entrega."""
from django.db.models import F
from .models import PurchaseOrder


def supplier_evaluation(supplier):
    orders = PurchaseOrder.objects.filter(supplier=supplier)
    closed = orders.count()  # OC gerada é a definição operacional de orçamento fechado.
    delivered = orders.filter(delivered_at__isnull=False, promised_delivery_at__isnull=False)
    tracked = delivered.count()
    on_time = delivered.filter(delivered_at__lte=F("promised_delivery_at")).count()
    # Pontuação 0-100: entrega 50, pagamento 25, negócios fechados 25.
    # Indicadores ausentes NÃO são considerados nota zero.
    parts = {"orders": (min(closed, 10) / 10 * 25, 25)}
    if tracked:
        parts["delivery"] = (on_time / tracked * 50, 50)
    if supplier.payment_score is not None:
        parts["payment"] = (supplier.payment_score / 5 * 25, 25)
    covered = sum(weight for _, weight in parts.values())
    score = round(100 * sum(points for points, _ in parts.values()) / covered, 1) if covered else None
    return {"score": score, "score_coverage": round(covered),
            "closed_orders": closed, "tracked_deliveries": tracked,
            "on_time_deliveries": on_time, "on_time_percentage": round(on_time / tracked * 100, 1) if tracked else None,
            "payment_score": supplier.payment_score}
