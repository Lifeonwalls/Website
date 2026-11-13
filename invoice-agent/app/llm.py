"""Thin wrapper around the Anthropic SDK for structured (Pydantic) outputs."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from .config import get_settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


@lru_cache
def client() -> anthropic.Anthropic:
    s = get_settings()
    # Explicit key if configured; otherwise the SDK resolves credentials from the environment.
    return anthropic.Anthropic(api_key=s.anthropic_api_key or None, max_retries=4)


def parse(*, schema: type[T], system: str, content: list[dict] | str, model: str,
          effort: str = "medium", max_tokens: int = 16000) -> T:
    """Call Claude with a Pydantic output schema. Retries once on the fallback model if declined."""
    s = get_settings()
    models = [model] + ([s.fallback_model] if s.fallback_model and s.fallback_model != model else [])
    last_reason = ""
    for m in models:
        try:
            resp = client().messages.parse(
                model=m,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_config={"effort": effort},
                output_format=schema,
            )
        except anthropic.BadRequestError as e:
            raise LLMError(f"Bad request to Claude: {e.message}") from e
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic API key is invalid or missing") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Rate limited by the Anthropic API after retries") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Could not reach the Anthropic API") from e

        if resp.stop_reason == "refusal":
            last_reason = f"refusal ({getattr(resp.stop_details, 'category', None)})"
            log.warning("Model %s declined; trying fallback", m)
            continue
        if resp.stop_reason == "max_tokens":
            raise LLMError("Response hit max_tokens before completing")
        if resp.parsed_output is None:
            raise LLMError("Claude returned no parsable output")
        return resp.parsed_output
    raise LLMError(f"All models declined the request: {last_reason}")
