"""
IEC Assignment 1 - Two Provider Cost Tracker
=============================================
Run:  uv run tracker.py

A simple window opens where you type 3 prompts.
The app sends each prompt to Gemini and Groq,
shows the replies, and saves results to results.json.
"""

import json
import os
import time
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
from pathlib import Path
from dotenv import load_dotenv

# ── Load API keys from .env file ─────────────────────────────────────────────
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY")
GROQ_MODEL     = os.getenv("GROQ_MODEL",   "openai/gpt-oss-120b")

# ── Pricing (USD per 1 million tokens) ───────────────────────────────────────
# Source: https://aistudio.google.com/docs/pricing  &  https://console.groq.com/docs/models
PRICING = {
    "gemini-3.5-flash":    {"input": 0.30, "output": 2.50},
    "gemini-3.5-flash-lite":{"input": 0.30, "output": 2.50},
    "gemini-3.8-flash":    {"input": 0.75, "output": 3.75},
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
    "openai/gpt-oss-20b":  {"input": 0.075,"output": 0.30},
}


# ── Helper: calculate cost ────────────────────────────────────────────────────
def calc_cost(in_tokens, out_tokens, model):
    """Return estimated USD cost for a call."""
    rate = PRICING.get(model, {"input": 0, "output": 0})
    return (in_tokens * rate["input"] + out_tokens * rate["output"]) / 1_000_000


# ── Call Google Gemini ────────────────────────────────────────────────────────
def ask_gemini(prompt):
    """Send prompt to Gemini. Returns (reply, in_tokens, out_tokens, seconds)."""
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    start  = time.perf_counter()
    resp   = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    secs   = round(time.perf_counter() - start, 2)

    reply     = resp.text
    in_tok    = resp.usage_metadata.prompt_token_count or 0
    out_tok   = resp.usage_metadata.candidates_token_count or 0
    # Thinking tokens (if any) are also billed as output
    think_tok = resp.usage_metadata.thoughts_token_count or 0

    return reply, in_tok, out_tok + think_tok, secs


# ── Call Groq ─────────────────────────────────────────────────────────────────
def ask_groq(prompt):
    """Send prompt to Groq. Returns (reply, in_tokens, out_tokens, seconds)."""
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)
    start  = time.perf_counter()
    resp   = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    secs   = round(time.perf_counter() - start, 2)

    reply  = resp.choices[0].message.content
    in_tok = resp.usage.prompt_tokens or 0
    out_tok= resp.usage.completion_tokens or 0

    return reply, in_tok, out_tok, secs


# ── Save results to results.json ──────────────────────────────────────────────
def save_results(all_results):
    """Write all results to results.json next to this file."""
    path = Path(__file__).parent / "results.json"
    path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# GUI
# ═══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("IEC Assignment 1 — Cost Tracker")
        self.configure(bg="#1e1e2e")
        self.geometry("1000x750")
        self.resizable(True, True)
        self._build()

    # ── Build all widgets ──────────────────────────────────────────────────────
    def _build(self):

        # ── Title bar ─────────────────────────────────────────────────────────
        tk.Label(self,
                 text="⚡ Two Provider Cost Tracker  |  Gemini  vs  Groq",
                 font=("Segoe UI", 14, "bold"),
                 bg="#1e1e2e", fg="#cba6f7").pack(pady=(14, 4))

        tk.Label(self,
                 text=f"Gemini model: {GEMINI_MODEL}     Groq model: {GROQ_MODEL}",
                 font=("Segoe UI", 9),
                 bg="#1e1e2e", fg="#6c7086").pack(pady=(0, 10))

        # ── Prompt inputs ──────────────────────────────────────────────────────
        input_frame = tk.Frame(self, bg="#1e1e2e")
        input_frame.pack(padx=20, fill="x")

        self.prompt_boxes = []
        colors = ["#89b4fa", "#a6e3a1", "#fab387"]   # blue, green, orange

        for i in range(3):
            row = tk.Frame(input_frame, bg="#1e1e2e")
            row.pack(fill="x", pady=4)

            tk.Label(row, text=f"Prompt {i+1}",
                     font=("Segoe UI", 10, "bold"),
                     width=9, anchor="w",
                     bg="#1e1e2e", fg=colors[i]).pack(side="left")

            box = tk.Text(row, height=2, font=("Segoe UI", 10),
                          bg="#313244", fg="#cdd6f4",
                          insertbackground="white",
                          relief="flat", wrap="word",
                          highlightthickness=1,
                          highlightbackground=colors[i])
            box.pack(side="left", fill="x", expand=True, ipady=4)
            self.prompt_boxes.append(box)

        # ── Run button + status label ──────────────────────────────────────────
        btn_row = tk.Frame(self, bg="#1e1e2e")
        btn_row.pack(pady=10)

        self.run_btn = tk.Button(btn_row,
                                 text="▶  Run All Prompts",
                                 font=("Segoe UI", 11, "bold"),
                                 bg="#cba6f7", fg="#1e1e2e",
                                 relief="flat", padx=20, pady=8,
                                 cursor="hand2",
                                 command=self._on_run)
        self.run_btn.pack(side="left", padx=(0, 10))

        self.status = tk.Label(btn_row,
                               text="Enter prompts above and click Run.",
                               font=("Segoe UI", 9),
                               bg="#1e1e2e", fg="#6c7086")
        self.status.pack(side="left")

        # ── Scrollable results area ────────────────────────────────────────────
        results_outer = tk.Frame(self, bg="#1e1e2e")
        results_outer.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        scrollbar = tk.Scrollbar(results_outer)
        scrollbar.pack(side="right", fill="y")

        self.canvas = tk.Canvas(results_outer, bg="#1e1e2e",
                                highlightthickness=0,
                                yscrollcommand=scrollbar.set)
        self.canvas.pack(fill="both", expand=True)
        scrollbar.config(command=self.canvas.yview)

        self.results_frame = tk.Frame(self.canvas, bg="#1e1e2e")
        self._canvas_win = self.canvas.create_window((0, 0),
                                                      window=self.results_frame,
                                                      anchor="nw")
        # Keep canvas width in sync with window width
        self.canvas.bind("<Configure>", lambda e: (
            self.canvas.itemconfig(self._canvas_win, width=e.width),
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        ))
        self.results_frame.bind("<Configure>", lambda e:
            self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        # Mouse wheel scroll
        self.canvas.bind_all("<MouseWheel>", lambda e:
            self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    # ── Run button clicked ─────────────────────────────────────────────────────
    def _on_run(self):
        # Read prompts
        prompts = []
        for i, box in enumerate(self.prompt_boxes):
            text = box.get("1.0", "end-1c").strip()
            if not text:
                messagebox.showwarning("Missing prompt",
                                       f"Please fill in Prompt {i+1}.")
                return
            prompts.append(text)

        # Check keys are loaded
        if not GEMINI_API_KEY or not GROQ_API_KEY:
            messagebox.showerror("No API keys",
                                 "GEMINI_API_KEY and GROQ_API_KEY must be set in .env")
            return

        # Clear old results and disable button
        for w in self.results_frame.winfo_children():
            w.destroy()
        self.run_btn.config(state="disabled", text="⏳  Running…")
        self.status.config(text="Calling APIs…", fg="#f9e2af")

        # Run in background so the window doesn't freeze
        threading.Thread(target=self._worker, args=(prompts,), daemon=True).start()

    # ── Background worker: makes all API calls ─────────────────────────────────
    def _worker(self, prompts):
        all_results = []

        for idx, prompt in enumerate(prompts, start=1):
            self.after(0, self.status.config,
                       {"text": f"Calling Gemini for prompt {idx}/3…", "fg": "#89b4fa"})

            # ── Gemini call ───────────────────────────────────────────────────
            try:
                g_reply, g_in, g_out, g_secs = ask_gemini(prompt)
                g_cost = calc_cost(g_in, g_out, GEMINI_MODEL)
                gemini_result = {
                    "prompt":           prompt,
                    "provider":         "gemini",
                    "model":            GEMINI_MODEL,
                    "reply":            g_reply,
                    "input_tokens":     g_in,
                    "output_tokens":    g_out,
                    "input_price_per_m":  PRICING.get(GEMINI_MODEL, {}).get("input",  0),
                    "output_price_per_m": PRICING.get(GEMINI_MODEL, {}).get("output", 0),
                    "cost_usd":         g_cost,
                    "elapsed_seconds":  g_secs,
                }
            except Exception as e:
                gemini_result = {"prompt": prompt, "provider": "gemini",
                                 "model": GEMINI_MODEL, "reply": f"ERROR: {e}",
                                 "input_tokens": 0, "output_tokens": 0,
                                 "input_price_per_m": 0, "output_price_per_m": 0,
                                 "cost_usd": 0, "elapsed_seconds": 0}

            self.after(0, self.status.config,
                       {"text": f"Calling Groq for prompt {idx}/3…", "fg": "#a6e3a1"})

            # ── Groq call ─────────────────────────────────────────────────────
            try:
                r_reply, r_in, r_out, r_secs = ask_groq(prompt)
                r_cost = calc_cost(r_in, r_out, GROQ_MODEL)
                groq_result = {
                    "prompt":           prompt,
                    "provider":         "groq",
                    "model":            GROQ_MODEL,
                    "reply":            r_reply,
                    "input_tokens":     r_in,
                    "output_tokens":    r_out,
                    "input_price_per_m":  PRICING.get(GROQ_MODEL, {}).get("input",  0),
                    "output_price_per_m": PRICING.get(GROQ_MODEL, {}).get("output", 0),
                    "cost_usd":         r_cost,
                    "elapsed_seconds":  r_secs,
                }
            except Exception as e:
                groq_result = {"prompt": prompt, "provider": "groq",
                               "model": GROQ_MODEL, "reply": f"ERROR: {e}",
                               "input_tokens": 0, "output_tokens": 0,
                               "input_price_per_m": 0, "output_price_per_m": 0,
                               "cost_usd": 0, "elapsed_seconds": 0}

            all_results.extend([gemini_result, groq_result])

            # Show this prompt's results in the UI
            self.after(0, self._show_prompt_result, idx, prompt,
                       gemini_result, groq_result)

        # Save to file
        path = save_results(all_results)
        self.after(0, self.status.config,
                   {"text": f"✓ Done!  Saved → {path.name}", "fg": "#a6e3a1"})
        self.after(0, self.run_btn.config,
                   {"state": "normal", "text": "▶  Run All Prompts"})

    # ── Draw one prompt's result card ──────────────────────────────────────────
    def _show_prompt_result(self, idx, prompt, gemini, groq):
        colors = ["#89b4fa", "#a6e3a1", "#fab387"]
        color  = colors[idx - 1]

        # ── Prompt heading ─────────────────────────────────────────────────────
        tk.Label(self.results_frame,
                 text=f"Prompt {idx}: {prompt[:80]}{'…' if len(prompt)>80 else ''}",
                 font=("Segoe UI", 10, "bold"),
                 bg="#1e1e2e", fg=color,
                 anchor="w").pack(fill="x", padx=8, pady=(14, 2))

        tk.Frame(self.results_frame,
                 bg=color, height=1).pack(fill="x", padx=8, pady=(0, 8))

        # ── Two reply panels side by side ──────────────────────────────────────
        pair = tk.Frame(self.results_frame, bg="#1e1e2e")
        pair.pack(fill="x", padx=8, pady=(0, 6))
        pair.columnconfigure(0, weight=1)
        pair.columnconfigure(1, weight=1)

        for col, result in enumerate([gemini, groq]):
            prov   = result["provider"]
            pcolor = "#89b4fa" if prov == "gemini" else "#a6e3a1"

            panel = tk.Frame(pair, bg="#313244",
                             highlightthickness=1,
                             highlightbackground=pcolor)
            panel.grid(row=0, column=col, sticky="nsew",
                       padx=(0, 6) if col == 0 else (6, 0))

            # Provider label
            tk.Label(panel,
                     text=f"{'🔵 GEMINI' if prov=='gemini' else '🟢 GROQ'}  "
                          f"({result['model']})",
                     font=("Segoe UI", 9, "bold"),
                     bg="#313244", fg=pcolor,
                     anchor="w").pack(fill="x", padx=10, pady=(8, 4))

            # Reply text box
            box = tk.Text(panel, height=7,
                          font=("Consolas", 9),
                          bg="#1e1e2e", fg="#cdd6f4",
                          relief="flat", wrap="word",
                          state="normal")
            box.insert("1.0", result["reply"])
            box.config(state="disabled")
            box.pack(fill="x", padx=10, pady=(0, 6))

            # Stats row
            stats = (
                f"In: {result['input_tokens']} tok  "
                f"Out: {result['output_tokens']} tok  "
                f"Time: {result['elapsed_seconds']}s  "
                f"Cost: ${result['cost_usd']:.8f}"
            )
            tk.Label(panel,
                     text=stats,
                     font=("Consolas", 8),
                     bg="#313244", fg="#f9e2af",
                     anchor="w").pack(fill="x", padx=10, pady=(0, 10))

        # ── Comparison table ───────────────────────────────────────────────────
        table_frame = tk.Frame(self.results_frame, bg="#181825")
        table_frame.pack(fill="x", padx=8, pady=(0, 4))

        headers = ["Provider", "In tokens", "Out tokens", "Time (s)", "Cost (USD)"]
        col_w   = [12, 12, 12, 12, 18]

        # Header row
        for c, (h, w) in enumerate(zip(headers, col_w)):
            tk.Label(table_frame, text=h,
                     font=("Consolas", 8, "bold"),
                     width=w, anchor="w",
                     bg="#181825", fg="#cba6f7").grid(row=0, column=c,
                                                       padx=4, pady=4,
                                                       sticky="w")
        # Data rows
        for r_idx, result in enumerate([gemini, groq], start=1):
            pc = "#89b4fa" if result["provider"] == "gemini" else "#a6e3a1"
            row_vals = [
                result["provider"],
                str(result["input_tokens"]),
                str(result["output_tokens"]),
                str(result["elapsed_seconds"]),
                f"${result['cost_usd']:.8f}",
            ]
            for c, (v, w) in enumerate(zip(row_vals, col_w)):
                tk.Label(table_frame, text=v,
                         font=("Consolas", 8),
                         width=w, anchor="w",
                         bg="#181825",
                         fg=pc if c == 0 else "#cdd6f4").grid(
                             row=r_idx, column=c, padx=4, pady=2, sticky="w")


# ── Run the app ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
