"""
AI Agent - Interfaces with OpenAI, Groq, Ollama, Gemini or any OpenAI-compatible API
to interpret plain-English test cases and decide actions.

The agent receives the current page state (DOM elements + screenshot) and decides
what action to take next to fulfill the plain-English test case.
"""

import json
import base64
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
{"action": "done", "params": {"result": "pass", "reason": "Successfully logged in and verified dashboard is displayed with user name"}}
```
Conclude the test. Result must be "pass" or "fail".

## Rules

1. **One action per response.** Always return exactly one action as JSON.
2. **Think before acting.** Include a "thought" field explaining your reasoning.
3. **Reference elements by index.** Use the [index] from the element list.
4. **Verify before concluding.** Don't mark "pass" until you've actually verified the expected outcome on the page. Check that the right text, page, or state is visible.
5. **Handle failures gracefully.** If an action fails, try an alternative approach. Only mark "fail" if the objective is clearly impossible.
6. **Look for demo/default credentials.** If the test mentions login but doesn't give credentials, look on the page for demo credentials or try common ones (e.g. admin@example.com / password).
7. **Be concise.** Keep thoughts short and actionable.
8. **For custom dropdowns** (not <select> tags), click to open first, then click the option.
9. **Maximum steps.** You have limited steps. Be efficient.

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
            # Groq chat completion API expects string content for text models
            if "groq.com" in base_url.lower() and "vision" not in model.lower():
                use_vision = False
        self.client = OpenAI(**kwargs)
        self.model = model
        self.use_vision = use_vision
        self.conversation = []  # Running conversation for context

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

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self.conversation,
            {"role": "user", "content": content}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=1000,
            )
        except Exception as e:
            err_str = str(e).lower()
            # If the model does not support vision/images, retry with text-only DOM
            if self.use_vision and any(term in err_str for term in ["image", "vision", "multimodal", "content_type", "unsupported", "must be a string", "400"]):
                self.use_vision = False
                messages[-1]["content"] = user_prompt
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1000,
                )
            else:
                raise

        raw_response = response.choices[0].message.content.strip()

        # Track conversation history (text only to conserve tokens)
        self.conversation.append({"role": "user", "content": user_prompt})
        self.conversation.append({"role": "assistant", "content": raw_response})

        # Keep last 16 turns
        if len(self.conversation) > 16:
            self.conversation = self.conversation[-16:]

        return self._parse_response(raw_response)

    def _build_prompt(self, test_case: str, page_state: dict, history: list) -> str:
        """Build the user prompt with current page state."""
        elements_text = self._format_elements(page_state.get("elements", []))

        history_text = "None yet."
        if history:
            steps = []
            for h in history[-8:]:  # Last 8 steps
                status = "PASS" if h.get("success") else "FAIL"
                steps.append(f"  Step {h['step']}: {h['action']} {h.get('params', {})} -> {status} ({h.get('message', '')})")
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
        """Format elements list into a readable string for the AI."""
        if not elements:
            return "(No interactive elements found)"

        lines = []
        for el in elements:
            parts = [f"[{el['i']}]", f"<{el['tag']}>"]

            if el.get("role"):
                parts.append(f'role="{el["role"]}"')

            attrs = el.get("attrs") or {}
            for key in ["type", "name", "placeholder", "aria-label", "href", "id", "title", "for", "value"]:
                if key in attrs and attrs[key]:
                    val = str(attrs[key])[:80]
                    parts.append(f'{key}="{val}"')

            text = el.get("text", "")
            if text:
                clean_text = " ".join(text.split())[:80]
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
