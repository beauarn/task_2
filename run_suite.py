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
from run_test import run_test

def main():
    parser = argparse.ArgumentParser(description="Run a suite of AI-powered test cases")
    parser.add_argument("--suite", required=True, help="Path to JSON suite file")
    parser.add_argument("--model", default=None, help="AI model to use")
    parser.add_argument("--base-url", default=None, help="Custom API base URL")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--no-vision", action="store_true", help="Force text-only DOM mode")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--output-dir", default="results", help="Output directory")
    args = parser.parse_args()

    load_dotenv()

    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n  ERROR: OPENAI_API_KEY not set. See .env.example\n")
        sys.exit(1)

    model = args.model or os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = args.base_url or os.getenv("OPENAI_BASE_URL")

    with open(args.suite, "r", encoding="utf-8") as f:
        suite = json.load(f)

    test_cases = suite.get("tests", [])
    if not test_cases:
        print("  No test cases found in suite file.")
        sys.exit(1)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) / f"suite_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*65}")
    print(f"  AI TEST SUITE RUNNER")
    print(f"{'='*65}")
    print(f"  Suite:       {args.suite}")
    print(f"  Tests:       {len(test_cases)}")
    print(f"  Model:       {model}")
    print(f"  Base URL:    {base_url or 'https://api.openai.com/v1'}")
    print(f"  Vision Mode: {'Off (DOM only)' if args.no_vision else 'On (Multimodal)'}")
    print(f"  Headless:    {args.headless}")
    print(f"  Output Dir:  {output_dir}")
    print(f"{'='*65}\n")

    results = []

    for i, tc in enumerate(test_cases, 1):
        url = tc.get("url", "")
        test = tc.get("test", "")
        name = tc.get("name", f"Test {i}")
        max_steps = tc.get("max_steps", 25)

        print(f"\n{'─'*65}")
        print(f"  [{i}/{len(test_cases)}] {name}")
        print(f"     URL:  {url}")
        print(f"     Test: {test}")
        print(f"{'─'*65}")

        test_output = output_dir / f"test_{i:02d}"
        test_output.mkdir(exist_ok=True)

        browser = BrowserController(headless=args.headless)
        agent = AIAgent(
            api_key=api_key,
            model=model,
            base_url=base_url,
            use_vision=not args.no_vision
        )

        try:
            result = run_test(browser, agent, url, test, max_steps, test_output)
        except Exception as e:
            result = {"result": "fail", "reason": f"Execution error: {str(e)}", "steps_taken": 0}
        finally:
            browser.close()

        result["name"] = name
        results.append(result)

        status = "PASS" if result["result"] == "pass" else "FAIL"
        print(f"\n  [{status}] {result.get('reason', '')[:80]}")

    passed = sum(1 for r in results if r["result"] == "pass")
    failed = len(results) - passed

    print(f"\n\n{'='*65}")
    print(f"  SUITE RESULTS")
    print(f"{'='*65}")
    print(f"  Total:   {len(results)}")
    print(f"  Passed:  {passed}")
    print(f"  Failed:  {failed}")
    print(f"{'='*65}")

    for r in results:
        status = "PASS" if r["result"] == "pass" else "FAIL"
        print(f"  [{status}] {r.get('name', '?')}: {r.get('reason', '')[:60]}")

    print(f"\n  Results saved to: {output_dir}\n")

    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump({"passed": passed, "failed": failed, "results": results}, f, indent=2, default=str)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
