"""
AI Agent - Interfaces with OpenAI, Groq, Ollama, Gemini or any OpenAI-compatible API
to interpret plain-English test cases and decide actions.

The agent receives the current page state (DOM elements + screenshot) and decides
what action to take next to fulfill the plain-English test case.
"""

import json
import base64
import time
from openai import OpenAI

SYSTEM_PROMPT = """You are an expert QA automation agent controlling a web browser. Your job is to execute test cases written in plain English by interacting with web pages step by step.

## How It Works
Each turn, you receive:
1. The TEST CASE to execute
2. The current page URL and title  
3. A list of INTERACTIVE ELEMENTS on the page (each with an index number)
4. A SCREENSHOT of the current page (if vision is enabled)
5. The HISTORY of actions you've already taken

You must choose ONE action to perform, then wait for the result.

## Available Actions

```json
{"action": "click", "params": {"index": 5}}
```
Click the element at the given index.

```json
{"action": "fill", "params": {"index": 3, "text": "hello@example.com"}}
```
Clear an input field and type new text into it.

```json
{"action": "select", "params": {"index": 7, "option": "California"}}
```
Select an option from a <select> dropdown by its visible text.

```json
{"action": "navigate", "params": {"url": "https://example.com/page"}}
```
Navigate the browser to a new URL.

```json
{"action": "press", "params": {"key": "Enter"}}
```
Press a keyboard key (Enter, Tab, Escape, ArrowDown, etc.).

```json
{"action": "hover", "params": {"index": 2}}
```
Hover over an element (useful for revealing menus).

```json
{"action": "scroll", "params": {"direction": "down"}}
```
Scroll the page up or down.

```json
{"action": "wait", "params": {"seconds": 3}}
```
Wait for the page to load or update.

```json
{"action": "done", "params": {"result": "pass", "reason": "Successfully verified expected outcome"}}
```
Conclude the test. Result must be "pass" or "fail".

## Rules

1. **One action per response.** Always return exactly one action as JSON.
2. **Think before acting.** Include a short "thought" field explaining your reasoning.
3. **Reference elements by index.** Use the [index] from the element list.
4. **Verify before concluding.** Don't mark "pass" until you've verified the expected outcome on the page.
5. **Handle failures gracefully.** If an action fails, try an alternative approach. Only mark "fail" if impossible.
6. **Be concise.** Keep thoughts short and actionable.
7. **Maximum steps.** Be efficient.

## Response Format

Always respond with ONLY a JSON object (no markdown fences, no extra text):

{
    "thought": "I need to click the Login button to proceed",
    "action": "click",
    "params": {"index": 5}
}
"""


class AIAgent:
    """AI agent that interprets test cases and decides browser actions."""

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str = None, use_vision: bool = True):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
            if "groq.com" in base_url.lower() and "vision" not in model.lower():
                use_vision = False
        self.client = OpenAI(**kwargs)
        self.model = model
        self.use_vision = use_vision

    def decide_action(self, test_case: str, page_state: dict, screenshot_b64: str, history: list) -> dict:
        """
        Given the current page state and test case, decide the next action.

        Args:
            test_case: The plain-English test case
            page_state: Dict with 'url', 'title', 'elements' 
            screenshot_b64: Base64-encoded PNG screenshot
            history: List of previous actions taken

        Returns:
            Dict with 'thought', 'action', 'params'
        """
        user_prompt = self._build_prompt(test_case, page_state, history)

        # Build message content
        if self.use_vision and screenshot_b64:
            content = [
                {"type": "text", "text": user_prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_b64}",
                        "detail": "low"
                    }
                }
            ]
        else:
            content = user_prompt

        # Self-contained prompt:
        # History is already summarized in user_prompt under ## ACTION HISTORY.
        # Keeping messages stateless prevents exponential token accumulation across steps.
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ]

        raw_response = self._call_llm_with_retry(messages, user_prompt)
        return self._parse_response(raw_response)

    def _call_llm_with_retry(self, messages: list, user_prompt: str, max_retries: int = 3) -> str:
        """Call LLM with fallback for vision and retry on rate-limits (TPM/RPM)."""
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=800,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                err_str = str(e).lower()

                # If vision not supported, switch to text-only DOM immediately
                if self.use_vision and any(term in err_str for term in ["image", "vision", "multimodal", "content_type", "unsupported", "must be a string", "400"]):
                    self.use_vision = False
                    messages[-1]["content"] = user_prompt
                    continue

                # If rate-limited (413 or 429), wait and retry
                if any(term in err_str for term in ["413", "429", "rate limit", "too large", "tpm", "rpm"]):
                    if attempt < max_retries - 1:
                        wait_sec = 4 * (attempt + 1)
                        print(f" [Rate limit hit, waiting {wait_sec}s before retry...]", end="", flush=True)
                        time.sleep(wait_sec)
                        continue

                raise

        raise RuntimeError("Failed to get response from AI after retries")

    def _build_prompt(self, test_case: str, page_state: dict, history: list) -> str:
        """Build the user prompt with current page state and action history."""
        elements_text = self._format_elements(page_state.get("elements", []))

        history_text = "None yet."
        if history:
            steps = []
            for h in history[-6:]:  # Keep last 6 actions
                status = "PASS" if h.get("success") else "FAIL"
                steps.append(f"  Step {h['step']}: {h['action']} {h.get('params', {})} -> {status}")
            history_text = "\n".join(steps)

        return f"""## TEST CASE
{test_case}

## CURRENT PAGE
- URL: {page_state.get('url', 'unknown')}
- Title: {page_state.get('title', 'unknown')}

## INTERACTIVE ELEMENTS ON PAGE
{elements_text}

## ACTION HISTORY
{history_text}

What is your next action? Respond with valid JSON only: {{"thought": "...", "action": "...", "params": {{...}}}}"""

    def _format_elements(self, elements: list) -> str:
        """Format elements list into a compact readable string for the AI."""
        if not elements:
            return "(No interactive elements found)"

        lines = []
        for el in elements:
            parts = [f"[{el['i']}]", f"<{el['tag']}>"]

            if el.get("role"):
                parts.append(f'role="{el["role"]}"')

            attrs = el.get("attrs") or {}
            for key in ["type", "name", "placeholder", "aria-label", "href", "id", "value"]:
                if key in attrs and attrs[key]:
                    val = str(attrs[key])[:35]
                    parts.append(f'{key}="{val}"')

            text = el.get("text", "")
            if text:
                clean_text = " ".join(text.split())[:35]
                parts.append(f'text="{clean_text}"')

            lines.append(" ".join(parts))

        return "\n".join(lines)

    def _parse_response(self, raw: str) -> dict:
        """Parse the AI's JSON response, handling markdown fences or surrounding chatter."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        # Direct JSON load
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "action" in parsed:
                return {
                    "thought": parsed.get("thought", ""),
                    "action": parsed.get("action", "done"),
                    "params": parsed.get("params", {})
                }
        except json.JSONDecodeError:
            pass

        # Extract JSON substring
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(cleaned[start:end])
                if isinstance(parsed, dict) and "action" in parsed:
                    return {
                        "thought": parsed.get("thought", ""),
                        "action": parsed.get("action", "done"),
                        "params": parsed.get("params", {})
                    }
            except json.JSONDecodeError:
                pass

        # Fallback if unparseable
        return {
            "thought": f"Could not parse action from AI response: {raw[:150]}",
            "action": "done",
            "params": {"result": "fail", "reason": f"AI response not valid JSON: {raw[:120]}"}
        }
