from dataclasses import dataclass
from typing import ClassVar

@dataclass(frozen=True)
class ShadowCostCalculator:
    """Calculates financial impact using standard commercial token pricing."""
    INPUT_RATE_PER_MILLION: ClassVar[float] = 0.15
    OUTPUT_RATE_PER_MILLION: ClassVar[float] = 0.60

    @classmethod
    def calculate_cost(cls, input_tokens: int, output_tokens: int) -> float:
        in_cost = (input_tokens / 1_000_000.0) * cls.INPUT_RATE_PER_MILLION
        out_cost = (output_tokens / 1_000_000.0) * cls.OUTPUT_RATE_PER_MILLION
        return round(in_cost + out_cost, 8)