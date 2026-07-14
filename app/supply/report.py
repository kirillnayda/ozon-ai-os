from app.core.security import html_escape
from app.supply.models import StockLevel, SupplyRecommendation


def render_report(items: list[SupplyRecommendation]) -> str:
    critical = sum(item.level == StockLevel.CRITICAL for item in items)
    lines = ["<b>AI Supply Manager · FBO</b>", "", f"Позиций: {len(items)} · критичных: {critical}"]
    for item in items:
        days = "нет спроса" if item.stock_days is None else f"{item.stock_days:.1f} дн."
        lines.append(f"\n<b>{html_escape(item.offer_id)}</b> · {html_escape(item.cluster_name)}")
        lines.append(f"остаток {item.available}, спрос {item.daily_demand:.2f}/день, запас {days}")
        lines.append(f"рекомендация: {item.recommended_quantity} шт. · {item.level.value}")
        if item.reason:
            lines.append(f"<i>{html_escape(item.reason)}</i>")
    return "\n".join(lines)
