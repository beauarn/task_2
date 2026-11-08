import json
import base64
import time
from openai import OpenAI

SYSTEM_PROMPT = """You are an expert, meticulous QA automation engineer controlling a web browser. Your job is to execute test cases written in plain English by interacting with web pages step by step.

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
{"action": "done", "params": {"result": "pass", "reason": "Specific evidence of why the test passed"}}
```
Conclude the test as "pass" or "fail".

---

## CRITICAL RULES TO PREVENT FALSE PASSES (STRICT ENFORCEMENT)

1. NEVER DECLARE PASS PREMATURELY:
   - If the test case contains an ACTION (e.g. click, fill, type, submit, select, search, log in), you CANNOT declare pass until that action has actually been executed.
   - Example: Test says "Click on Pricing and verify pricing plans are shown". Emitting done: pass on step 1 just because you see a link called Pricing is invalid. You MUST click the link first, wait for the page to change, verify the pricing plans on the new page, and only THEN call done: pass.

2. COMPLETING FORMS THOROUGHLY:
   - If the test case asks to fill the form, you must inspect the page and fill ALL available input fields in that form (First Name, Last Name, Company, Email, Phone/WhatsApp, etc.) step by step.
   - DO NOT stop after filling only 1 or 2 fields. Continue filling the remaining fields turn by turn.
   - Only call done: pass once all fields specified by the test case (or all fields of the form) have been filled.
   - If the test case says submit, you must also click the submit button and check the response.

3. VERIFY OUTCOME, NOT JUST INTENT:
   - Performing an action does not mean it succeeded.
   - If you just clicked Submit or Log In, do NOT conclude on that turn. On the NEXT turn, check if an error banner appeared or if the destination page loaded.
   - If an error message is shown, the test must be marked result: fail.

4. HONEST FAILURES:
   - If an expected element, button, or outcome cannot be found after searching: emit {"action": "done", "params": {"result": "fail", "reason": "Detailed reason why it failed"}}.
   - Reporting an accurate FAIL is correct and expected. False PASS is unacceptable in QA automation.

5. CITE CONCRETE EVIDENCE:
   - In your reason for done, cite specific proof: e.g. "All form fields filled with values" or "Page title changed to Pricing and plans Startup, Agency, Enterprise are visible".

## Response Format

Always respond with ONLY a JSON object (no markdown fences, no extra text):

{
    "thought": "I need to fill the Last Name field next to continue completing the form",
    "action": "fill",
    "params": {"index": 8, "text": "gibberish"}
}
"""

class AIAgent:
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
        user_prompt = self._build_prompt(test_case, page_state, history)

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
            {"role": "user", "content": content}
        ]

        raw_response = self._call_llm_with_retry(messages, user_prompt)
        return self._parse_response(raw_response)

    def _call_llm_with_retry(self, messages: list, user_prompt: str, max_retries: int = 3) -> str:
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

                if self.use_vision and any(term in err_str for term in ["image", "vision", "multimodal", "content_type", "unsupported", "must be a string", "400"]):
                    self.use_vision = False
                    messages[-1]["content"] = user_prompt
                    continue

                if any(term in err_str for term in ["413", "429", "rate limit", "too large", "tpm", "rpm"]):
                    if attempt < max_retries - 1:
                        wait_sec = 4 * (attempt + 1)
                        print(f" [Rate limit hit, waiting {wait_sec}s before retry...]", end="", flush=True)
                        time.sleep(wait_sec)
                        continue

                raise

        raise RuntimeError("Failed to get response from AI after retries")

    def _build_prompt(self, test_case: str, page_state: dict, history: list) -> str:
        elements_text = self._format_elements(page_state.get("elements", []))

        history_text = "None yet."
        if history:
            steps = []
            for h in history[-8:]:
                status = "PASS" if h.get("success") else "FAIL"
                steps.append(f"  Step {h['step']}: {h['action']} {h.get('params', {})} -> {status} ({h.get('message', '')})")
            history_text = "\n".join(steps)

        return f"""## TEST CASE TO EXECUTE
{test_case}

## CURRENT PAGE
- URL: {page_state.get('url', 'unknown')}
- Title: {page_state.get('title', 'unknown')}

## INTERACTIVE ELEMENTS ON PAGE
{elements_text}

## ACTION HISTORY (Steps already executed)
{history_text}

Review the test case carefully:
- If this is a form to fill, check if there are other unfilled form inputs (First Name, Last Name, Company, Email, Phone, etc.). Fill them turn-by-turn.
- If this requires clicking or navigating, perform the click first. Do not declare pass until verified on the next turn.
- What is your next single action? Respond with valid JSON only: {{"thought": "...", "action": "...", "params": {{...}}}}"""

    def _format_elements(self, elements: list) -> str:
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
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

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

        return {
            "thought": f"Could not parse action from AI response: {raw[:150]}",
            "action": "done",
            "params": {"result": "fail", "reason": f"AI response not valid JSON: {raw[:120]}"}
        }
