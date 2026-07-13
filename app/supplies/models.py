from dataclasses import dataclass


@dataclass(frozen=True)
class SupplyLine:
    offer_id: str
    quantity: int
    units_per_box: int

    @property
    def boxes(self) -> int:
        if self.quantity % self.units_per_box:
            raise ValueError(f"{self.quantity} не делится на {self.units_per_box}")
        return self.quantity // self.units_per_box


@dataclass(frozen=True)
class SupplyIntent:
    destination: str
    lines: tuple[SupplyLine, ...]

    @property
    def boxes(self) -> int:
        return sum(line.boxes for line in self.lines)

