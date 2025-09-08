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

def encoding_for_model(model_name: LLMSpecifier | str):
    """Get the encoding for a specific OpenAI model."""

    # Todo: This should likely be handled further upstream
    provider, model_name = model_name.split('/', 1)

    match provider:
        case "openai":
            if model_name == "gpt-5":
                # Uses the same encoding, tiktoken is outdated https://github.com/openai/tiktoken/issues/428
                model_name = "gpt-5-mini"
            return tiktoken.encoding_for_model(model_name)
        case "google":
            # Google doesn't have a way to check these locally, so use gpt-5-mini as a proxy
            return tiktoken.encoding_for_model("gpt-5-mini")
        case _:
            raise ValueError(f"Unknown provider: {provider}")


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