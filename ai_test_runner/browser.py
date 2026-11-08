import base64
import time
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

EXTRACT_ELEMENTS_JS = """
() => {
    document.querySelectorAll('[data-test-ai-idx]').forEach(el => {
        el.removeAttribute('data-test-ai-idx');
    });

    const HIGH_PRIO_TAGS = new Set(['input', 'button', 'select', 'textarea']);
    const MID_PRIO_TAGS = new Set(['a', 'option', 'details', 'summary']);
    const SEMANTIC_TAGS = new Set(['h1', 'h2', 'h3', 'label']);
    const INTERACTIVE_ROLES = new Set([
        'button', 'link', 'textbox', 'checkbox', 'radio', 'tab',
        'menuitem', 'option', 'combobox', 'searchbox'
    ]);

    const candidates = [];
    const all = document.querySelectorAll('*');

    for (const el of all) {
        try {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) continue;
        } catch (e) {
            continue;
        }

        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role');

        let priority = 4;
        if (HIGH_PRIO_TAGS.has(tag) || (role && (role === 'button' || role === 'textbox'))) {
            priority = 1;
        } else if (MID_PRIO_TAGS.has(tag) || (role && INTERACTIVE_ROLES.has(role)) || el.hasAttribute('onclick')) {
            priority = 2;
        } else if (SEMANTIC_TAGS.has(tag)) {
            priority = 3;
        } else {
            continue;
        }

        candidates.push({ el, tag, role, priority });
    }

    candidates.sort((a, b) => a.priority - b.priority);

    const elements = [];
    for (const item of candidates) {
        const el = item.el;
        const tag = item.tag;
        const role = item.role;
        const index = elements.length;
        el.setAttribute('data-test-ai-idx', String(index));

        const attrs = {};
        for (const attr of ['id', 'name', 'type', 'placeholder', 'value', 'href', 'aria-label']) {
            const val = el.getAttribute(attr);
            if (val && val.trim()) {
                attrs[attr] = val.trim().substring(0, 40);
            }
        }

        if (tag === 'select') {
            const options = [];
            for (const opt of el.options) {
                options.push(opt.text.trim().substring(0, 30));
            }
            if (options.length > 0) attrs['options'] = options.slice(0, 10).join(' | ');
        }

        if (el.type === 'checkbox' || el.type === 'radio') {
            attrs['checked'] = el.checked ? 'true' : 'false';
        }

        let text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').substring(0, 50);

        elements.push({
            i: index,
            tag: tag,
            role: role || undefined,
            text: text || undefined,
            attrs: Object.keys(attrs).length > 0 ? attrs : undefined
        });

        if (elements.length >= 65) break;
    }

    return elements;
}
"""

class BrowserController:
    def __init__(self, headless: bool = False, timeout: int = 15000):
        self.headless = headless
        self.timeout = timeout
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None

    def launch(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        self._context.on("page", self._on_new_page)
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.timeout)

    def _on_new_page(self, new_page: Page):
        try:
            new_page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        self._page = new_page
        self._page.set_default_timeout(self.timeout)

    def _ensure_active_page(self):
        if not self._context:
            return
        pages = self._context.pages
        if not pages:
            self._page = self._context.new_page()
            return
        if self._page is None or self._page.is_closed():
            self._page = pages[-1]
            self._page.set_default_timeout(self.timeout)

    def navigate(self, url: str):
        self._ensure_active_page()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._page.wait_for_timeout(1500)

    def get_page_state(self) -> dict:
        self._ensure_active_page()
        try:
            elements = self._page.evaluate(EXTRACT_ELEMENTS_JS)
        except Exception:
            elements = []

        try:
            url = self._page.url
            title = self._page.title()
        except Exception:
            url = "unknown"
            title = "unknown"

        return {
            "url": url,
            "title": title,
            "elements": elements
        }

    def take_screenshot_b64(self) -> str:
        self._ensure_active_page()
        try:
            screenshot_bytes = self._page.screenshot(type="png")
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception:
            return ""

    def save_screenshot(self, path: str):
        self._ensure_active_page()
        try:
            self._page.screenshot(path=path, type="png")
        except Exception:
            pass

    def click_element(self, index: int):
        self._ensure_active_page()
        selector = f'[data-test-ai-idx="{index}"]'
        locator = self._page.locator(selector).first

        try:
            locator.click(timeout=self.timeout)
        except Exception:
            try:
                locator.click(force=True, timeout=5000)
            except Exception:
                locator.evaluate("el => el.click()")

        self._page.wait_for_timeout(1000)
        self._ensure_active_page()

    def fill_element(self, index: int, text: str):
        self._ensure_active_page()
        selector = f'[data-test-ai-idx="{index}"]'
        locator = self._page.locator(selector).first

        try:
            locator.click(timeout=5000)
            locator.fill(text, timeout=self.timeout)
        except Exception:
            try:
                locator.press_sequentially(text)
            except Exception:
                locator.evaluate("""(el, val) => {
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""", text)

        self._page.wait_for_timeout(500)

    def select_option(self, index: int, option: str):
        self._ensure_active_page()
        selector = f'[data-test-ai-idx="{index}"]'
        locator = self._page.locator(selector).first

        try:
            locator.select_option(label=option, timeout=self.timeout)
        except Exception:
            try:
                locator.select_option(value=option, timeout=5000)
            except Exception:
                locator.evaluate("""(el, opt) => {
                    for (let o of el.options) {
                        if (o.text.includes(opt) || o.value.includes(opt)) {
                            el.value = o.value;
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            break;
                        }
                    }
                }""", option)
        self._page.wait_for_timeout(500)

    def hover_element(self, index: int):
        self._ensure_active_page()
        selector = f'[data-test-ai-idx="{index}"]'
        self._page.locator(selector).first.hover(timeout=self.timeout)
        self._page.wait_for_timeout(500)

    def press_key(self, key: str):
        self._ensure_active_page()
        self._page.keyboard.press(key)
        self._page.wait_for_timeout(500)

    def scroll(self, direction: str = "down"):
        self._ensure_active_page()
        delta = 600 if direction == "down" else -600
        self._page.mouse.wheel(0, delta)
        self._page.wait_for_timeout(800)

    def close(self):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
