# Approach & Limitations Note: Task 2 (AI Test Runner)

**Candidate:** Kartik  
**Task:** Turn plain-English test cases into automated tests  
**Technology:** Python, Playwright, Multimodal AI (OpenAI GPT-4o / Groq / OpenAI-compatible LLMs)

---

## 1. High-Level Approach

Traditional automated tests (Selenium/Playwright scripts) require hardcoded selectors (`#submit-btn`, `//button[@type='submit']`), rigid navigation steps, and brittle assertion logic. When UI structures change or when writing tests from business requirements, traditional automation creates maintenance overhead.

This project implements an **autonomous agentic loop** that translates natural language intentions into browser actions in real time:

```
┌─────────────────────────────────────────────────────────────┐
│                      AGENTIC TEST LOOP                      │
│                                                             │
│  1. OBSERVE   ──▶ Read active page URL, title, DOM          │
│                   interactive tree, & take screenshot       │
│                                                             │
│  2. ORIENT    ──▶ Compare current page state against test   │
│                   goal; maintain chronological action history│
│                                                             │
│  3. DECIDE    ──▶ AI generates chain-of-thought reasoning   │
│                   and emits a single structured JSON action │
│                                                             │
│  4. ACT       ──▶ Playwright executes the action (click,    │
│                   fill, select, scroll, navigate) with      │
│                   multi-layer resilience fallbacks          │
│                                                             │
│  5. VERIFY    ──▶ AI confirms expected assertion state;     │
│                   emits PASS/FAIL verdict with clear reason │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Key Architectural Decisions

### A. Dual Perception: Structured DOM + Visual Grounding
- Rather than feeding raw, noisy HTML into the LLM (which wastes tokens and confuses reasoning), a client-side JavaScript extractor identifies all semantic and interactive elements (`a`, `button`, `input`, `select`, ARIA roles) and assigns each an ephemeral index (`[data-test-ai-idx="N"]`).
- For vision-capable models (e.g. GPT-4o), full-viewport screenshots are attached alongside the indexed DOM list. This gives the model both **spatial/visual awareness** (layout, styling, overlays) and **deterministic element targeting** (exact DOM index).

### B. Index-Based Targeting Over Dynamic Selector Generation
- Asking an LLM to generate XPath or CSS selectors on the fly often produces brittle or invalid queries.
- By stamping elements with an integer index and passing `[0] <button> text="Sign in"`, the model simply responds with `{"action": "click", "params": {"index": 0}}`. Playwright then immediately targets `[data-test-ai-idx="0"]`.

### C. Multi-Layer Action Fallbacks
Real-world websites like `phptravels.com` have floating headers, dynamic modals, and non-standard markup. Actions are wrapped with defensive fallbacks:
- **Click**: Standard Playwright click ➔ Force click (bypassing element interceptors) ➔ JavaScript `el.click()` dispatch.
- **Input Fill**: Standard `fill()` ➔ Sequential keystroke typing ➔ JavaScript input/change event dispatch.
- **Multi-Tab Tracking**: Automatically detects when links open new tabs/windows (`target="_blank"`) and repoints active execution to the frontmost page.

### D. Provider Agnostic (Zero Hardcoding)
- Built on top of the standard OpenAI client SDK, making it compatible with OpenAI (GPT-4o, GPT-4o-mini), Groq (`openai/gpt-oss-120b`), Google Gemini (via OpenAI-compatible endpoint), Ollama (local Llama models), or OpenRouter.
- Built-in automatic fallback: If a chosen model does not support multimodal vision, it gracefully switches to DOM-only mode without crashing.

---

## 3. Verified Against Real Websites

1. **PHPTravels Demo (`https://phptravels.com/demo`)**:
   - Tested multi-step test: *"Click on Pricing in the navigation and verify the pricing plans are displayed"*.
   - The agent successfully identified the navigation link, transitioned to the pricing page, evaluated the plan tiers ("Startup, Agency, Enterprise"), and declared **PASS** with full visual artifacts.
2. **Arbitrary Sites (`https://example.com`, forms, searches)**:
   - Successfully proved that zero website-specific selectors or heuristics are hardcoded in the codebase.
3. **Negative Assertion Tests**:
   - Tested impossible conditions (e.g., verifying a nonexistent button); the agent correctly analyzed the page, failed safely, and exited with status code 1.

---

## 4. Limitations & Edge Cases

An honest understanding of limitations is essential for deploying AI testing in production:

| Limitation | Impact | Mitigation / Recommended Solution |
| :--- | :--- | :--- |
| **API Latency** | Each step takes 1–3 seconds for model inference compared to milliseconds for hardcoded tests. | Use fast inference providers (e.g. Groq, GPT-4o-mini); run tests asynchronously or overnight. |
| **Non-Deterministic Reasoning** | Temperature is set low (0.1), but probabilistic outputs can occasionally produce different action paths. | Implement step-level retries and validation checkpoints; enforce strict JSON response formatting. |
| **iframes & Shadow DOM** | Cross-origin iframes and isolated shadow trees hide elements from standard query selectors. | Enhance the JS DOM extractor to traverse accessible iframe document contexts and shadow roots recursively. |
| **Canvas & WebGL** | Canvas-rendered interfaces (e.g. Google Maps, Figma-style apps) have no DOM nodes. | Rely purely on visual bounding boxes / coordinates using vision models (e.g., coordinate clicking). |
| **Token Consumption on Heavy Pages** | Large enterprise pages with 1,000+ interactive nodes exceed context windows. | Filter viewport-visible elements only; paginate element extraction based on scroll position. |
| **CAPTCHAs & Bot Protection** | Cloudflare / Turnstile challenges deliberately block automated browsers. | Use testing/staging environments with bot protection bypassed or configured with whitelisted test tokens. |

---

## 5. Conclusion

This tool proves that LLM-driven browser automation can bridge the gap between human test specifications and executable browser tests. It requires zero test code maintenance when UI layouts change and works out-of-the-box on previously unseen web applications.
