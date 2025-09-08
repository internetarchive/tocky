from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class LLMModel:
    provider: Literal["openai"]
    model: str

    input_price_pm: int
    """Input price in microdollars per 1,000 tokens"""

    cached_input_price_pm: int | None
    """Cached input price in microdollars per 1,000 tokens"""

    output_price_pm: int
    """Output price in microdollars per 1,000 tokens"""

    knowledge_cutoff: datetime

    supports_temperature: bool = True
    """Whether the model supports temperature parameter"""

    supports_batch: bool = True
    """Whether the model supports batch requests"""

    can_input_text: bool = True
    can_input_images: bool = False
    can_input_audio: bool = False

    can_output_text: bool = True
    can_output_images: bool = False

    is_deprecated: bool = False

    supports_chat_completion_api: bool = True
    supports_responses_api: bool = True
    supports_streaming: bool = True

    supports_reasoning: bool = False

    context_window_tokens: int | None = None
    max_output_tokens: int | None = None


d = datetime.fromisoformat

LLM_MODELS: list[LLMModel] = [
    # See https://platform.openai.com/docs/pricing
    LLMModel(
        provider="openai",
        model="gpt-5",
        input_price_pm=1_25_0,
        cached_input_price_pm=12_5,
        output_price_pm=10_00_0,
        supports_temperature=False,
        can_input_images=True,
        supports_reasoning=True,
        context_window_tokens=400_000,
        max_output_tokens=128_000,
        knowledge_cutoff=d("2024-09-30"),
    ),
    LLMModel(
        provider="openai",
        model="gpt-5-mini",
        input_price_pm=25_0,
        cached_input_price_pm=2_5,
        output_price_pm=2_00_0,
        supports_temperature=False,
        can_input_images=True,
        supports_reasoning=True,
        context_window_tokens=400_000,
        max_output_tokens=128_000,
        knowledge_cutoff=d("2024-05-31"),
    ),
    LLMModel(
        provider="openai",
        model="gpt-5-nano",
        input_price_pm=5_0,
        cached_input_price_pm=5,
        output_price_pm=40_0,
        supports_temperature=False,
        can_input_images=True,
        supports_reasoning=True,
        context_window_tokens=400_000,
        max_output_tokens=128_000,
        knowledge_cutoff=d("2024-05-31"),
    ),
    LLMModel(
        provider="openai",
        model="gpt-4.1",
        input_price_pm=2_00_0,
        cached_input_price_pm=50_0,
        output_price_pm=8_00_0,
        can_input_images=True,
        context_window_tokens=1_047_576,
        max_output_tokens=32_768,
        knowledge_cutoff=d("2024-06-01"),
    ),
    LLMModel(
        provider="openai",
        model="gpt-4.1-mini",
        input_price_pm=40_0,
        cached_input_price_pm=10_0,
        output_price_pm=1_60_0,
        can_input_images=True,
        context_window_tokens=1_047_576,
        max_output_tokens=32_768,
        knowledge_cutoff=d("2024-06-01"),
    ),
    LLMModel(
        provider="openai",
        model="gpt-4.1-nano",
        input_price_pm=10_0,
        cached_input_price_pm=2_5,
        output_price_pm=40_0,
        can_input_images=True,
        context_window_tokens=1_047_576,
        max_output_tokens=32_768,
        knowledge_cutoff=d("2024-06-01"),
    ),
    LLMModel(
        provider="openai",
        model="gpt-4.5-preview",
        input_price_pm=75_00_0,
        cached_input_price_pm=37_50_0,
        output_price_pm=1_50_00_0,
        can_input_images=True,
        is_deprecated=True,
        context_window_tokens=128_000,
        max_output_tokens=16_384,
        knowledge_cutoff=d("2023-10-01"),
    ),
    LLMModel(
        provider="openai",
        model="gpt-4o",
        input_price_pm=2_50_0,
        cached_input_price_pm=1_25_0,
        output_price_pm=10_00_0,
        can_input_images=True,
        context_window_tokens=128_000,
        max_output_tokens=16_384,
        knowledge_cutoff=d("2023-10-01"),
    ),
    LLMModel(
        provider="openai",
        model="gpt-4o-mini",
        input_price_pm=15_0,
        cached_input_price_pm=7_5,
        output_price_pm=60_0,
        can_input_images=True,
        context_window_tokens=128_000,
        max_output_tokens=16_384,
        knowledge_cutoff=d("2023-10-01")
    ),
    LLMModel(
        provider="openai",
        model="o1",
        input_price_pm=15_00_0,
        cached_input_price_pm=7_50_0,
        output_price_pm=60_00_0,
        can_input_images=True,
        supports_reasoning=True,
        context_window_tokens=200_000,
        max_output_tokens=100_000,
        knowledge_cutoff=d("2023-10-01")
    ),
    LLMModel(
        provider="openai",
        model="o1-pro",
        input_price_pm=150_00_0,
        cached_input_price_pm=None,
        output_price_pm=600_00_0,
        can_input_images=True,
        supports_chat_completion_api=False,
        supports_streaming=False,
        supports_reasoning=True,
        context_window_tokens=200_000,
        max_output_tokens=100_000,
        knowledge_cutoff=d("2023-10-01")
    ),
    LLMModel(
        provider="openai",
        model="o3-pro",
        input_price_pm=20_00_0,
        cached_input_price_pm=None,
        output_price_pm=80_00_0,
        can_input_images=True,
        supports_reasoning=True,
        context_window_tokens=200_000,
        max_output_tokens=100_000,
        knowledge_cutoff=d("2024-06-01")
    ),
    LLMModel(
        provider="openai",
        model="o3",
        input_price_pm=2_00_0,
        cached_input_price_pm=50_0,
        output_price_pm=8_00_0,
        can_input_images=True,
        supports_reasoning=True,
        context_window_tokens=200_000,
        max_output_tokens=100_000,
        knowledge_cutoff=d("2024-06-01")
    ),
    LLMModel(
        provider="openai",
        model="o4-mini",
        input_price_pm=1_10_0,
        cached_input_price_pm=27_5,
        output_price_pm=4_40_0,
        supports_temperature=False,
        can_input_images=True,
        supports_reasoning=True,
        context_window_tokens=200_000,
        max_output_tokens=100_000,
        knowledge_cutoff=d("2024-06-01")
    ),
    LLMModel(
        provider="openai",
        model="o3-mini",
        input_price_pm=1_10_0,
        cached_input_price_pm=55_0,
        output_price_pm=4_40_0,
        can_input_images=False,
        supports_reasoning=True,
        context_window_tokens=200_000,
        max_output_tokens=100_000,
        knowledge_cutoff=d("2023-10-01")
    ),
    LLMModel(
        provider="openai",
        model="o1-mini",
        input_price_pm=1_10_0,
        cached_input_price_pm=55_0,
        output_price_pm=4_40_0,
        supports_batch=False,
        can_input_images=False,
        supports_reasoning=True,
        context_window_tokens=128_000,
        max_output_tokens=65_536,
        knowledge_cutoff=d("2023-10-01")
    ),
]

LLMSpecifier = Literal[
    "openai/gpt-5",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1-nano",
    "openai/gpt-4.5-preview",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/o1",
    "openai/o1-pro",
    "openai/o3-pro",
    "openai/o3",
    "openai/o4-mini",
    "openai/o3-mini",
    "openai/o1-mini",
]


def get_model_info(llm_specifier: LLMSpecifier | str) -> LLMModel | None:
    provider, model_name = llm_specifier.split("/", 1)
    for model in LLM_MODELS:
        if model.provider == provider and model.model == model_name:
            return model
    return None


def get_model_index_json():
    return [
        {
          **model.__dict__,
          "knowledge_cutoff": model.knowledge_cutoff.isoformat(),
        }
        for model in LLM_MODELS
    ]
