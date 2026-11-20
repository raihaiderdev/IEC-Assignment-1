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

> **Note:** the output below is from an actual run with `gemini-3.8-flash` and
> `openai/gpt-oss-120b`. Token counts, timing, and cost will vary with your
> prompt and chosen models. Gemini free-tier responses can be slow (rate
> limiting); Groq's LPU hardware typically replies in under 2 seconds.

```
Sending prompt to Gemini (gemini-3.8-flash) and Groq (openai/gpt-oss-120b)...

--- gemini (gemini-3.8-flash) ---
The speed of light in a vacuum is exactly **299,792,458 meters per second**
(commonly denoted as ***c***).

Here are a few common approximations:

* **Metric:** ~**300,000 kilometers per second** (3 × 10⁸ m/s)
* **Imperial:** ~**186,282 miles per second**
* **Miles per hour:** ~**670,616,629 mph**

--- groq (openai/gpt-oss-120b) ---
The speed of light in a vacuum is exactly **299,792,458 m/s** (meters per second).

- In other common units this is:
  • **≈ 299,792 km/s** (kilometers per second)
  • **≈ 186,282 mi/s** (miles per second)
  • **≈ 1.079 × 10⁹ km/h** (kilometers per hour)

This value is a fundamental constant of nature and is denoted by the symbol
**c** in physics equations, such as Einstein's famous relation E = mc².

Provider  Input tokens  Output tokens  Elapsed (s)  Cost (USD)
--------  ------------  -------------  -----------  ------------
gemini    8             337            33.087       $0.00126975
groq      78            216            1.101        $0.00014130

Results written to .../IEC-Assignment-1/results.json
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

Calling two LLM providers with the same prompt reveals striking differences in
speed, token usage, and cost. Across three live test runs, Groq's LPU hardware
replied in 1.1–1.6 seconds every time, while Gemini 3.8 Flash on the free tier
took 33–99 seconds (a sign of rate-limiting rather than raw model speed). On
the cost side, Groq's GPT-OSS 120B was consistently 8–13× cheaper than Gemini
3.8 Flash for the same prompt, entirely because of the difference in
per-token pricing. Reading token counts directly from each API's usage metadata
— rather than estimating from character count — also showed that Groq reports
noticeably more input tokens for the same prompt (78–82 vs. 8–12), reflecting
different tokenizers and system-prompt handling between the two providers.
