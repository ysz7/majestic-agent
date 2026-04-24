"""
Platform — abstract base for every gateway adapter (Telegram, Discord, …).
"""
from abc import ABC, abstractmethod


class Platform(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
