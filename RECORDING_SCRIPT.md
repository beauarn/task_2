# 5-Minute Screen Recording Walkthrough Script

Use this script to record your 5-minute submission video for Arun.

---

### Setup Before You Start Recording:
1. Open your terminal in `D:\task2` with your virtual environment or Python ready.
2. Have your code editor (VS Code / Cursor / IDE) open showing the project structure.
3. Keep a browser window handy to show the generated test screenshots.

---

### [0:00 - 0:45] Introduction & Goal
**What to show:** Show your code editor with the project structure (`ai_test_runner`, `run_test.py`, `README.md`).

**What to say:**
> *"Hi Arun and team, my name is Kartik. Today I'm presenting my solution for Task 2: Turning plain-English test cases into automated browser tests.*  
> *The objective was to create a tool that takes a natural language instruction—like 'Click on Pricing and verify the pricing plans are displayed'—and executes it in a real browser without any hardcoded selectors or site-specific assumptions.*  
> *I built this using Python, Playwright for browser control, and an autonomous AI agent loop compatible with OpenAI GPT-4o, Groq, or any OpenAI-compatible multimodal endpoint."*

---

### [0:45 - 1:45] Architecture & How It Works
**What to show:** Show `ai_test_runner/browser.py` and `ai_test_runner/agent.py`.

**What to say:**
> *"Here is how the architecture works under the hood:*  
> *Instead of asking the AI to guess fragile CSS or XPath selectors, my tool uses an agentic perception loop:*  
> *1. When a page loads, Playwright executes a lightweight JavaScript snippet that extracts all semantic and interactive elements—like buttons, links, inputs, and ARIA roles.*  
> *2. Each element is stamped with a temporary integer index: `[data-test-ai-idx='N']`.*  
> *3. The AI receives both this clean, indexed DOM tree and a visual screenshot of the viewport.*  
> *4. The AI returns a structured JSON action—such as `click index 12` or `fill index 3`—with chain-of-thought reasoning.*  
> *5. Playwright executes the action using multi-layer fallbacks: if an element is covered by a floating header, it automatically falls back to force-click or JavaScript event dispatch.*  
> *6. When the expected outcome is verified, the AI concludes with a PASS or FAIL verdict and saves visual proof."*

---

### [1:45 - 3:00] Live Demo 1: PHPTravels Demo Site
**What to show:** Open your terminal and run the test against `phptravels.com/demo`:

```bash
python run_test.py --url "https://phptravels.com/demo" --test "Click on Pricing in the navigation and verify the pricing plans are displayed"
```

**What to say:**
> *"Let's run a test on the PHPTravels demo site requested in the prompt.*  
> *Notice I'm giving it a pure plain-English test case: 'Click on Pricing in the navigation and verify the pricing plans are displayed'.*  
> *The browser launches, navigates to PHPTravels, inspects the interactive elements, identifies the 'Pricing' link at index 12, and clicks it.*  
> *On the new page, it analyzes the pricing tiers—recognizing 'Startup', 'Agency', and 'Enterprise'—and immediately concludes with a PASS.*  
> *Notice that every step captures full screenshots and saves a structured `result.json` artifact in the `results/` folder."*

---

### [3:00 - 3:45] Live Demo 2: Negative Test / Zero Hardcoding
**What to show:** In the terminal, run a negative test on another site to prove failure detection:

```bash
python run_test.py --url "https://example.com" --test "Verify that the page contains a button called 'Sign in as Astronaut'" --headless --max-steps 3
```

**What to say:**
> *"To prove this tool isn't hardcoded and can detect real test failures, let's run an impossible assertion on example.com:*  
> *The AI inspects the page, realizes no such button exists, and reports a clean FAIL verdict with exit code 1.*  
> *We also support running batch test suites using `run_suite.py` with a JSON configuration file."*

---

### [3:45 - 4:45] Approach & Honest Limitations
**What to show:** Open `APPROACH_AND_LIMITATIONS.md` in the editor.

**What to say:**
> *"I've also documented a detailed note on my approach and its limitations:*  
> *First, latency: because each step requires an LLM inference call, agentic tests take a couple of seconds per step compared to pure code-based tests.*  
> *Second, dynamic iframes and canvas elements: elements inside cross-domain iframes or canvas graphs require coordinate-based clicking or frame-tree traversal.*  
> *Third, bot protection: real-world sites with CAPTCHAs or Cloudflare require whitelisted test environments.*  
> *The key advantage, however, is maintainability: tests never break when IDs, classes, or layouts change, and anyone on the team can write tests in plain English."*

---

### [4:45 - 5:00] Closing
**What to say:**
> *"Both task repositories are available on GitHub with complete READMEs and reproducible setup instructions. Thank you for your time and the opportunity, and I look forward to discussing my approach in the interview!"*
