"""Randomized human-like behavior utilities used by the browser session.

All delays are drawn from log-normal-ish distributions so the script never
behaves like a metronome (which IG's behavioral classifier picks up on).
"""
import random
import asyncio
import math
from typing import Iterable


def gauss_delay(mean: float, std: float, lo: float, hi: float) -> float:
    """Gaussian sample clamped to [lo, hi]. mean and std in seconds."""
    for _ in range(8):
        v = random.gauss(mean, std)
        if lo <= v <= hi:
            return v
    return max(lo, min(hi, mean))


def short_pause() -> float:
    return gauss_delay(1.4, 0.6, 0.4, 4.0)


def medium_pause() -> float:
    return gauss_delay(4.0, 1.6, 1.5, 9.0)


def long_pause() -> float:
    return gauss_delay(45.0, 18.0, 15.0, 180.0)


async def sleep_async(seconds: float):
    await asyncio.sleep(max(0.05, seconds))


async def human_type(page, selector: str, text: str, wpm_mean: int = 65):
    """Type one character at a time with realistic WPM + occasional pauses."""
    el = await page.wait_for_selector(selector, timeout=15000)
    await el.click()
    # 65 WPM = ~ 4.6 chars/sec -> mean per-char delay ~ 0.22s
    per_char = 60.0 / max(20, wpm_mean) / 4.6
    for i, ch in enumerate(text):
        await page.keyboard.type(ch, delay=0)
        await asyncio.sleep(max(0.04, random.gauss(per_char, per_char * 0.5)))
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(0.3, 0.9))


async def human_scroll(page, distance: int | None = None):
    """Smooth wheel scroll in chunks."""
    if distance is None:
        distance = random.randint(220, 720)
    steps = max(3, distance // 80)
    per = distance / steps
    for _ in range(steps):
        await page.mouse.wheel(0, per)
        await asyncio.sleep(random.uniform(0.05, 0.18))


async def human_move_and_click(page, selector: str):
    el = await page.wait_for_selector(selector, timeout=15000, state="visible")
    box = await el.bounding_box()
    if not box:
        return
    cx = box["x"] + box["width"] / 2 + random.uniform(-box["width"] / 4, box["width"] / 4)
    cy = box["y"] + box["height"] / 2 + random.uniform(-box["height"] / 4, box["height"] / 4)
    # Bezier-ish path
    steps = random.randint(12, 28)
    sx, sy = random.randint(120, 600), random.randint(120, 400)
    for i in range(steps):
        t = i / steps
        x = sx + (cx - sx) * t + random.uniform(-2, 2)
        y = sy + (cy - sy) * t + random.uniform(-2, 2)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.005, 0.02))
    await asyncio.sleep(random.uniform(0.05, 0.18))
    await page.mouse.click(cx, cy)
    await asyncio.sleep(short_pause())


def should_act_today(kind: str, limit: int) -> bool:
    """Returns True if we're under the daily cap for this kind."""
    from ..db import count_actions_today
    return count_actions_today(kind) < limit
