"""IEC Assignment 1 - Two Provider Cost Tracker.

A small command-line tool that sends one prompt to both Google Gemini and
Groq using their official Python SDKs, reads the token counts each API reports
in its usage metadata, measures how long each call took, and prints a
side-by-side comparison of tokens, elapsed time, and estimated USD cost.

After both providers succeed it writes ``results.json`` (a UTF-8 JSON array
with one object per provider) to the repository root.

Usage::

    uv run tracker.py "your prompt"

Configuration is read from a local ``.env`` file (loaded with python-dotenv) or
from the process environment. Required settings are documented in
``.env.example``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Pricing table - USD per 1,000,000 tokens.
#
# These rates were verified on the providers' official pricing pages and are
# the *standard paid-tier* rates used to estimate cost. Both providers offer a
# free tier (Google AI Studio free tier; GroqCloud developer/free plan), so the
# actual charge for a qualifying run is $0 - the figure here is an estimate of
# what the same request would cost on the paid tier.
#
# Sources (verified Nov 2026):
#   Gemini - https://aistudio.google.com/docs/pricing
#   Groq   - https://console.groq.com/docs/models
#
# To use a model not listed here, either add it to this table (with rates you
# have verified yourself) or override the price per provider via the optional
# environment variables GEMINI_INPUT_PRICE_PER_M / GEMINI_OUTPUT_PRICE_PER_M
# (and the GROQ_* equivalents). If no rate is available for a configured model
# the tool reports a clear error instead of silently using another model's rate.
# ---------------------------------------------------------------------------
PRICING: dict[str, dict[str, float]] = {
    # Gemini Developer API (Google AI Studio). Rates for prompts <= 200k tokens.
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
    # GroqCloud (developer / free plan) models.
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
    "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
}

# Fields written to results.json, in the required order.
JSON_FIELDS = (
    "provider",
    "model",
    "reply",
    "input_tokens",
    "output_tokens",
    "input_price_per_m",
    "output_price_per_m",
    "cost_usd",
)


class TrackerError(Exception):
    """Configuration or response-parsing error raised by the tracker."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
def load_config() -> dict[str, str]:
    """Load and validate configuration from ``.env`` and the environment.

    Returns a dict with the four required settings. Raises ``TrackerError``
    naming every missing setting and explaining how to configure it.
    """
    load_dotenv()  # reads .env if present; harmless if absent

    keys = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "gemini_model": os.getenv("GEMINI_MODEL"),
        "groq_api_key": os.getenv("GROQ_API_KEY"),
        "groq_model": os.getenv("GROQ_MODEL"),
    }
    env_name = {
        "gemini_api_key": "GEMINI_API_KEY",
        "gemini_model": "GEMINI_MODEL",
        "groq_api_key": "GROQ_API_KEY",
        "groq_model": "GROQ_MODEL",
    }

    missing = [env_name[k] for k, v in keys.items() if not v]
    if missing:
        raise TrackerError(
            "Missing required configuration: " + ", ".join(missing) + ".\n"
            "Fix this by copying .env.example to .env and filling in the values "
            "(or exporting them as environment variables). Obtain a Gemini key "
            "from Google AI Studio (https://aistudio.google.com/apikey) and a "
            "Groq key from GroqCloud (https://console.groq.com/keys)."
        )
    return keys  # type: ignore[return-value]


def resolve_price(provider: str, model: str, in_env: str, out_env: str) -> tuple[float, float]:
    """Return ``(input_price_per_m, output_price_per_m)`` for ``model``.

    Uses the verified ``PRICING`` table first, then optional environment
    overrides. Raises ``TrackerError`` if no rate is configured for the model.
    """
    if model in PRICING:
        return PRICING[model]["input"], PRICING[model]["output"]

    in_raw, out_raw = os.getenv(in_env), os.getenv(out_env)
    if in_raw is not None and out_raw is not None:
        try:
            return float(in_raw), float(out_raw)
        except ValueError as exc:
            raise TrackerError(
                f"{in_env}={in_raw!r} and {out_env}={out_raw!r} are not valid "
                f"numbers."
            ) from exc

    known = ", ".join(sorted(PRICING))
    raise TrackerError(
        f"No configured rate for {provider} model {model!r}. Add the model's "
        f"verified USD-per-million-token rates to the PRICING table in "
        f"tracker.py, or set {in_env} and {out_env} in .env.\n"
        f"Models with verified rates: {known}."
    )


# ---------------------------------------------------------------------------
# Cost helpers
# ---------------------------------------------------------------------------
def compute_cost(input_tokens: int, output_tokens: int,
                  input_price_per_m: float, output_price_per_m: float) -> float:
    """Estimate USD cost from token counts and per-million-token prices."""
    return (input_tokens * input_price_per_m
            + output_tokens * output_price_per_m) / 1_000_000


# ---------------------------------------------------------------------------
# Provider calls (one function per provider)
# ---------------------------------------------------------------------------
def call_gemini(prompt: str, config: dict[str, str],
                prices: tuple[float, float]) -> dict:
    """Send ``prompt`` to Google Gemini and return a result dict."""
    from google import genai

    input_price_per_m, output_price_per_m = prices
    client = genai.Client(api_key=config["gemini_api_key"])

    start = time.perf_counter()
    response = client.models.generate_content(
        model=config["gemini_model"], contents=prompt
    )
    elapsed = time.perf_counter() - start

    # Reply text. response.text raises ValueError when there is no text part.
    try:
        reply = response.text
    except ValueError:
        raise TrackerError(
            f"Gemini returned no text reply "
            f"(prompt_feedback={response.prompt_feedback})."
        )
    if reply is None or reply == "":
        raise TrackerError("Gemini returned an empty reply.")

    # Token counts straight from usage metadata.
    usage = response.usage_metadata
    if usage is None:
        raise TrackerError(
            "Gemini response is missing usage metadata; cannot count tokens."
        )
    if usage.prompt_token_count is None:
        raise TrackerError(
            "Gemini usage metadata is missing prompt_token_count."
        )
    if usage.candidates_token_count is None:
        raise TrackerError(
            "Gemini usage metadata is missing candidates_token_count."
        )
    # Output billed at the output rate includes thinking tokens, which the API
    # reports separately in thoughts_token_count. A valid zero is preserved.
    input_tokens = int(usage.prompt_token_count)
    output_tokens = int(usage.candidates_token_count) + int(
        usage.thoughts_token_count or 0
    )

    cost_usd = compute_cost(
        input_tokens, output_tokens, input_price_per_m, output_price_per_m
    )
    return {
        "provider": "gemini",
        "model": config["gemini_model"],
        "reply": reply,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_price_per_m": input_price_per_m,
        "output_price_per_m": output_price_per_m,
        "cost_usd": cost_usd,
        "elapsed_seconds": elapsed,
    }


def call_groq(prompt: str, config: dict[str, str],
              prices: tuple[float, float]) -> dict:
    """Send ``prompt`` to Groq and return a result dict."""
    from groq import Groq

    input_price_per_m, output_price_per_m = prices
    client = Groq(api_key=config["groq_api_key"])
    messages = [{"role": "user", "content": prompt}]

    start = time.perf_counter()
    response = client.chat.completions.create(
        model=config["groq_model"], messages=messages
    )
    elapsed = time.perf_counter() - start

    if not response.choices:
        raise TrackerError("Groq returned no choices.")
    reply = response.choices[0].message.content
    if reply is None or reply == "":
        raise TrackerError("Groq returned an empty reply.")

    usage = response.usage
    if usage is None:
        raise TrackerError(
            "Groq response is missing usage data; cannot count tokens."
        )
    if usage.prompt_tokens is None:
        raise TrackerError("Groq usage is missing prompt_tokens.")
    if usage.completion_tokens is None:
        raise TrackerError("Groq usage is missing completion_tokens.")
    input_tokens = int(usage.prompt_tokens)
    output_tokens = int(usage.completion_tokens)

    cost_usd = compute_cost(
        input_tokens, output_tokens, input_price_per_m, output_price_per_m
    )
    return {
        "provider": "groq",
        "model": config["groq_model"],
        "reply": reply,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_price_per_m": input_price_per_m,
        "output_price_per_m": output_price_per_m,
        "cost_usd": cost_usd,
        "elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def print_replies(results: list[dict]) -> None:
    """Print each provider's reply under a labeled header."""
    for r in results:
        print(f"\n--- {r['provider']} ({r['model']}) ---")
        print(r["reply"])


def print_table(results: list[dict]) -> None:
    """Print the comparison table (tokens, elapsed seconds, cost in USD)."""
    headers = ["Provider", "Input tokens", "Output tokens", "Elapsed (s)", "Cost (USD)"]
    rows = [
        [
            r["provider"],
            str(r["input_tokens"]),
            str(r["output_tokens"]),
            f"{r['elapsed_seconds']:.3f}",
            f"${r['cost_usd']:.8f}",
        ]
        for r in results
    ]
    all_rows = [headers, *rows]
    widths = [max(len(str(row[i])) for row in all_rows) for i in range(len(headers))]
    sep = "  ".join("-" * w for w in widths)

    def fmt(row: list[str]) -> str:
        return "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row))

    print()
    print(fmt(headers))
    print(sep)
    for row in rows:
        print(fmt(row))
    print()


def write_results(results: list[dict]) -> Path:
    """Write ``results.json`` at the repository root and return its path.

    Only the eight specified fields are written for each provider; elapsed time
    is shown in the terminal table but not stored in the JSON.
    """
    path = Path(__file__).resolve().parent / "results.json"
    data = [{field: r[field] for field in JSON_FIELDS} for r in results]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"Results written to {path}")
    return path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    args = argv[1:]

    if len(args) != 1:
        print('Usage: uv run tracker.py "your prompt"', file=sys.stderr)
        return 2

    prompt = args[0]
    if not prompt.strip():
        print("Error: prompt must not be empty or whitespace-only.",
              file=sys.stderr)
        return 2

    # Validate configuration before any API call.
    try:
        config = load_config()
    except TrackerError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 1

    try:
        gemini_prices = resolve_price(
            "Gemini", config["gemini_model"],
            "GEMINI_INPUT_PRICE_PER_M", "GEMINI_OUTPUT_PRICE_PER_M",
        )
        groq_prices = resolve_price(
            "Groq", config["groq_model"],
            "GROQ_INPUT_PRICE_PER_M", "GROQ_OUTPUT_PRICE_PER_M",
        )
    except TrackerError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 1

    print(
        f"Sending prompt to Gemini ({config['gemini_model']}) and "
        f"Groq ({config['groq_model']})..."
    )

    # Attempt both providers; collect any errors. results.json is only written
    # when both succeed, so a failure leaves any previous results.json intact.
    calls = [
        ("gemini", call_gemini, gemini_prices),
        ("groq", call_groq, groq_prices),
    ]
    results: list[dict] = []
    errors: list[tuple[str, Exception]] = []
    for name, call_fn, prices in calls:
        try:
            results.append(call_fn(prompt, config, prices))
        except Exception as exc:  # noqa: BLE001 - report any API/parse failure
            errors.append((name, exc))

    if errors:
        for name, exc in errors:
            print(f"{name} error: {exc}", file=sys.stderr)
        print(
            "results.json was not updated because not all providers succeeded.",
            file=sys.stderr,
        )
        return 1

    # Both succeeded.
    print_replies(results)
    print_table(results)
    write_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
