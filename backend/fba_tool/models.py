from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SkuRow:
    sku: str
    total_qty: int
    carton_qty: int
    length_cm: float
    width_cm: float
    height_cm: float
    unit_weight_kg: float = 0.0
    carton_tare_kg: float = 0.0
    carton_gross_kg: float | None = None
    unit_length_cm: float = 0.0
    unit_width_cm: float = 0.0
    unit_height_cm: float = 0.0
    category: str = ""

    @property
    def full_cartons(self) -> int:
        if self.carton_qty <= 0:
            return 0
        return self.total_qty // self.carton_qty

    @property
    def remainder(self) -> int:
        if self.carton_qty <= 0:
            return 0
        return self.total_qty % self.carton_qty

    def gross_weight_for_qty(self, qty: int) -> float:
        from fba_tool.box_weight import carton_gross_kg

        return carton_gross_kg(
            qty,
            self.unit_weight_kg,
            self.carton_tare_kg,
            self.carton_gross_kg,
            self.carton_qty,
        )

    def unit_volume_cm3(self) -> float:
        if self.carton_qty <= 0:
            return 0.0
        carton_volume = self.length_cm * self.width_cm * self.height_cm
        return carton_volume / self.carton_qty


@dataclass
class BoxItem:
    sku: str
    qty: int


@dataclass
class BoxPlan:
    box_no: int
    items: List[BoxItem] = field(default_factory=list)
    source: str = "整箱"

    def as_dict(self) -> Dict[str, str]:
        return {
            "箱号": self.box_no,
            "来源": self.source,
            "SKU明细": ", ".join(f"{item.sku} x {item.qty}" for item in self.items),
        }

