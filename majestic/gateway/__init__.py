"""
Gateway — runs one or more platform adapters concurrently.

Usage:
    from majestic.gateway import Gateway
    from majestic.gateway.telegram import TelegramPlatform

    gw = Gateway()
    gw.add(TelegramPlatform())
    asyncio.run(gw.run())
"""
import asyncio

from .base import Platform


class Gateway:
    def __init__(self):
        self._platforms: list[Platform] = []

    def add(self, platform: Platform) -> "Gateway":
        self._platforms.append(platform)
        return self

    async def run(self) -> None:
        active = [p for p in self._platforms if p.is_configured()]
        if not active:
            print("No platforms configured. Run `majestic setup` first.")
            return
        names = ", ".join(p.name for p in active)
        print(f"Starting gateway: {names}")
        await asyncio.gather(*[p.start() for p in active])
