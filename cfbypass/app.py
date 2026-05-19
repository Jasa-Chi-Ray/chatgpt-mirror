from __future__ import annotations

import asyncio
import os
import shutil
import time
import traceback
from typing import Any
from urllib.parse import urlparse

from DrissionPage import ChromiumOptions, ChromiumPage
from fastapi import FastAPI
from pydantic import BaseModel, Field, HttpUrl, field_validator

DEFAULT_USER_AGENT = os.getenv(
    "CF_BYPASS_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)
DEFAULT_HEADLESS = os.getenv("CF_BYPASS_HEADLESS", "true").lower() not in {
    "0",
    "false",
    "no",
}
MAX_WAIT_SECONDS = int(os.getenv("CF_BYPASS_MAX_WAIT_SECONDS", "35"))
POLL_INTERVAL_SECONDS = float(os.getenv("CF_BYPASS_POLL_INTERVAL_SECONDS", "2"))
PARTIAL_COOKIE_GRACE_SECONDS = float(
    os.getenv("CF_BYPASS_PARTIAL_COOKIE_GRACE_SECONDS", "8")
)
NAVIGATION_RETRIES = int(os.getenv("CF_BYPASS_NAVIGATION_RETRIES", "2"))
DISPLAY_SIZE = os.getenv("CF_BYPASS_DISPLAY_SIZE", "1920x1080")

CLOUDFLARE_COOKIE_NAMES = {"cf_clearance", "__cf_bm", "__cflb", "_cfuvid"}
EXTRA_COOKIE_PREFIXES = ("oai-", "__Host-next-auth.", "__Secure-next-auth.")
CLICK_SELECTORS = (".spacer", "input[type='checkbox']")

app = FastAPI()
_BYPASS_LOCK = asyncio.Lock()
_XVFB_DISPLAY = None


class CloudFlare5sQuerySchema(BaseModel):
    url: HttpUrl = Field(..., description="cloudflare target url")
    user_agent: str | None = Field(default=None, description="user agent")
    proxy_server: str | None = Field(default=None, description="http/https proxy")

    @field_validator("user_agent")
    @classmethod
    def normalize_user_agent(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("proxy_server")
    @classmethod
    def validate_proxy_server(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None

        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("proxy_server 必须是合法的 http/https 代理地址")
        if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
            raise ValueError("proxy_server 不能包含路径或查询参数")
        return normalized


def log(message: str) -> None:
    print(f"[cfbypass] {message}", flush=True)


def parse_display_size() -> tuple[int, int]:
    try:
        width_raw, height_raw = DISPLAY_SIZE.lower().split("x", 1)
        width = max(int(width_raw), 800)
        height = max(int(height_raw), 600)
        return width, height
    except Exception:
        return 1920, 1080


def ensure_virtual_display() -> None:
    global _XVFB_DISPLAY
    if DEFAULT_HEADLESS or os.getenv("DISPLAY") or _XVFB_DISPLAY is not None:
        return

    from pyvirtualdisplay import Display

    width, height = parse_display_size()
    _XVFB_DISPLAY = Display(
        backend="xvfb",
        visible=True,
        size=(width, height),
        use_xauth=True,
    )
    _XVFB_DISPLAY.start()
    log(f"virtual display started: DISPLAY={os.getenv('DISPLAY')}")


def resolve_browser_path() -> str | None:
    for candidate in (
        os.getenv("CF_BYPASS_BROWSER_PATH"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def is_interesting_cookie_name(name: str) -> bool:
    normalized = name.strip()
    if not normalized:
        return False
    if normalized in CLOUDFLARE_COOKIE_NAMES:
        return True
    return normalized.startswith(EXTRA_COOKIE_PREFIXES)


def normalize_cookies(raw_cookies: list[dict[str, Any]]) -> list[dict[str, str]]:
    cookies: list[dict[str, str]] = []
    for raw in raw_cookies:
        name = str(raw.get("name", "")).strip()
        value = str(raw.get("value", "")).strip()
        domain = str(raw.get("domain", "")).strip()
        if not name or not value or not is_interesting_cookie_name(name):
            continue

        item = {"name": name, "value": value}
        if domain:
            item["domain"] = domain
        cookies.append(item)
    return cookies


class Cloudflare5sBypass:
    def __init__(self, user_agent: str | None = None, proxy_server: str | None = None):
        ensure_virtual_display()
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.proxy_server = proxy_server
        self.driver: ChromiumPage | None = None

    def _build_options(self) -> ChromiumOptions:
        browser_path = resolve_browser_path()
        if not browser_path:
            raise RuntimeError("未找到 Chromium/Chrome 可执行文件")

        options = ChromiumOptions()
        options.set_paths(browser_path=browser_path)
        if self.user_agent:
            options.set_user_agent(self.user_agent)
        if self.proxy_server:
            options.set_proxy(self.proxy_server)

        for argument in (
            "--accept-lang=en-US",
            "--disable-background-mode",
            "--disable-dev-shm-usage",
            "--disable-features=FlashDeprecationWarning,EnablePasswordsAccountStorage,PrivacySandboxSettings4",
            "--disable-gpu",
            "--disable-infobars",
            "--disable-popup-blocking",
            "--disable-suggestions-ui",
            "--disable-extensions",
            "--force-color-profile=srgb",
            "--hide-crash-restore-bubble",
            "--metrics-recording-only",
            "--no-default-browser-check",
            "--no-first-run",
            "--password-store=basic",
            "--use-mock-keychain",
            "--window-size=1920,1080",
        ):
            options.set_argument(argument)

        if DEFAULT_HEADLESS:
            options.headless(True)
        else:
            options.headless(False)
            options.set_argument("--start-maximized")

        if os.name != "nt":
            options.set_argument("--no-sandbox")
            options.set_argument("--disable-setuid-sandbox")

        return options

    def _ensure_driver(self) -> ChromiumPage:
        if self.driver is None:
            self.driver = ChromiumPage(addr_or_opts=self._build_options())
        return self.driver

    def _close_driver(self) -> None:
        if self.driver is None:
            return
        try:
            self.driver.quit()
        except Exception as error:
            log(f"quit browser failed: {error}")
        finally:
            self.driver = None

    def _read_cookies(self) -> list[dict[str, str]]:
        driver = self._ensure_driver()
        raw_cookies = driver.cookies()
        if not isinstance(raw_cookies, list):
            return []
        return normalize_cookies(raw_cookies)

    def _maybe_click_verification(self) -> bool:
        driver = self._ensure_driver()
        for selector in CLICK_SELECTORS:
            try:
                if not driver.wait.ele_displayed(selector, timeout=1):
                    continue
                element = driver.ele(selector, timeout=1)
                if element is None:
                    continue
                element.click()
                log(f"clicked verification selector: {selector}")
                return True
            except Exception:
                continue
        return False

    async def get_cf_cookie(self, url: str) -> dict[str, Any]:
        last_cookies: list[dict[str, str]] = []
        last_error: Exception | None = None

        for attempt in range(1, NAVIGATION_RETRIES + 1):
            partial_cookie_at: float | None = None
            try:
                driver = self._ensure_driver()
                try:
                    driver.set.cookies.clear()
                except Exception:
                    pass

                log(f"navigate attempt={attempt} url={url}")
                driver.get(url)

                deadline = time.monotonic() + MAX_WAIT_SECONDS
                while time.monotonic() < deadline:
                    cookies = self._read_cookies()
                    if cookies:
                        last_cookies = cookies
                        if any(
                            cookie["name"] == "cf_clearance"
                            for cookie in cookies
                        ):
                            return {"user_agent": self.user_agent, "cookies": cookies}
                        if any(
                            cookie["name"] in CLOUDFLARE_COOKIE_NAMES
                            for cookie in cookies
                        ):
                            if partial_cookie_at is None:
                                partial_cookie_at = time.monotonic()
                            if (
                                time.monotonic() - partial_cookie_at
                                >= PARTIAL_COOKIE_GRACE_SECONDS
                            ):
                                return {
                                    "user_agent": self.user_agent,
                                    "cookies": cookies,
                                }

                    self._maybe_click_verification()
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except Exception as error:
                last_error = error
                log(f"attempt={attempt} failed: {error}")
                log(traceback.format_exc())
            finally:
                self._close_driver()

        if last_cookies:
            log(
                "returning partial cookies after timeout: "
                + ",".join(cookie["name"] for cookie in last_cookies)
            )
            return {"user_agent": self.user_agent, "cookies": last_cookies}

        if last_error is not None:
            log(f"all attempts failed: {last_error}")
        return {"user_agent": self.user_agent, "cookies": []}


@app.get("/")
async def index() -> dict[str, Any]:
    return {"message": "ok"}


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok", "headless": DEFAULT_HEADLESS}


async def solve(query_params: CloudFlare5sQuerySchema) -> dict[str, Any]:
    async with _BYPASS_LOCK:
        bypass = Cloudflare5sBypass(
            user_agent=query_params.user_agent,
            proxy_server=query_params.proxy_server,
        )
        return await bypass.get_cf_cookie(str(query_params.url))


@app.post("/cloudflare5s/bypass-v1")
async def bypass_v1(query_params: CloudFlare5sQuerySchema) -> dict[str, Any]:
    return await solve(query_params)


@app.post("/cloudflare5s/bypass-v2")
async def bypass_v2(query_params: CloudFlare5sQuerySchema) -> dict[str, Any]:
    return await solve(query_params)
