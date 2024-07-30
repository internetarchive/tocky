from dataclasses import dataclass
import math
import openai

import tiktoken


@dataclass
class PriceRangeCents:
    min: float
    max: float

    def __repr__(self):
        return f"{self.min / 100:.4f} - {self.max / 100:.4f} USD"

@dataclass
class ModelPricing:
    name: str
    prompt_cents: int
    """Cost in cents per 1,000,000 tokens"""
    completion_cents: int
    """Cost in cents per 1,000,000 tokens"""
    image_base_tokens: int
    """Base token cost for an image"""
    image_tile_size: int
    """Size of a square image tile in pixels"""
    tokens_per_tile: int
    """Tokens per image tile"""

    def cost_from_usage(self, usage: openai.types.CompletionUsage):
        return self.cost(usage.prompt_tokens, usage.completion_tokens)

    def cost(self, prompt_tokens: int, completion_tokens: int):
        prompt_cost = prompt_tokens * self.prompt_cents / 1_000_000
        completion_cost = completion_tokens * self.completion_cents / 1_000_000
        return prompt_cost + completion_cost

    def count_tokens(self, message: str) -> int:
        return len(tiktoken.encoding_for_model(self.name).encode(message))

    def predict_cost(
        self,
        prompts: list[str],
        max_tokens: int,
        image_sizes: list[tuple[int, int]],
    ):       
        prompt_tokens = sum(self.count_tokens(p) for p in prompts)
        image_tokens = sum(
            self.tokens_per_tile * math.ceil(image_size[0] / self.image_tile_size) * math.ceil(image_size[1] / self.image_tile_size)
            for image_size in image_sizes
        )
        if image_tokens:
            image_tokens += self.image_base_tokens
        
        prompt_cost = (prompt_tokens + image_tokens) * self.prompt_cents / 1_000_000
        completion_cost = max_tokens * self.completion_cents / 1_000_000

        return PriceRangeCents(min=prompt_cost, max=prompt_cost + completion_cost)

MODEL_PRICES = {
    "gpt-4o-mini": ModelPricing(
        name="gpt-4o-mini",
        prompt_cents=15,
        completion_cents=60,
        image_base_tokens=2833,
        image_tile_size=512,
        tokens_per_tile=5667,
    ),
}

def predict_cost(
    model_name: str,
    prompts: list[str],
    max_tokens: int,
    image_sizes: list[tuple[int, int]],
):
    return MODEL_PRICES[model_name].predict_cost(prompts, max_tokens, image_sizes)
