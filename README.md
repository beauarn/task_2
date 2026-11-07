# AI Test Runner

> Turn plain-English test cases into automated browser tests, powered by AI.

**AI Test Runner** takes a test case written in natural language — like *"Log in as a customer and verify the dashboard is shown"* — and executes it automatically in a real browser. It observes the page, decides what to do next, performs the action, and reports whether the test passed or failed.

---

## How It Works

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  Plain-English│────▶│   AI Agent    │────▶│   Browser    │
│  Test Case    │     │  (GPT-4o)    │     │ (Playwright) │
└──────────────┘     └───────┬───────┘     └──────┬───────┘
                             │                     │
                             │   "click [5]"       │
                             │────────────────────▶│
                             │                     │
                             │◀────────────────────│
                             │  new page state +   │
                             │  screenshot         │
                             │                     │
                             │  ... repeat ...     │
                             │                     │
                     ┌───────▼───────┐             │
                     │  ✅ PASS or   │             │
                     │  ❌ FAIL      │             │
                     └───────────────┘
```

**Step-by-step:**

1. The tool launches a Chromium browser and navigates to the target URL
2. It extracts all interactive elements from the page (buttons, links, inputs, etc.) and takes a screenshot
3. Both the element list and the screenshot are sent to GPT-4o along with the test case
4. The AI decides the next action (click, type, navigate, scroll, etc.)
5. The tool executes that action in the browser
6. Steps 2–5 repeat until the AI concludes the test as **PASS** or **FAIL**
7. Screenshots are saved for every step, creating a visual record

## Quick Start

### 1. Prerequisites

- **Python 3.9+**
- **An OpenAI API key** with access to `gpt-4o` (or another vision-capable model)

### 2. Install

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/ai-test-runner.git
cd ai-test-runner

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 3. Configure

```bash
# Copy the example env file
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux

# Edit .env and add your OpenAI API key
```

Your `.env` file should contain:
```
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_MODEL=gpt-4o
```

### 4. Run

```bash
python run_test.py \
  --url "https://phptravels.com/demo" \
  --test "Verify the demo page loads and shows pricing or product information"
```

## Usage

```
python run_test.py --url <URL> --test <TEST_CASE> [OPTIONS]
```

| Argument       | Required | Description                                       |
|----------------|----------|---------------------------------------------------|
| `--url`        | Yes      | Starting URL for the test                         |
| `--test`       | Yes      | Test case in plain English                        |
| `--model`      | No       | AI model to use (default: from `.env` or `gpt-4o`)|
| `--headless`   | No       | Run browser without a visible window              |
| `--max-steps`  | No       | Max actions before timeout (default: 25)          |
| `--output-dir` | No       | Where to save screenshots and logs (default: `results`) |

### Examples

```bash
# Verify a page loads correctly
python run_test.py \
  --url "https://example.com" \
  --test "Verify the page shows a heading that says 'Example Domain'"

# Test a login flow
python run_test.py \
  --url "https://demo-site.com/login" \
  --test "Log in with email 'user@test.com' and password 'pass123', then verify the dashboard loads"

# Run headless (no browser window)
python run_test.py \
  --url "https://phptravels.com/demo" \
  --test "Check that the page displays travel-related content" \
  --headless
```

## Output

Each test run creates a timestamped folder in `results/` containing:

```
results/
└── 20241107_143022/
    ├── step_00_initial.png     # Initial page load
    ├── step_01.png             # After step 1
    ├── step_02.png             # After step 2
    ├── ...
    ├── step_05_final.png       # Final state
    └── result.json             # Structured test result
```

The `result.json` includes the verdict, reasoning, and full action history:

```json
{
  "result": "pass",
  "reason": "Successfully verified the dashboard displays the user's name and recent activity",
  "steps_taken": 4,
  "test_case": "Log in and verify the dashboard is shown",
  "url": "https://demo-site.com",
  "history": [...]
}
```

## Architecture

```
ai_test_runner/
├── __init__.py
├── agent.py         # AI agent: sends page state to GPT-4o, gets next action
└── browser.py       # Browser controller: Playwright wrapper + DOM extraction
```

| Component           | Responsibility                                                   |
|---------------------|------------------------------------------------------------------|
| **`run_test.py`**   | CLI entry point, orchestrates the test loop                     |
| **`agent.py`**      | Communicates with GPT-4o; builds prompts, parses action responses |
| **`browser.py`**    | Manages Playwright browser; extracts DOM elements; executes actions |

### Key Design Decisions

- **DOM extraction + screenshots**: The AI gets *both* a structured list of interactive elements (with indices) *and* a visual screenshot. The DOM list enables precise element targeting; the screenshot provides visual context for layout understanding.
- **Element indexing**: Each interactive element is assigned a `data-test-ai-idx` attribute. The AI references elements by index, and the browser targets them via `[data-test-ai-idx="N"]`. This is more reliable than generating CSS/XPath selectors.
- **Conversation memory**: The agent maintains a rolling conversation history so it can reference earlier actions and adapt its strategy.
- **Low-temperature generation**: `temperature=0.1` for consistent, deterministic actions.

## Approach & Limitations

### Approach

This tool implements an **agentic loop** pattern: the AI observes the page state, reasons about what to do, takes one action, and observes the result. This mirrors how a human tester would work — look at the page, decide what to click, check what happened.

The combination of **structured DOM data** (for precise element identification) and **visual screenshots** (for layout understanding) gives the AI a rich understanding of the page, making it effective across different websites without any site-specific configuration.

### Limitations

1. **API cost**: Each step makes a GPT-4o API call with an image. A 10-step test costs roughly $0.05–0.15 depending on page complexity.
2. **Speed**: Each step takes 2–5 seconds (mostly API latency). A full test typically takes 30–90 seconds.
3. **Complex multi-page flows**: Very long test scenarios (10+ steps) may occasionally lose context or get confused. Breaking them into smaller test cases helps.
4. **iframes**: The DOM extractor currently operates on the main frame only. Content inside iframes is not extracted.
5. **File uploads & native dialogs**: Browser-native dialogs (file picker, print dialog, alerts) are not currently handled.
6. **Highly dynamic SPAs**: Pages with rapid DOM updates or heavy animations may cause stale element indices between extraction and action.
7. **CAPTCHA / anti-bot**: Cannot bypass CAPTCHAs or bot detection (by design).
8. **AI judgment**: The AI may occasionally misinterpret ambiguous test cases or make wrong assertions. Writing clear, specific test cases improves reliability.

### Future Improvements

- **Multi-model support**: Add Gemini, Claude, or local models as alternatives to OpenAI
- **Parallel test execution**: Run multiple test cases concurrently
- **Retry logic**: Automatically retry failed actions before giving up
- **HTML report generation**: Generate visual HTML reports with embedded screenshots
- **iframe support**: Extract and interact with iframe content

## Running Multiple Test Cases

Use `run_suite.py` to run a batch of test cases from a JSON file:

```bash
python run_suite.py --suite examples/suite.json
```

Suite file format (`suite.json`):
```json
{
    "tests": [
        {
            "name": "Homepage loads",
            "url": "https://example.com",
            "test": "Verify the page shows a heading",
            "max_steps": 10
        }
    ]
}
```

## License

MIT
