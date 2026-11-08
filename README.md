# Autonomous Browser QA Agent (Task 2)

An autonomous, multi-provider AI test runner that turns plain-English test descriptions into fully executed browser tests using Playwright and Large Language Models.

---

## Overview

Traditional test automation frameworks rely on brittle, hardcoded CSS selectors or XPath expressions that break whenever layouts shift, IDs change, or components are refactored.

This solution implements a closed-loop **autonomous browser agent**:
1. It ingests an arbitrary test objective written in plain natural language (e.g., *"Click on Pricing in the navigation and verify the pricing plans are displayed"*).
2. It perceives the live browser page state using both **spatial screenshots** and a **dynamically indexed semantic DOM tree**.
3. It reasons turn-by-turn to plan and execute actions (clicks, inputs, selections, navigation) using multi-tier defensive fallbacks.
4. It halts only when the test objective is verified, emitting visual audit screenshots and structured JSON test results.

---

## Architecture

```
 ┌────────────────────────────────────────────────────────┐
 │                   AGENTIC CONTROL LOOP                 │
 └──────────────────────────┬─────────────────────────────┘
                            │
               1. Launch & Navigate (Playwright)
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │                   PAGE PERCEPTION                      │
 │  • Inject client-side JS DOM indexer                   │
 │  • Priority classification: forms & buttons first      │
 │  • Ephemeral element stamps: [data-test-ai-idx="N"]    │
 │  • Viewport screenshot capture (multimodal grounding)  │
 └──────────────────────────┬─────────────────────────────┘
                            │
               2. Structured State + Action History
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │                  REASONING ENGINE                      │
 │  • LLM Inference (OpenAI / Groq / Gemini / Ollama)     │
 │  • Chain-of-thought evaluation                         │
 │  • Anti-premature-pass guardrails                      │
 │  • Structured JSON action: {"action": "...", ...}      │
 └──────────────────────────┬─────────────────────────────┘
                            │
               3. Resilient Action Dispatch
                            │
                            ▼
 ┌────────────────────────────────────────────────────────┐
 │                 BROWSER DISPATCHER                     │
 │  • Primary: Playwright native locator action           │
 │  • Fallback 1: Force action (bypasses overlays)        │
 │  • Fallback 2: Direct JavaScript DOM event dispatch    │
 │  • Automatic multi-tab / popup window tracking         │
 └──────────────────────────┬─────────────────────────────┘
                            │
                            ▼
                Test Objective Complete?
               ├── No  ──▶ Repeat Loop
               └── Yes ──▶ Save Artifacts & Report PASS/FAIL
```

---

## Key Engineering Innovations

### 1. Index-Based Dynamic Grounding
Instead of asking the LLM to invent fragile XPath or CSS selectors on the fly, a lightweight in-page JavaScript crawler assigns temporary integer indices (`data-test-ai-idx="0"`, `"1"`, ...) to all interactive elements. The AI returns an exact element index, making interaction 100% deterministic.

### 2. Token-Optimized Perception
Enterprise pages often have thousands of DOM nodes that exceed token limits. The crawler prioritizes high-value form inputs and buttons first, truncates verbose text, and caps the payload at ~65 elements (~650 tokens per step). This prevents rate limits while preserving complete actionable state.

### 3. Anti-Hallucination & Verification Guardrails
- **Anti-Premature Pass Guard:** If a test case requires interaction (`click`, `fill`, `submit`), the runner programmatically intercepts and rejects any `done: pass` emitted before physical actions occur.
- **Form Completeness:** Forces the agent to step through all relevant form fields before declaring completion.
- **Two-Turn Outcome Verification:** Actions (like form submission) must be verified on the subsequent turn by inspecting confirmation messages or destination URLs.

### 4. Resilient Action Fallbacks
Real-world sites feature floating headers and dynamic overlays. If a standard Playwright action fails, the runner automatically escalates to a forced action, and finally to a direct JavaScript event dispatch (`el.dispatchEvent(new Event('input'))`).

### 5. Multi-Tab Awareness
Automatically detects when links open in new tabs (`target="_blank"`) and shifts active execution to the newest page context.

### 6. Interactive Inspection Pause
When executed in non-headless mode, the browser stays open after test completion so the tester can inspect the page state. Pressing `Enter` in the terminal cleanly shuts down the session.

---

## Project Structure

```
.
├── ai_test_runner/
│   ├── __init__.py
│   ├── agent.py                 # Multi-provider reasoning agent & prompt engine
│   └── browser.py               # Playwright controller & resilient DOM crawler
├── examples/
│   ├── sample_tests.txt         # Pre-configured test cases
│   └── suite.json               # Batch test suite definition
├── run_test.py                  # CLI runner for individual test cases
├── run_suite.py                 # Batch runner for test suites
├── APPROACH_AND_LIMITATIONS.md  # Detailed technical notes & limitation analysis
├── RECORDING_SCRIPT.md          # 5-minute walkthrough presentation script
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment configuration template
└── .gitignore                   # Secrets and artifact ignore rules
```

---

## Installation & Setup

### 1. Prerequisites
- Python 3.9+
- An API key for your chosen LLM provider (OpenAI, Groq, Google Gemini, or a local Ollama instance)

### 2. Clone Repository
```bash
git clone https://github.com/beauarn/task_2.git
cd task_2
```

### 3. Install Dependencies & Playwright Browser
```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 4. Configure Environment
Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your preferred configuration:

**For Groq (Default / High Speed):**
```env
OPENAI_API_KEY=gsk_your_groq_key_here
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=openai/gpt-oss-120b
```

**For OpenAI:**
```env
OPENAI_API_KEY=sk-your_openai_key_here
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=
```

---

## Usage

### Single Test Execution

Run a plain-English test against any website:

```bash
python run_test.py \
  --url "https://phptravels.com/demo" \
  --test "Click on Pricing in the navigation and verify the pricing plans are displayed"
```

### Headless Mode (CI / Background)

Run tests silently without spawning a visible browser window:

```bash
python run_test.py \
  --url "https://phptravels.com/demo" \
  --test "Verify the demo page loads and contains links to live demo" \
  --headless
```

### Form Filling Test

```bash
python run_test.py \
  --url "https://phptravels.com/demo" \
  --test "fill the form by the name of kartik and other gibberish values"
```

### Batch Suite Execution

Execute an entire test suite defined in JSON:

```bash
python run_suite.py --suite examples/suite.json --headless
```

---

## CLI Options Reference

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--url` | String | *Required* | Starting URL for the test session |
| `--test` | String | *Required* | Test case description written in plain English |
| `--model` | String | `.env` / `gpt-4o` | LLM model identifier |
| `--base-url` | String | `.env` / OpenAI | Custom API endpoint (Groq, Ollama, Gemini) |
| `--api-key` | String | `OPENAI_API_KEY` | Provider API authentication key |
| `--no-vision` | Flag | `False` | Force text-only DOM mode (skips screenshots) |
| `--headless` | Flag | `False` | Run browser in headless mode (no GUI window) |
| `--auto-close` | Flag | `False` | Skip terminal pause and close browser automatically |
| `--max-steps` | Integer | `25` | Step budget before safety timeout |
| `--output-dir` | String | `results` | Output directory for audit screenshots and JSON logs |

---

## Test Artifacts & Audit Logs

Every test run generates a timestamped directory inside `results/`:

```
results/
└── 20261109_031455/
    ├── step_00_initial.png      # Baseline page load screenshot
    ├── step_01.png              # State after action 1
    ├── step_02.png              # State after action 2
    ├── step_08_final.png        # Final verification screenshot
    └── result.json              # Machine-readable test execution report
```

### Structured Output Schema (`result.json`)
```json
{
  "result": "pass",
  "reason": "All form fields filled with values and submitted successfully",
  "steps_taken": 8,
  "test_case": "fill the form by the name of kartik and other gibberish values",
  "url": "https://phptravels.com/demo",
  "history": [
    {
      "step": 1,
      "action": "fill",
      "params": {"index": 7, "text": "kartik"},
      "thought": "Start filling the form: first fill the First Name field with 'kartik'",
      "success": true,
      "message": "Filled element [7] with 'kartik'"
    }
  ]
}
```

---

## Verified Test Benchmarks

| Target Application | Test Scenario | Steps | Verdict |
| :--- | :--- | :---: | :---: |
| `phptravels.com/demo` | Navigation to Pricing & plan tier verification | 2 | **PASS** |
| `phptravels.com/demo` | Multi-field form completion & submission | 8 | **PASS** |
| `example.com` | Title verification & documentation link click | 1 | **PASS** |
| `example.com` | Negative test: Nonexistent button verification | 1 | **FAIL (Expected)** |

---

## Limitations

For a full discussion on trade-offs, token costs, iframe encapsulation, and CAPTCHA boundaries, refer to [`APPROACH_AND_LIMITATIONS.md`](APPROACH_AND_LIMITATIONS.md).

---

## License

MIT License. Open source for interview evaluation and commercial adaptation.
