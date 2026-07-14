from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.errors import ContractNotVerified


@dataclass(frozen=True)
class ProductRestriction:
    allowed: bool
    reason_code: str = ""
    max_quantity: int | None = None


class SupplyPlanningGateway(Protocol):
    """Boundary for DTOs that must be verified in an Ozon seller cabinet."""

    def clusters(self) -> tuple[str, ...]: ...
    def timeslots(self, cluster: str) -> tuple[str, ...]: ...
    def restriction(self, offer_id: str, cluster: str, quantity: int) -> ProductRestriction: ...


class MockSupplyPlanningGateway:
    def __init__(self, clusters: tuple[str, ...] = ("Москва", "Санкт-Петербург"), slots: tuple[str, ...] = ("2026-07-20 10:00–12:00", "2026-07-21 14:00–16:00"), max_quantity: int = 100_000) -> None:
        self._clusters, self._slots, self.max_quantity = clusters, slots, max_quantity

    def clusters(self) -> tuple[str, ...]:
        return self._clusters

    def timeslots(self, cluster: str) -> tuple[str, ...]:
        return self._slots if cluster in self._clusters else ()

    def restriction(self, offer_id: str, cluster: str, quantity: int) -> ProductRestriction:
        if cluster not in self._clusters:
            return ProductRestriction(False, "cluster_unavailable")
        if quantity > self.max_quantity:
            return ProductRestriction(False, "quantity_limit", self.max_quantity)
        return ProductRestriction(True, max_quantity=self.max_quantity)


class UnverifiedOzonSupplyPlanningGateway:
    """Fail-closed production boundary until official DTO fixtures are recorded."""

    @staticmethod
    def _blocked():
        raise ContractNotVerified("Контракты кластеров, таймслотов и ограничений поставки требуют проверки в кабинете")

    def clusters(self) -> tuple[str, ...]:
        return self._blocked()

    def timeslots(self, cluster: str) -> tuple[str, ...]:
        return self._blocked()

    def restriction(self, offer_id: str, cluster: str, quantity: int) -> ProductRestriction:
        return self._blocked()
