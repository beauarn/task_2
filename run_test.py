#!/usr/bin/env python3
"""
AI Test Runner - Turn plain-English test cases into automated browser tests.

Usage:
    python run_test.py --url "https://example.com" --test "Verify the homepage loads"
    python run_test.py --url "https://phptravels.com/demo" --test "Verify product information is displayed"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ai_test_runner.browser import BrowserController
from ai_test_runner.agent import AIAgent


def main():
    parser = argparse.ArgumentParser(
        description="AI Test Runner — Execute plain-English test cases in a real browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_test.py --url "https://phptravels.com/demo" --test "Click on Pricing in the navigation and verify the pricing plans are displayed"
  python run_test.py --url "https://example.com" --test "Verify the page title says Example Domain" --headless
        """,
    )
    parser.add_argument("--url", required=True, help="Starting URL for the test")
    parser.add_argument("--test", required=True, help='Test case in plain English (e.g. "Log in and verify dashboard")')
    parser.add_argument("--model", default=None, help="AI model (default: from .env or gpt-4o)")
    parser.add_argument("--base-url", default=None, help="Custom API base URL (e.g. Ollama, Groq, Gemini OpenAI proxy)")
    parser.add_argument("--api-key", default=None, help="API key (default: from OPENAI_API_KEY env var)")
    parser.add_argument("--no-vision", action="store_true", help="Force text-only DOM mode (skip sending screenshots)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (no visible GUI window)")
    parser.add_argument("--auto-close", action="store_true", help="Automatically close browser when test ends (by default, kept open until Enter)")
    parser.add_argument("--max-steps", type=int, default=25, help="Maximum actions before timeout (default: 25)")
    parser.add_argument("--output-dir", default="results", help="Directory for screenshots and logs (default: results)")
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n  ❌ ERROR: No API key found.")
        print("     Set OPENAI_API_KEY in .env or pass --api-key <key>\n")
        sys.exit(1)

    model = args.model or os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = args.base_url or os.getenv("OPENAI_BASE_URL")

    # Create timestamped output directory
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Banner
    print(f"\n{'='*65}")
    print(f"  🤖 AI TEST RUNNER")
    print(f"{'='*65}")
    print(f"  URL:         {args.url}")
    print(f"  Test Case:   {args.test}")
    print(f"  Model:       {model}")
    print(f"  Base URL:    {base_url or 'https://api.openai.com/v1'}")
    print(f"  Vision Mode: {'Off (DOM only)' if args.no_vision else 'On (Multimodal)'}")
    print(f"  Headless:    {args.headless}")
    print(f"  Keep Open:   {'No (auto-close)' if (args.headless or args.auto_close) else 'Yes (waits for Enter)'}")
    print(f"  Max Steps:   {args.max_steps}")
    print(f"  Output Dir:  {output_dir}")
    print(f"{'='*65}\n")

    browser = BrowserController(headless=args.headless)
    agent = AIAgent(
        api_key=api_key,
        model=model,
        base_url=base_url,
        use_vision=not args.no_vision
    )

    try:
        result = run_test(browser, agent, args.url, args.test, args.max_steps, output_dir)
        print_result(result)

        # Save result JSON
        result_file = output_dir / "result.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  📁 Test artifact saved to: {result_file}")

        return 0 if result["result"] == "pass" else 1

    except KeyboardInterrupt:
        print("\n\n  ⚠️ Test interrupted by user.\n")
        return 130
    except Exception as e:
        print(f"\n  ❌ RUNTIME ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 2
    finally:
        # Keep browser open until user presses Enter in terminal (unless headless or --auto-close)
        if not args.headless and not args.auto_close:
            try:
                print(f"\n{'─'*65}")
                input("  ⏸️  Browser kept open for your inspection.\n      👉 Press [Enter] here in the terminal to close the browser... ")
            except (KeyboardInterrupt, EOFError):
                pass
        browser.close()


def run_test(browser, agent, url, test_case, max_steps, output_dir):
    """
    Main test execution loop.
    1. Navigate to target URL
    2. Extract DOM + screenshot
    3. Query AI agent for next action
    4. Execute action in browser
    5. Repeat until AI signals 'done' (pass/fail) or timeout
    """
    print(f"  ▶ Launching Chromium and navigating to {url}...")
    browser.launch()
    browser.navigate(url)
    time.sleep(1)

    # Initial screenshot
    browser.save_screenshot(str(output_dir / "step_00_initial.png"))

    history = []

    for step in range(1, max_steps + 1):
        # 1. Page state
        state = browser.get_page_state()
        screenshot_b64 = browser.take_screenshot_b64()

        browser.save_screenshot(str(output_dir / f"step_{step:02d}.png"))

        element_count = len(state.get("elements", []))
        print(f"\n  ┌─ STEP {step}/{max_steps}")
        print(f"  │  Page: {state.get('title', '?')[:50]} ({element_count} elements)")

        # 2. Agent decision
        print(f"  │  🧠 Thinking...", end="", flush=True)
        start_time = time.time()
        try:
            action = agent.decide_action(test_case, state, screenshot_b64, history)
        except Exception as e:
            print(f" ERROR: {e}")
            return {
                "result": "fail",
                "reason": f"AI model error: {str(e)}",
                "steps_taken": len(history),
                "test_case": test_case,
                "url": url,
                "history": history,
            }

        elapsed = time.time() - start_time
        print(f" ({elapsed:.1f}s)")

        thought = action.get("thought", "")
        action_type = action.get("action", "unknown")
        params = action.get("params", {})

        if thought:
            print(f"  │  💭 {thought[:110]}{'...' if len(thought) > 110 else ''}")
        print(f"  │  ▸ Action: {action_type} {json.dumps(params, default=str)[:80]}")

        # 3. Completion check
        if action_type == "done":
            result = params.get("result", "fail")
            reason = params.get("reason", "No reason provided")

            # Guard: Prevent premature false passes when test requires physical action
            action_verbs = ["click", "fill", "type", "submit", "select", "log in", "login", "search", "enter"]
            requires_action = any(verb in test_case.lower() for verb in action_verbs)
            if result == "pass" and requires_action and len(history) == 0:
                print(f"  │  ⚠️ Intercepted premature PASS (no actions were taken yet). Forcing execution...")
                history.append({
                    "step": step,
                    "action": "correction",
                    "params": {},
                    "thought": thought,
                    "success": False,
                    "message": "REJECTED: You declared pass without taking any action. The test case requires you to interact with the page (click/fill) first.",
                })
                continue

            browser.save_screenshot(str(output_dir / f"step_{step:02d}_final.png"))
            return {
                "result": result,
                "reason": reason,
                "steps_taken": len(history),
                "test_case": test_case,
                "url": url,
                "history": history,
            }

        # 4. Action execution
        success, message = execute_action(browser, action_type, params)

        history.append({
            "step": step,
            "action": action_type,
            "params": params,
            "thought": thought,
            "success": success,
            "message": message,
        })

        status_icon = "✓" if success else "✗"
        print(f"  └─ {status_icon} {message}")

        time.sleep(0.5)

    # Max steps reached
    browser.save_screenshot(str(output_dir / "step_final_timeout.png"))
    return {
        "result": "fail",
        "reason": f"Test did not complete within {max_steps} steps",
        "steps_taken": len(history),
        "test_case": test_case,
        "url": url,
        "history": history,
    }


def execute_action(browser, action_type, params):
    """Execute a single browser action and return (success, message)."""
    try:
        if action_type == "click":
            index = params.get("index")
            if index is None:
                return False, "Missing index parameter for click"
            browser.click_element(int(index))
            return True, f"Clicked element [{index}]"

        elif action_type == "fill":
            index = params.get("index")
            text = str(params.get("text", ""))
            if index is None:
                return False, "Missing index parameter for fill"
            browser.fill_element(int(index), text)
            return True, f"Filled element [{index}] with '{text[:30]}'"

        elif action_type == "select":
            index = params.get("index")
            option = str(params.get("option", ""))
            if index is None:
                return False, "Missing index parameter for select"
            browser.select_option(int(index), option)
            return True, f"Selected '{option}' in element [{index}]"

        elif action_type == "navigate":
            url = str(params.get("url", ""))
            browser.navigate(url)
            return True, f"Navigated to {url}"

        elif action_type == "press":
            key = str(params.get("key", "Enter"))
            browser.press_key(key)
            return True, f"Pressed key: {key}"

        elif action_type == "scroll":
            direction = str(params.get("direction", "down"))
            browser.scroll(direction)
            return True, f"Scrolled {direction}"

        elif action_type == "wait":
            seconds = min(int(params.get("seconds", 2)), 10)
            time.sleep(seconds)
            return True, f"Waited {seconds}s"

        elif action_type == "hover":
            index = params.get("index")
            if index is None:
                return False, "Missing index parameter for hover"
            browser.hover_element(int(index))
            return True, f"Hovered over element [{index}]"

        else:
            return False, f"Unknown action type: {action_type}"

    except Exception as e:
        return False, f"Action failed: {str(e)[:150]}"


def print_result(result):
    """Print the formatted final test outcome."""
    status = result["result"].upper()
    reason = result["reason"]
    steps = result["steps_taken"]

    icon = "✅" if status == "PASS" else "❌"

    print(f"\n{'='*65}")
    print(f"  {icon}  TEST {status}")
    print(f"{'─'*65}")
    print(f"  Steps taken:  {steps}")
    print(f"  Reason:       {reason}")
    print(f"{'='*65}")


if __name__ == "__main__":
    sys.exit(main())
