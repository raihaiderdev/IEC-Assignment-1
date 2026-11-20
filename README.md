# IEC Assignment 1 — Two Provider Cost Tracker

A beginner-friendly Python app that opens a window, lets you type **3 prompts**,
sends each one to **Google Gemini** and **Groq** at the same time, and shows
you the replies side by side along with how many tokens were used, how long it
took, and what it would cost.

---

## What it does

1. You type 3 questions (prompts) in the app window
2. It sends each question to both Gemini and Groq
3. It shows both answers side by side for each prompt
4. It shows a table comparing tokens, speed, and cost
5. It saves everything to a `results.json` file

---

## Project files

```
IEC-Assignment-1/
├── tracker.py       ← the main app (run this)
├── pyproject.toml   ← project config (lists dependencies)
├── uv.lock          ← exact package versions
├── .env.example     ← template for your API keys
├── .env             ← your real keys (never committed)
├── .gitignore       ← tells git what files to ignore
├── README.md        ← this file
└── results.json     ← created when you run the app (gitignored)
```

---

## Setup — step by step

### Step 1 — Install Python

Download and install Python 3.11 or newer from https://www.python.org/

### Step 2 — Install uv

`uv` is a fast Python package manager. Install it by running this in your terminal:

```bash
pip install uv
```

### Step 3 — Install the project dependencies

Open a terminal in the project folder and run:

```bash
uv sync
```

This reads `pyproject.toml` and installs these three packages into a local `.venv` folder:

| Package | What it does |
|---|---|
| `google-genai` | Official Google SDK to talk to Gemini |
| `groq` | Official Groq SDK to talk to Groq |
| `python-dotenv` | Reads your API keys from the `.env` file |

### Step 4 — Get your API keys

You need a free key from each provider:

| Provider | Where to get the key |
|---|---|
| Google Gemini | https://aistudio.google.com/apikey |
| Groq | https://console.groq.com/keys |

Both are free — no credit card needed.

### Step 5 — Create your `.env` file

Copy the example file:

```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

Then open `.env` and replace the placeholder values with your real keys:

```
GEMINI_API_KEY=paste_your_gemini_key_here
GEMINI_MODEL=gemini-3.5-flash

GROQ_API_KEY=paste_your_groq_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

> ⚠️ Never share your `.env` file or commit it to GitHub. It is already listed
> in `.gitignore` so git will automatically ignore it.

---

## How to run

```bash
uv run tracker.py
```

A window will open that looks like this:

```
┌─────────────────────────────────────────────────────────┐
│  ⚡ Two Provider Cost Tracker  |  Gemini  vs  Groq       │
│  Gemini model: gemini-3.5-flash   Groq: gpt-oss-120b    │
│                                                          │
│  Prompt 1  [ type your first question here            ] │
│  Prompt 2  [ type your second question here           ] │
│  Prompt 3  [ type your third question here            ] │
│                                                          │
│  [ ▶ Run All Prompts ]   Enter prompts above and click  │
└─────────────────────────────────────────────────────────┘
```

Type your 3 questions and click **Run All Prompts**.

---

## Sample output

After clicking Run, results appear for each prompt like this:

```
Prompt 1: What is the speed of light?
─────────────────────────────────────────────────────────

🔵 GEMINI  (gemini-3.5-flash)      🟢 GROQ  (openai/gpt-oss-120b)
┌──────────────────────────┐       ┌──────────────────────────┐
│ The speed of light in a  │       │ The speed of light in a  │
│ vacuum is exactly        │       │ vacuum is exactly        │
│ 299,792,458 m/s...       │       │ 299,792,458 m/s...       │
│                          │       │                          │
│ In: 8    Out: 92         │       │ In: 78   Out: 180        │
│ Time: 2.1s  Cost: $0.00  │       │ Time: 1.1s  Cost: $0.00  │
└──────────────────────────┘       └──────────────────────────┘

Provider   In tokens   Out tokens   Time (s)   Cost (USD)
gemini     8           92           2.10       $0.00023600
groq       78          180          1.10       $0.00012270
```

> **Note:** Gemini on the free tier can be slow (sometimes 30–90 seconds per
> request due to rate limiting). Groq typically responds in 1–2 seconds.

---

## results.json

After every run the app saves a `results.json` file. It contains one entry per
prompt per provider (6 entries total for 3 prompts × 2 providers):

```json
[
  {
    "prompt": "What is the speed of light?",
    "provider": "gemini",
    "model": "gemini-3.5-flash",
    "reply": "The speed of light in a vacuum is exactly 299,792,458 m/s...",
    "input_tokens": 8,
    "output_tokens": 92,
    "input_price_per_m": 0.30,
    "output_price_per_m": 2.50,
    "cost_usd": 0.000236,
    "elapsed_seconds": 2.1
  },
  {
    "prompt": "What is the speed of light?",
    "provider": "groq",
    "model": "openai/gpt-oss-120b",
    "reply": "The speed of light in a vacuum is exactly 299,792,458 m/s...",
    "input_tokens": 78,
    "output_tokens": 180,
    "input_price_per_m": 0.15,
    "output_price_per_m": 0.60,
    "cost_usd": 0.00012270,
    "elapsed_seconds": 1.1
  }
]
```

`results.json` is listed in `.gitignore` and is never committed to GitHub.

---

## How the cost is calculated

```
cost = (input_tokens × input_price + output_tokens × output_price) / 1,000,000
```

**Example:**
- Groq: 78 input tokens × $0.15 + 180 output tokens × $0.60 = 11.7 + 108 = 119.7
- Divide by 1,000,000 → **$0.0001197**

> These are estimates based on the standard paid-tier rates. The free tier
> costs $0, so your actual bill will be $0 for small experiments.

### Pricing used (verified November 2026)

| Provider | Model | Input $/1M | Output $/1M | Source |
|---|---|---|---|---|
| Gemini | `gemini-3.5-flash` | $0.30 | $2.50 | [aistudio.google.com/docs/pricing](https://aistudio.google.com/docs/pricing) |
| Gemini | `gemini-3.5-flash-lite` | $0.30 | $2.50 | [aistudio.google.com/docs/pricing](https://aistudio.google.com/docs/pricing) |
| Gemini | `gemini-3.8-flash` | $0.75 | $3.75 | [aistudio.google.com/docs/pricing](https://aistudio.google.com/docs/pricing) |
| Groq | `openai/gpt-oss-120b` | $0.15 | $0.60 | [console.groq.com/docs/models](https://console.groq.com/docs/models) |
| Groq | `openai/gpt-oss-20b` | $0.075 | $0.30 | [console.groq.com/docs/models](https://console.groq.com/docs/models) |

---

## How the code is structured

`tracker.py` is kept simple and readable. Here is what each part does:

```python
# 1. Load API keys from .env
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
...

# 2. Pricing dictionary
PRICING = { "gemini-3.5-flash": {"input": 0.30, "output": 2.50}, ... }

# 3. calc_cost() — one formula, 2 lines
def calc_cost(in_tokens, out_tokens, model): ...

# 4. ask_gemini() — sends prompt, returns reply + token counts + time
def ask_gemini(prompt): ...

# 5. ask_groq() — same but for Groq
def ask_groq(prompt): ...

# 6. save_results() — writes results.json
def save_results(all_results): ...

# 7. App class — the GUI window
class App(tk.Tk):
    _build()              # draw all widgets
    _on_run()             # handles button click
    _worker()             # runs API calls in background
    _show_prompt_result() # draws one result card
```

---

## What this assignment demonstrates

This project shows three important things:

1. **Different providers give different speeds** — Groq's LPU hardware responds
   in 1–2 seconds while Gemini's free tier can take 30–90 seconds due to rate
   limits.

2. **Cost depends on token count and model** — The same prompt sent to two
   different models produces different token counts (because each model uses a
   different tokenizer) and different costs (because pricing varies).

3. **APIs return usage data** — Both providers include token counts directly in
   the API response (`usage_metadata` for Gemini, `usage` for Groq), so you
   don't have to estimate — you read exact numbers.
