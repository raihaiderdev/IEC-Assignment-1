"""IEC Assignment 1 - Two Provider Cost Tracker (GUI edition).

Run with:
    uv run tracker.py

A Tkinter window opens and asks for three prompts. After you click
"Run All Prompts" the app sends each prompt to Google Gemini and Groq,
shows a live status, displays each reply, prints a per-prompt comparison
table, and writes results.json at the repository root.

Configuration is loaded from a local .env file (python-dotenv).
Required settings: GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY, GROQ_MODEL.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, scrolledtext, ttk

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Pricing table  (USD per 1 000 000 tokens, verified Nov 2026)
# Sources:
#   Gemini – https://aistudio.google.com/docs/pricing
#   Groq   – https://console.groq.com/docs/models
# ---------------------------------------------------------------------------
PRICING: dict[str, dict[str, float]] = {
    "gemini-3.8-flash":      {"input": 0.75,  "output": 3.75},
    "gemini-3.1-flash-lite": {"input": 0.25,  "output": 1.50},
    "openai/gpt-oss-120b":   {"input": 0.15,  "output": 0.60},
    "openai/gpt-oss-20b":    {"input": 0.075, "output": 0.30},
}

JSON_FIELDS = (
    "prompt",
    "provider",
    "model",
    "reply",
    "input_tokens",
    "output_tokens",
    "input_price_per_m",
    "output_price_per_m",
    "cost_usd",
    "elapsed_seconds",
)

# Colour palette
C_BG        = "#0f0f1a"   # dark navy background
C_PANEL     = "#1a1a2e"   # slightly lighter panel
C_CARD      = "#16213e"   # card background
C_ACCENT    = "#e94560"   # red accent
C_GEMINI    = "#4f8ef7"   # Gemini blue
C_GROQ      = "#00d4aa"   # Groq teal
C_TEXT      = "#e0e0e0"   # main text
C_SUBTEXT   = "#8888aa"   # muted text
C_BORDER    = "#2a2a4a"   # border / separator
C_ENTRY_BG  = "#0d1117"   # entry widget background
C_BTN       = "#e94560"   # button face
C_BTN_HOVER = "#c73652"   # button hover
C_SUCCESS   = "#00d4aa"
C_ERROR     = "#e94560"
C_WARN      = "#f4a261"


class TrackerError(Exception):
    pass


# ---------------------------------------------------------------------------
# Config & pricing helpers (unchanged logic from original tracker.py)
# ---------------------------------------------------------------------------
def load_config() -> dict[str, str]:
    load_dotenv()
    keys = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "gemini_model":   os.getenv("GEMINI_MODEL"),
        "groq_api_key":   os.getenv("GROQ_API_KEY"),
        "groq_model":     os.getenv("GROQ_MODEL"),
    }
    env_name = {
        "gemini_api_key": "GEMINI_API_KEY",
        "gemini_model":   "GEMINI_MODEL",
        "groq_api_key":   "GROQ_API_KEY",
        "groq_model":     "GROQ_MODEL",
    }
    missing = [env_name[k] for k, v in keys.items() if not v]
    if missing:
        raise TrackerError(
            "Missing configuration: " + ", ".join(missing) + ".\n\n"
            "Copy .env.example → .env and fill in your API keys."
        )
    return keys  # type: ignore[return-value]


def resolve_price(provider: str, model: str,
                  in_env: str, out_env: str) -> tuple[float, float]:
    if model in PRICING:
        return PRICING[model]["input"], PRICING[model]["output"]
    in_raw, out_raw = os.getenv(in_env), os.getenv(out_env)
    if in_raw and out_raw:
        try:
            return float(in_raw), float(out_raw)
        except ValueError as exc:
            raise TrackerError(f"Invalid price env vars: {in_env}, {out_env}") from exc
    known = ", ".join(sorted(PRICING))
    raise TrackerError(
        f"No rate for {provider} model {model!r}.\n"
        f"Models with verified rates: {known}."
    )


def compute_cost(input_tokens: int, output_tokens: int,
                 input_price_per_m: float, output_price_per_m: float) -> float:
    return (input_tokens * input_price_per_m
            + output_tokens * output_price_per_m) / 1_000_000


# ---------------------------------------------------------------------------
# API call functions (one per provider)
# ---------------------------------------------------------------------------
def call_gemini(prompt: str, config: dict, prices: tuple[float, float]) -> dict:
    from google import genai
    ip, op = prices
    client = genai.Client(api_key=config["gemini_api_key"])
    t0 = time.perf_counter()
    response = client.models.generate_content(model=config["gemini_model"],
                                               contents=prompt)
    elapsed = time.perf_counter() - t0
    try:
        reply = response.text
    except ValueError:
        raise TrackerError(f"Gemini blocked the request "
                           f"(prompt_feedback={response.prompt_feedback}).")
    if not reply:
        raise TrackerError("Gemini returned an empty reply.")
    usage = response.usage_metadata
    if usage is None:
        raise TrackerError("Gemini response missing usage metadata.")
    if usage.prompt_token_count is None or usage.candidates_token_count is None:
        raise TrackerError("Gemini usage metadata missing token counts.")
    in_tok  = int(usage.prompt_token_count)
    out_tok = int(usage.candidates_token_count) + int(usage.thoughts_token_count or 0)
    return {
        "provider": "gemini", "model": config["gemini_model"],
        "reply": reply,
        "input_tokens": in_tok, "output_tokens": out_tok,
        "input_price_per_m": ip, "output_price_per_m": op,
        "cost_usd": compute_cost(in_tok, out_tok, ip, op),
        "elapsed_seconds": elapsed,
    }


def call_groq(prompt: str, config: dict, prices: tuple[float, float]) -> dict:
    from groq import Groq
    ip, op = prices
    client = Groq(api_key=config["groq_api_key"])
    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=config["groq_model"],
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.perf_counter() - t0
    if not response.choices:
        raise TrackerError("Groq returned no choices.")
    reply = response.choices[0].message.content
    if not reply:
        raise TrackerError("Groq returned an empty reply.")
    usage = response.usage
    if usage is None:
        raise TrackerError("Groq response missing usage data.")
    if usage.prompt_tokens is None or usage.completion_tokens is None:
        raise TrackerError("Groq usage missing token counts.")
    in_tok  = int(usage.prompt_tokens)
    out_tok = int(usage.completion_tokens)
    return {
        "provider": "groq", "model": config["groq_model"],
        "reply": reply,
        "input_tokens": in_tok, "output_tokens": out_tok,
        "input_price_per_m": ip, "output_price_per_m": op,
        "cost_usd": compute_cost(in_tok, out_tok, ip, op),
        "elapsed_seconds": elapsed,
    }


def write_results(all_results: list[dict]) -> Path:
    path = Path(__file__).resolve().parent / "results.json"
    data = [{f: r[f] for f in JSON_FIELDS} for r in all_results]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class TrackerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("IEC Assignment 1 — Two Provider Cost Tracker")
        self.configure(bg=C_BG)
        self.minsize(1100, 700)
        self.resizable(True, True)

        # Try to maximise on startup
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._define_fonts()
        self._build_ui()
        self.all_results: list[dict] = []

    # ------------------------------------------------------------------
    def _define_fonts(self) -> None:
        self.f_title    = tkfont.Font(family="Segoe UI", size=18, weight="bold")
        self.f_heading  = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        self.f_label    = tkfont.Font(family="Segoe UI", size=10)
        self.f_entry    = tkfont.Font(family="Segoe UI", size=10)
        self.f_mono     = tkfont.Font(family="Consolas", size=9)
        self.f_mono_sm  = tkfont.Font(family="Consolas", size=8)
        self.f_btn      = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.f_badge    = tkfont.Font(family="Segoe UI", size=9, weight="bold")

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # ── Header ──────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C_PANEL, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚡  Two Provider Cost Tracker",
                 font=self.f_title, bg=C_PANEL, fg=C_ACCENT).pack(side="left", padx=24)
        tk.Label(hdr, text="Gemini  vs  Groq",
                 font=self.f_label, bg=C_PANEL, fg=C_SUBTEXT).pack(side="left", padx=4)

        # config badge (top-right)
        self._cfg_label = tk.Label(hdr, text="● config OK", font=self.f_badge,
                                   bg=C_PANEL, fg=C_SUBTEXT)
        self._cfg_label.pack(side="right", padx=20)

        # separator
        tk.Frame(self, bg=C_ACCENT, height=2).pack(fill="x")

        # ── Main scrollable canvas ───────────────────────────────────────
        outer = tk.Frame(self, bg=C_BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=C_BG, highlightthickness=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._scroll_frame = tk.Frame(canvas, bg=C_BG)
        self._scroll_win   = canvas.create_window(
            (0, 0), window=self._scroll_frame, anchor="nw"
        )
        self._scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(self._scroll_win, width=e.width),
        )
        # Mouse-wheel scroll
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        content = self._scroll_frame  # everything goes in here

        # ── Prompt input card ────────────────────────────────────────────
        card = self._make_card(content, "📝  Enter Your Prompts")
        self._prompt_vars: list[tk.StringVar] = []
        self._prompt_entries: list[tk.Text] = []

        for i in range(3):
            row = tk.Frame(card, bg=C_CARD)
            row.pack(fill="x", pady=6)

            tk.Label(row, text=f"Prompt {i+1}",
                     font=self.f_heading, bg=C_CARD,
                     fg=[C_GEMINI, C_GROQ, C_WARN][i],
                     width=10, anchor="w").pack(side="left", padx=(0, 10))

            entry = tk.Text(row, height=2, font=self.f_entry,
                            bg=C_ENTRY_BG, fg=C_TEXT,
                            insertbackground=C_TEXT,
                            relief="flat", bd=0,
                            wrap="word",
                            highlightthickness=1,
                            highlightbackground=C_BORDER,
                            highlightcolor=C_ACCENT)
            entry.pack(side="left", fill="x", expand=True, ipady=6)
            self._prompt_entries.append(entry)

        # ── Run button + status bar ───────────────────────────────────────
        btn_row = tk.Frame(card, bg=C_CARD, pady=10)
        btn_row.pack(fill="x")

        self._run_btn = tk.Button(
            btn_row,
            text="▶   Run All Prompts",
            font=self.f_btn,
            bg=C_BTN, fg="white",
            activebackground=C_BTN_HOVER, activeforeground="white",
            relief="flat", bd=0, cursor="hand2",
            padx=28, pady=10,
            command=self._on_run,
        )
        self._run_btn.pack(side="left")

        self._clear_btn = tk.Button(
            btn_row,
            text="✕  Clear",
            font=self.f_label,
            bg=C_BORDER, fg=C_SUBTEXT,
            activebackground=C_PANEL, activeforeground=C_TEXT,
            relief="flat", bd=0, cursor="hand2",
            padx=16, pady=10,
            command=self._on_clear,
        )
        self._clear_btn.pack(side="left", padx=10)

        self._status_var = tk.StringVar(value="Ready — enter three prompts and click Run.")
        tk.Label(btn_row, textvariable=self._status_var,
                 font=self.f_label, bg=C_CARD, fg=C_SUBTEXT,
                 anchor="w").pack(side="left", padx=16)

        # ── Progress bar ─────────────────────────────────────────────────
        self._progress = ttk.Progressbar(card, mode="indeterminate", length=400)
        self._progress.pack(anchor="w", pady=(0, 4))

        # ── Results area (built dynamically per run) ──────────────────────
        self._results_frame = tk.Frame(content, bg=C_BG)
        self._results_frame.pack(fill="both", expand=True, pady=8)

        # ── Footer ───────────────────────────────────────────────────────
        footer = tk.Frame(content, bg=C_PANEL, pady=8)
        footer.pack(fill="x", side="bottom")
        tk.Label(footer,
                 text="Cost = (input_tokens × input_price + output_tokens × output_price) / 1,000,000"
                      "   |   Rates verified Nov 2026   |   Estimates only — free-tier usage may cost $0",
                 font=self.f_mono_sm, bg=C_PANEL, fg=C_SUBTEXT).pack()

        # ── Check config on startup ───────────────────────────────────────
        self.after(200, self._check_config)

    # ------------------------------------------------------------------
    def _make_card(self, parent: tk.Widget, title: str) -> tk.Frame:
        wrapper = tk.Frame(parent, bg=C_BG, pady=6)
        wrapper.pack(fill="x", padx=20, pady=6)

        tk.Label(wrapper, text=title, font=self.f_heading,
                 bg=C_BG, fg=C_TEXT).pack(anchor="w", pady=(0, 6))
        tk.Frame(wrapper, bg=C_BORDER, height=1).pack(fill="x", pady=(0, 10))

        inner = tk.Frame(wrapper, bg=C_CARD, padx=20, pady=16,
                         highlightthickness=1, highlightbackground=C_BORDER)
        inner.pack(fill="x")
        return inner

    # ------------------------------------------------------------------
    def _check_config(self) -> None:
        try:
            cfg = load_config()
            gm = cfg.get("gemini_model", "?")
            gr = cfg.get("groq_model", "?")
            self._cfg_label.configure(
                text=f"● Gemini: {gm}   Groq: {gr}",
                fg=C_SUCCESS,
            )
        except TrackerError as exc:
            self._cfg_label.configure(text="⚠ config error", fg=C_ERROR)
            messagebox.showerror("Configuration Error", str(exc))

    # ------------------------------------------------------------------
    def _get_prompts(self) -> list[str]:
        prompts = []
        for i, entry in enumerate(self._prompt_entries):
            text = entry.get("1.0", "end-1c").strip()
            if not text:
                raise TrackerError(f"Prompt {i+1} is empty. Please enter a prompt.")
            prompts.append(text)
        return prompts

    # ------------------------------------------------------------------
    def _on_clear(self) -> None:
        for entry in self._prompt_entries:
            entry.delete("1.0", "end")
        for widget in self._results_frame.winfo_children():
            widget.destroy()
        self._status_var.set("Ready — enter three prompts and click Run.")
        self.all_results.clear()

    # ------------------------------------------------------------------
    def _on_run(self) -> None:
        try:
            prompts = self._get_prompts()
        except TrackerError as exc:
            messagebox.showwarning("Input Error", str(exc))
            return

        # Clear previous results
        for widget in self._results_frame.winfo_children():
            widget.destroy()
        self.all_results.clear()

        self._run_btn.configure(state="disabled", text="⏳  Running…")
        self._progress.start(12)
        self._status_var.set("Calling APIs… this may take a moment.")

        thread = threading.Thread(target=self._worker, args=(prompts,), daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    def _worker(self, prompts: list[str]) -> None:
        """Run all API calls in a background thread; post results to main thread."""
        try:
            config = load_config()
            gemini_prices = resolve_price(
                "Gemini", config["gemini_model"],
                "GEMINI_INPUT_PRICE_PER_M", "GEMINI_OUTPUT_PRICE_PER_M",
            )
            groq_prices = resolve_price(
                "Groq", config["groq_model"],
                "GROQ_INPUT_PRICE_PER_M", "GROQ_OUTPUT_PRICE_PER_M",
            )
        except TrackerError as exc:
            self.after(0, self._on_error, str(exc))
            return

        all_results: list[dict] = []
        errors: list[str] = []

        total = len(prompts) * 2
        done  = 0

        for idx, prompt in enumerate(prompts, start=1):
            prompt_results: list[dict] = []

            for provider, call_fn, prices in [
                ("Gemini", call_gemini, gemini_prices),
                ("Groq",   call_groq,  groq_prices),
            ]:
                self.after(0, self._status_var.set,
                           f"Prompt {idx}/3 → calling {provider}…")
                try:
                    result = call_fn(prompt, config, prices)
                    result["prompt"] = prompt
                    prompt_results.append(result)
                except Exception as exc:
                    errors.append(f"Prompt {idx} / {provider}: {exc}")
                    # Insert a stub so the table still renders
                    prompt_results.append({
                        "prompt": prompt,
                        "provider": provider.lower(),
                        "model": config.get(f"{provider.lower()}_model", "?"),
                        "reply": f"[ERROR: {exc}]",
                        "input_tokens": 0, "output_tokens": 0,
                        "input_price_per_m": prices[0],
                        "output_price_per_m": prices[1],
                        "cost_usd": 0.0,
                        "elapsed_seconds": 0.0,
                    })
                done += 1
                self.after(0, self._update_progress_label,
                           done, total, idx, provider)

            all_results.extend(prompt_results)
            self.after(0, self._add_prompt_result_card, idx, prompt, prompt_results)

        # Write JSON (all results, even stubs for failed calls)
        try:
            path = write_results(all_results)
            json_msg = f"results.json saved → {path}"
        except Exception as exc:
            json_msg = f"Could not write results.json: {exc}"

        self.all_results = all_results
        self.after(0, self._on_done, errors, json_msg)

    # ------------------------------------------------------------------
    def _update_progress_label(self, done: int, total: int,
                               idx: int, provider: str) -> None:
        self._status_var.set(
            f"Progress: {done}/{total} calls done  "
            f"(Prompt {idx} / {provider} complete)"
        )

    # ------------------------------------------------------------------
    def _on_error(self, msg: str) -> None:
        self._progress.stop()
        self._run_btn.configure(state="normal", text="▶   Run All Prompts")
        self._status_var.set("Error — see message box.")
        messagebox.showerror("Error", msg)

    # ------------------------------------------------------------------
    def _on_done(self, errors: list[str], json_msg: str) -> None:
        self._progress.stop()
        self._run_btn.configure(state="normal", text="▶   Run All Prompts")

        if errors:
            self._status_var.set(f"Done with {len(errors)} error(s). {json_msg}")
            messagebox.showwarning(
                "Some calls failed",
                "\n\n".join(errors) + f"\n\n{json_msg}",
            )
        else:
            self._status_var.set(f"✓ All done!  {json_msg}")
            self._add_summary_card()

    # ------------------------------------------------------------------
    def _add_prompt_result_card(self, idx: int, prompt: str,
                                results: list[dict]) -> None:
        """Add one card per prompt showing both providers' replies + mini table."""
        wrapper = tk.Frame(self._results_frame, bg=C_BG, pady=4)
        wrapper.pack(fill="x", padx=20)

        # Title
        title_row = tk.Frame(wrapper, bg=C_BG)
        title_row.pack(fill="x", pady=(0, 4))
        tk.Label(title_row,
                 text=f"Prompt {idx}",
                 font=self.f_heading, bg=C_BG,
                 fg=[C_GEMINI, C_GROQ, C_WARN][idx - 1]).pack(side="left")
        tk.Label(title_row,
                 text=f'  "{prompt[:90]}{"…" if len(prompt) > 90 else ""}"',
                 font=self.f_label, bg=C_BG, fg=C_SUBTEXT).pack(side="left")
        tk.Frame(wrapper, bg=C_BORDER, height=1).pack(fill="x", pady=(4, 8))

        # Two side-by-side reply panels
        panels = tk.Frame(wrapper, bg=C_BG)
        panels.pack(fill="x")
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)

        for col, r in enumerate(results):
            is_gemini  = r["provider"] == "gemini"
            prov_color = C_GEMINI if is_gemini else C_GROQ
            prov_icon  = "🔵" if is_gemini else "🟢"
            is_error   = r["reply"].startswith("[ERROR:")

            panel = tk.Frame(panels, bg=C_CARD,
                             highlightthickness=1,
                             highlightbackground=prov_color,
                             padx=14, pady=12)
            panel.grid(row=0, column=col, sticky="nsew", padx=(0 if col else 0, 8 if col == 0 else 0))

            # Provider header
            ph = tk.Frame(panel, bg=C_CARD)
            ph.pack(fill="x", pady=(0, 8))
            tk.Label(ph, text=f"{prov_icon}  {r['provider'].upper()}",
                     font=self.f_heading, bg=C_CARD, fg=prov_color).pack(side="left")
            tk.Label(ph, text=r["model"],
                     font=self.f_badge, bg=C_CARD, fg=C_SUBTEXT).pack(side="left", padx=8)

            # Reply text box
            reply_box = scrolledtext.ScrolledText(
                panel, height=8, font=self.f_mono,
                bg=C_ENTRY_BG,
                fg=C_ERROR if is_error else C_TEXT,
                insertbackground=C_TEXT,
                relief="flat", bd=0,
                wrap="word",
            )
            reply_box.insert("1.0", r["reply"])
            reply_box.configure(state="disabled")
            reply_box.pack(fill="both", expand=True, pady=(0, 10))

            # Stats row
            stats = tk.Frame(panel, bg=C_CARD)
            stats.pack(fill="x")
            self._stat_pill(stats, "In",    str(r["input_tokens"]),  C_SUBTEXT)
            self._stat_pill(stats, "Out",   str(r["output_tokens"]), C_SUBTEXT)
            self._stat_pill(stats, "Time",  f"{r['elapsed_seconds']:.2f}s", C_WARN)
            self._stat_pill(stats, "Cost",  f"${r['cost_usd']:.8f}", prov_color)

        # Comparison mini-table below the panels
        self._add_mini_table(wrapper, results)

    # ------------------------------------------------------------------
    def _stat_pill(self, parent: tk.Widget, label: str,
                   value: str, color: str) -> None:
        frame = tk.Frame(parent, bg=C_BORDER, padx=8, pady=4)
        frame.pack(side="left", padx=(0, 6))
        tk.Label(frame, text=label, font=self.f_badge,
                 bg=C_BORDER, fg=C_SUBTEXT).pack(side="left")
        tk.Label(frame, text=f"  {value}", font=self.f_badge,
                 bg=C_BORDER, fg=color).pack(side="left")

    # ------------------------------------------------------------------
    def _add_mini_table(self, parent: tk.Widget, results: list[dict]) -> None:
        frame = tk.Frame(parent, bg=C_PANEL, padx=16, pady=12,
                         highlightthickness=1, highlightbackground=C_BORDER)
        frame.pack(fill="x", pady=(10, 4))

        headers = ["Provider", "Model", "Input tokens", "Output tokens",
                   "Elapsed (s)", "Cost (USD)"]
        col_colors = [C_TEXT, C_SUBTEXT, C_TEXT, C_TEXT, C_WARN, C_SUCCESS]

        # Header row
        for c, (h, clr) in enumerate(zip(headers, col_colors)):
            tk.Label(frame, text=h, font=self.f_badge,
                     bg=C_PANEL, fg=clr,
                     width=16, anchor="w").grid(row=0, column=c, padx=6, pady=2, sticky="w")

        tk.Frame(frame, bg=C_BORDER, height=1).grid(
            row=1, column=0, columnspan=len(headers), sticky="ew", pady=4)

        for r_idx, r in enumerate(results):
            prov_color = C_GEMINI if r["provider"] == "gemini" else C_GROQ
            vals = [
                (r["provider"],               prov_color),
                (r["model"],                  C_SUBTEXT),
                (str(r["input_tokens"]),       C_TEXT),
                (str(r["output_tokens"]),      C_TEXT),
                (f"{r['elapsed_seconds']:.3f}", C_WARN),
                (f"${r['cost_usd']:.8f}",      C_SUCCESS),
            ]
            for c, (v, clr) in enumerate(vals):
                tk.Label(frame, text=v, font=self.f_mono_sm,
                         bg=C_PANEL, fg=clr,
                         width=16, anchor="w").grid(row=r_idx+2, column=c,
                                                     padx=6, pady=1, sticky="w")

    # ------------------------------------------------------------------
    def _add_summary_card(self) -> None:
        """Add a grand-summary table across all prompts after all calls finish."""
        wrapper = tk.Frame(self._results_frame, bg=C_BG, pady=8)
        wrapper.pack(fill="x", padx=20)

        tk.Label(wrapper, text="📊  Grand Summary — All Prompts",
                 font=self.f_heading, bg=C_BG, fg=C_ACCENT).pack(anchor="w")
        tk.Frame(wrapper, bg=C_ACCENT, height=2).pack(fill="x", pady=(4, 10))

        frame = tk.Frame(wrapper, bg=C_PANEL, padx=16, pady=12,
                         highlightthickness=1, highlightbackground=C_ACCENT)
        frame.pack(fill="x")

        headers = ["#", "Provider", "Model", "Prompt (truncated)",
                   "In tok", "Out tok", "Elapsed (s)", "Cost (USD)"]
        for c, h in enumerate(headers):
            tk.Label(frame, text=h, font=self.f_badge,
                     bg=C_PANEL, fg=C_ACCENT,
                     anchor="w").grid(row=0, column=c, padx=8, pady=2, sticky="w")

        tk.Frame(frame, bg=C_ACCENT, height=1).grid(
            row=1, column=0, columnspan=len(headers), sticky="ew", pady=4)

        # Group by prompt index (results arrive in order: gemini then groq per prompt)
        prompt_groups: dict[str, list[dict]] = {}
        for r in self.all_results:
            prompt_groups.setdefault(r["prompt"], []).append(r)

        row_idx = 2
        total_cost = {"gemini": 0.0, "groq": 0.0}

        for p_idx, (prompt, group) in enumerate(prompt_groups.items(), start=1):
            for r in group:
                prov_color = C_GEMINI if r["provider"] == "gemini" else C_GROQ
                total_cost[r["provider"]] = total_cost.get(r["provider"], 0) + r["cost_usd"]
                trunc = prompt[:40] + ("…" if len(prompt) > 40 else "")
                vals = [
                    (str(p_idx),                   C_SUBTEXT),
                    (r["provider"],                 prov_color),
                    (r["model"],                    C_SUBTEXT),
                    (trunc,                         C_TEXT),
                    (str(r["input_tokens"]),         C_TEXT),
                    (str(r["output_tokens"]),        C_TEXT),
                    (f"{r['elapsed_seconds']:.3f}", C_WARN),
                    (f"${r['cost_usd']:.8f}",       C_SUCCESS),
                ]
                for c, (v, clr) in enumerate(vals):
                    tk.Label(frame, text=v, font=self.f_mono_sm,
                             bg=C_PANEL, fg=clr,
                             anchor="w").grid(row=row_idx, column=c,
                                              padx=8, pady=1, sticky="w")
                row_idx += 1

        # Totals row
        tk.Frame(frame, bg=C_BORDER, height=1).grid(
            row=row_idx, column=0, columnspan=len(headers), sticky="ew", pady=6)
        row_idx += 1
        tk.Label(frame, text="TOTAL", font=self.f_badge,
                 bg=C_PANEL, fg=C_ACCENT).grid(row=row_idx, column=0,
                                                columnspan=2, sticky="w", padx=8)
        for prov, color in [("gemini", C_GEMINI), ("groq", C_GROQ)]:
            lbl_txt = f"{prov}: ${total_cost.get(prov, 0.0):.8f}"
            tk.Label(frame, text=lbl_txt, font=self.f_badge,
                     bg=C_PANEL, fg=color).grid(row=row_idx, column=3 if prov == "gemini" else 4,
                                                 sticky="w", padx=8)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    app = TrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
