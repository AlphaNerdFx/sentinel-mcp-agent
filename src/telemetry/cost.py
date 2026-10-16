from dataclasses import dataclass
from typing import ClassVar, Dict


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


class CostEngine:
    """Calculates shadow pricing and token unit economics across model providers."""

    # PRD Section 4.3 Pricing Ledger: USD per 1,000,000 tokens
    DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
        "qwen2.5:7b-instruct-q4_K_M": {
            "prompt_per_1m": 0.15,
            "completion_per_1m": 0.60,
        },
        "gpt-4o-mini": {
            "prompt_per_1m": 0.15,
            "completion_per_1m": 0.60,
        },
    }

    def __init__(self, pricing_table: Dict[str, Dict[str, float]] | None = None) -> None:
        self.pricing_table = pricing_table or self.DEFAULT_PRICING

    def calculate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model_name: str = "qwen2.5:7b-instruct-q4_K_M",
    ) -> float:
        """Computes simulated or real USD spend for a model completion turn."""
        rates = self.DEFAULT_PRICING.get(
            model_name,
            self.DEFAULT_PRICING["qwen2.5:7b-instruct-q4_K_M"],
        )
        prompt_cost = (prompt_tokens / 1_000_000.0) * rates["prompt_per_1m"]
        completion_cost = (completion_tokens / 1_000_000.0) * rates["completion_per_1m"]
        return round(prompt_cost + completion_cost, 8)

    def calculate_tokens_per_second(self, completion_tokens: int, latency_ms: float) -> float:
        """Calculates physical generation throughput."""
        if latency_ms <= 0.0:
            return 0.0
        return round(completion_tokens / (latency_ms / 1000.0), 2)


# Backward-compatibility aliases for Phase 1 tests
CostCalculator = CostEngine
CostTracker = CostEngine
