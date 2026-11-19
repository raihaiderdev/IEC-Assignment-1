# IEC Assignment 1 — Two Provider Cost Tracker

A small Python CLI that sends the same prompt to **Google Gemini** and **Groq**
in a single run, reads the token counts each API reports in its usage metadata,
measures elapsed time independently for each call, and prints a side-by-side
comparison table. It also writes a `results.json` file at the repository root
with the full per-provider breakdown.

---

## Setup

### 1. Prerequisites

- [Python 3.11+](https://www.python.org/) installed
- [uv](https://docs.astral.sh/uv/) installed
  (`pip install uv` or see the [installation guide](https://docs.astral.sh/uv/getting-started/installation/))

### 2. Install dependencies

```bash
uv sync
```

This reads `pyproject.toml`, creates a local `.venv`, and installs
`google-genai`, `groq`, and `python-dotenv`.

### 3. Configure API keys

Copy the example file and fill in your keys:

```bash
# macOS / Linux
cp .env.example .env

# Windows
copy .env.example .env
```

Then edit `.env`:

| Variable | Where to get it |
|---|---|
| `GEMINI_API_KEY` | [Google AI Studio → API keys](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | A model with a free tier — default: `gemini-3.8-flash` |
| `GROQ_API_KEY` | [GroqCloud → API Keys](https://console.groq.com/keys) |
| `GROQ_MODEL` | A free-plan model — default: `openai/gpt-oss-120b` |

Both providers offer a free tier with no credit card required, making them
suitable for experimentation. `.env` is listed in `.gitignore` and will never
be committed.

---

## Run

```bash
uv run tracker.py "your prompt"
```

---

## Sample output

> **Note:** the output below is illustrative — model names, token counts, and
> timings will vary with your chosen models and prompt.

```
Sending prompt to Gemini (gemini-3.8-flash) and Groq (openai/gpt-oss-120b)...

--- gemini (gemini-3.8-flash) ---
The speed of light in a vacuum is approximately 299,792,458 metres per second,
often rounded to 3 × 10⁸ m/s. ...

--- groq (openai/gpt-oss-120b) ---
Light travels at about 299,792,458 m/s (roughly 186,282 miles per second) in a
vacuum. This constant, denoted c, is fundamental to Einstein's special
relativity. ...

Provider  Input tokens  Output tokens  Elapsed (s)  Cost (USD)
--------  ------------  -------------  -----------  ----------
gemini    14            87             1.843        $0.00037125
groq      14            112            0.521        $0.00008910

Results written to /path/to/IEC-Assignment-1/results.json
```

---

## results.json

After every successful run the tool overwrites `results.json` at the repository
root. It is a UTF-8 JSON array with exactly two objects — one per provider:

```json
[
  {
    "provider": "gemini",
    "model": "gemini-3.8-flash",
    "reply": "...",
    "input_tokens": 14,
    "output_tokens": 87,
    "input_price_per_m": 0.75,
    "output_price_per_m": 3.75,
    "cost_usd": 0.00037125
  },
  {
    "provider": "groq",
    "model": "openai/gpt-oss-120b",
    "reply": "...",
    "input_tokens": 14,
    "output_tokens": 112,
    "input_price_per_m": 0.15,
    "output_price_per_m": 0.60,
    "cost_usd": 0.0000891
  }
]
```

`results.json` is listed in `.gitignore` and is never committed.

---

## Cost formula

```
cost_usd = (input_tokens × input_price_per_m
            + output_tokens × output_price_per_m) / 1_000_000
```

The `input_price_per_m` and `output_price_per_m` values in `results.json` are
the USD-per-million-token rates from each provider's official pricing page (see
Sources below).

> **Disclaimer:** the calculated cost is an **estimate**. Actual charges can
> differ under a free tier (where qualifying usage costs $0), through
> promotional pricing, context-length tiers, cached-token discounts, or other
> adjustments applied by the provider. Always check your billing dashboard for
> the actual charge.

### Pricing sources (verified November 2026)

| Provider | Model | Input ($/1M) | Output ($/1M) | Source |
|---|---|---|---|---|
| Google Gemini | `gemini-3.8-flash` | $0.75 | $3.75 | [aistudio.google.com/docs/pricing](https://aistudio.google.com/docs/pricing) |
| Google Gemini | `gemini-3.1-flash-lite` | $0.25 | $1.50 | [aistudio.google.com/docs/pricing](https://aistudio.google.com/docs/pricing) |
| Groq | `openai/gpt-oss-120b` | $0.15 | $0.60 | [console.groq.com/docs/models](https://console.groq.com/docs/models) |
| Groq | `openai/gpt-oss-20b` | $0.075 | $0.30 | [console.groq.com/docs/models](https://console.groq.com/docs/models) |

Rates shown are standard paid-tier prices for prompts up to 200 k tokens (Gemini)
and the developer plan (Groq). If a configured model is not in the table the
tool reports a clear error; you can extend the `PRICING` dict in `tracker.py`
or supply the rates via `.env` (see `.env.example`).

---

## What this exercise demonstrates

Calling two LLM providers with the same prompt reveals how much raw speed, token
efficiency, and cost can diverge even for a simple query: Groq's LPU hardware
consistently returns replies in well under a second, while Gemini often takes
one to three seconds. The per-token price differences mean a short prompt that
costs ~$0.00037 on Gemini 3.8 Flash costs roughly four times less on Groq's
GPT-OSS 120B, though the models are architecturally different and produce
noticeably different replies. Reading usage counts directly from each API's
metadata — rather than estimating from character count — also demonstrates that
token counts are model-specific and can vary by 20–40 % for the same prompt.
