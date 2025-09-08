from dataclasses import dataclass
import math
from typing import Iterable, Literal, overload
import openai
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionChunk,
    ChatCompletion,
    ChatCompletionMessage,
)
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import ChoiceDelta, Choice as ChunkChoice
from openai._types import NotGiven, NOT_GIVEN

import tiktoken

from tocky.env import get_env
from tocky.utils.models import LLMSpecifier


env = get_env()

def encoding_for_model(model_name: str):
    """Get the encoding for a specific OpenAI model."""
    if model_name == "gpt-5":
        # Uses the same encoding, tiktoken is outdated https://github.com/openai/tiktoken/issues/428
        model_name = "gpt-5-mini"
    return tiktoken.encoding_for_model(model_name)

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
        return len(encoding_for_model(self.name).encode(message))

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


@overload
def hit_llm_one_off(
    llm: LLMSpecifier,
    prompt: str,
    system_prompt: str | None = None,
    stream: Literal[False] = False,
) -> ChatCompletion: ...
@overload
def hit_llm_one_off(
    llm: LLMSpecifier,
    prompt: str,
    system_prompt: str | None,
    stream: Literal[True],
) -> Iterable[ChatCompletionChunk]: ...
def hit_llm_one_off(
    llm: LLMSpecifier,
    prompt: str,
    system_prompt: str | None = None,
    stream: bool = False,
) -> ChatCompletion | Iterable[ChatCompletionChunk]:
    llm_function = hit_llm_streaming if stream else hit_llm
    return llm_function(
        llm,
        [
            {
                "role": "user",
                "content": prompt,
            },
        ],
        system_prompt=system_prompt,
    )


def hit_llm_streaming(
    llm: LLMSpecifier,
    messages: Iterable[ChatCompletionMessageParam],
    system_prompt: str | None = None,
) -> Iterable[ChatCompletionChunk]:
    # Note the args and the kwargs must be consistent with the signature
    # of the other method!
    cache_key = hit_llm.__cache_key__(  # type: ignore
        llm,
        messages,
        system_prompt=system_prompt,
    )
    if cache_key in env.cache:
        resp = hit_llm(
            llm,
            messages,
            system_prompt=system_prompt,
        )
        # We're going to fake it as a stream
        yield ChatCompletionChunk(
            id=resp.id,
            choices=[
                ChunkChoice(
                    delta=ChoiceDelta(
                        role="assistant",
                        content=resp.choices[0].message.content,
                    ),
                    finish_reason=resp.choices[0].finish_reason,
                    index=0,
                    logprobs=None,  # type: ignore
                )
            ],
            usage=None,
            created=resp.created,
            model=resp.model,
            system_fingerprint=resp.system_fingerprint,
            object="chat.completion.chunk",
        )
        yield ChatCompletionChunk(
            id=resp.id,
            choices=[],
            usage=resp.usage,
            created=resp.created,
            model=resp.model,
            object="chat.completion.chunk",
        )
        return

    client, model = llm.split("/", 1)
    match client:
        case "openai":
            llm_client = env.openai_client
        case "google":
            llm_client = env.gemini_openai_client
        case _:
            raise ValueError(f"Unknown client: {client}")

    response = llm_client.chat.completions.create(
        model=model,  # type: ignore
        stream=True,
        stream_options={"include_usage": True},
        messages=[
            *(
                [
                    {
                        "role": "system",
                        "content": system_prompt,
                    }
                ]
                if system_prompt
                else []
            ),
            *messages,
        ],
    )

    full_content = ""
    first_chunk: ChatCompletionChunk | None = None
    last_contentful_chunk: ChatCompletionChunk | None = None
    last_chunk: ChatCompletionChunk | None = None

    prev_chunk: ChatCompletionChunk | None = None
    for chunk in response:
        if first_chunk is None:
            first_chunk = chunk

        if chunk.choices and chunk.choices[0].delta.content:
            full_content += chunk.choices[0].delta.content
            yield chunk
        else:
            # We're at the end of the stream, this is the final chunk
            # that just contains usage information
            last_contentful_chunk = prev_chunk
            last_chunk = chunk
            yield chunk

        prev_chunk = chunk

    assert last_chunk is not None, "Last chunk should not be None"
    assert last_contentful_chunk is not None, "Last contentful chunk should not be None"
    assert last_chunk.usage is not None, "Last chunk should have usage information"

    aggregate_chat_completion = ChatCompletion(
        id=last_chunk.id,
        choices=[
            Choice(
                finish_reason=last_contentful_chunk.choices[0].finish_reason or "stop",
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=full_content,
                ),
            )
        ],
        usage=last_chunk.usage,
        created=last_chunk.created,
        model=last_chunk.model,
        object="chat.completion",
        system_fingerprint=last_chunk.system_fingerprint,
    )

    # Now we're done; save a memoized version of the response
    env.cache_sync.set(cache_key, aggregate_chat_completion)



@env.cache_sync.memoize()
def hit_llm(
    llm: LLMSpecifier | str,
    messages: Iterable[ChatCompletionMessageParam],
    reasoning_effort: Literal["none", "low", "medium", "high"] | NotGiven = NOT_GIVEN,
    system_prompt: str | None = None,
):
    client, model = llm.split("/", 1)
    match client:
        case "openai":
            llm_client = env.openai_client
        case "google":
            llm_client = env.gemini_openai_client
        case _:
            raise ValueError(f"Unknown client: {client}")

    return llm_client.chat.completions.create(
        model=model,
        # This is failing because the official OpenAI client does not allow for 'none'
        # as a reasoning effort, but the Gemini OpenAI client does allow it.
        reasoning_effort=reasoning_effort,  # type: ignore
        messages=[
            *(
                [
                    {
                        "role": "system",
                        "content": system_prompt,
                    }
                ]
                if system_prompt
                else []
            ),
            *messages,
        ],
    )