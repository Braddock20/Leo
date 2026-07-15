"""Instagram browser session manager.

Owns a single Playwright Chromium process + persistent profile. All jobs
call into this object so the IG session is reused (one login fingerprint).
"""
import asyncio
import json
import logging
import os
import random
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page, Playwright

from .stealth import apply_stealth
from .humanizer import short_pause, medium_pause, long_pause, sleep_async, human_scroll
from ..config import Config
from ..crypto import encrypt, decrypt
from ..db import get_conn

log = logging.getLogger("ig.session")


class IGSession:
    """Singleton-ish holder for the live browser context."""

    def __init__(self):
        self._pw: Optional[Playwright] = None
        self._ctx: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()
        self._logged_in: bool = False
        self._username: Optional[str] = None

    async def start(self):
        if self._ctx is not None:
            return
        self._pw = await async_playwright().start()
        # Use a persistent profile so cookies + cache survive restarts.
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(Config.CHROMIUM_PROFILE_DIR),
            headless=Config.HEADLESS,
            viewport={"width": 1280, "height": 860},
            user_agent=Config.USER_AGENT,
            locale="en-US",
            timezone_id="Europe/Moscow",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ],
        )
        await apply_stealth(self._ctx)
        self._page = await self._ctx.new_page()
        # Load and inject saved cookies (if any) so we don't trigger password login
        await self._inject_saved_cookies()
        # Open IG home — if session is valid we'll see the feed
        await self._page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await sleep_async(medium_pause())
        self._logged_in = await self._detect_logged_in()
        if self._logged_in:
            log.info("Session active.")
        else:
            log.warning("No active session. Use the dashboard to log in with cookies.")

    async def stop(self):
        try:
            if self._ctx is not None:
                await self._ctx.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                await self._pw.stop()
        except Exception:
            pass
        self._ctx = None
        self._page = None
        self._pw = None
        self._logged_in = False

    async def ensure_started(self):
        if self._ctx is None or self._page is None:
            await self.start()
        # If cookies were injected but page is dead, refresh
        try:
            await self._page.title()
        except Exception:
            if self._ctx is not None:
                self._page = await self._ctx.new_page()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("IG session not started")
        return self._page

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    async def _detect_logged_in(self) -> bool:
        try:
            url = self._page.url
            if "/accounts/login" in url:
                return False
            # The nav bar's presence is the simplest reliable signal
            await self._page.wait_for_selector('nav, [aria-label="Home"], [aria-label="Profile"]', timeout=8000)
            return True
        except Exception:
            return False

    async def _inject_saved_cookies(self):
        from ..db import get_conn as _gc
        with _gc() as c:
            row = c.execute("SELECT * FROM sessions_meta LIMIT 1").fetchone()
        if not row:
            return
        cookies_json = decrypt(row["encrypted_cookies"])
        if not cookies_json:
            return
        try:
            cookies = json.loads(cookies_json)
        except Exception:
            return
        # Normalize for Playwright
        normalized = []
        for ck in cookies:
            n = {
                "name": ck.get("name"),
                "value": ck.get("value"),
                "domain": ck.get("domain", ".instagram.com"),
                "path": ck.get("path", "/"),
            }
            if ck.get("expires") and isinstance(ck["expires"], (int, float)):
                n["expires"] = ck["expires"]
            if ck.get("httpOnly") is not None:
                n["httpOnly"] = bool(ck["httpOnly"])
            if ck.get("secure") is not None:
                n["secure"] = bool(ck["secure"])
            if ck.get("sameSite") in ("Strict", "Lax", "None"):
                n["sameSite"] = ck["sameSite"]
            normalized.append(n)
        try:
            await self._ctx.add_cookies(normalized)
            self._username = row["account_username"]
            log.info(f"Injected {len(normalized)} cookies for @{self._username}")
        except Exception as e:
            log.warning(f"Cookie injection failed: {e}")

    async def save_cookies(self):
        """Persist current context cookies to the DB (encrypted)."""
        if self._ctx is None:
            return
        cookies = await self._ctx.cookies("https://www.instagram.com/")
        if not cookies:
            return
        # Filter to just the IG-relevant ones
        keep = [c for c in cookies if "instagram.com" in c.get("domain", "")]
        from datetime import datetime, timezone
        with get_conn() as c:
            c.execute(
                """INSERT INTO sessions_meta(account_username, encrypted_cookies, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(account_username) DO UPDATE SET
                     encrypted_cookies=excluded.encrypted_cookies,
                     updated_at=excluded.updated_at""",
                ("me", encrypt(json.dumps(keep)), datetime.now(timezone.utc).isoformat()),
            )
        log.info(f"Saved {len(keep)} cookies.")

    # ---------- high-level actions ----------

    async def like_first_posts_on_feed(self, n: int):
        await self.ensure_started()
        if not self._logged_in:
            raise RuntimeError("Not logged in")
        await self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await sleep_async(medium_pause())
        await human_scroll(self.page, 400)
        liked = 0
        # The feed is a stream of articles. The "like" button has aria-label="Like".
        buttons = await self.page.query_selector_all('button[aria-label="Like"]')
        for btn in buttons[: max(1, n)]:
            try:
                await btn.scroll_into_view_if_needed()
                await sleep_async(short_pause())
                await btn.click()
                liked += 1
                await sleep_async(gauss_short())
            except Exception:
                continue
        return liked

    async def follow_from_profile(self, username: str) -> bool:
        await self.ensure_started()
        if not self._logged_in:
            raise RuntimeError("Not logged in")
        await self.page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded")
        await sleep_async(medium_pause())
        # The Follow button text is "Follow" before, "Following"/"Requested" after
        for sel in ['button:has-text("Follow")', 'div[role="button"]:has-text("Follow")']:
            btn = await self.page.query_selector(sel)
            if btn:
                try:
                    await btn.scroll_into_view_if_needed()
                    await sleep_async(short_pause())
                    await btn.click()
                    await sleep_async(short_pause())
                    return True
                except Exception:
                    return False
        return False

    async def send_dm(self, username: str, text: str) -> bool:
        await self.ensure_started()
        if not self._logged_in:
            raise RuntimeError("Not logged in")
        await self.page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded")
        await sleep_async(medium_pause())
        # Click the Message button
        msg_btn = await self.page.query_selector('button:has-text("Message")')
        if not msg_btn:
            return False
        await msg_btn.click()
        await sleep_async(medium_pause())
        # Compose box
        box = await self.page.wait_for_selector('textarea, div[contenteditable="true"][aria-label="Message"]', timeout=10000)
        await box.click()
        await self.page.keyboard.type(text, delay=random.randint(20, 80))
        await sleep_async(short_pause())
        # Send button (paper plane icon)
        send = await self.page.query_selector('button[type="submit"], button[aria-label="Send"]')
        if not send:
            return False
        await send.click()
        await sleep_async(medium_pause())
        return True

    async def view_stories(self, n: int) -> int:
        await self.ensure_started()
        if not self._logged_in:
            raise RuntimeError("Not logged in")
        await self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await sleep_async(medium_pause())
        # The story tray is at the top of the feed. Each avatar is a clickable button.
        tray_buttons = await self.page.query_selector_all('div[role="button"] canvas, [aria-label*="story"]')
        viewed = 0
        for el in tray_buttons[: max(1, n)]:
            try:
                await el.click()
                viewed += 1
                await sleep_async(gauss_short())
            except Exception:
                continue
        return viewed


def gauss_short():
    import random
    return max(0.6, random.gauss(2.2, 0.9))


# Module-level singleton
SESSION = IGSession()
