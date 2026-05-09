"""
Abstract base class for all communication channels.

A channel is the I/O boundary between the outside world and the agent runtime.
Every concrete channel must implement the three async methods below.
"""

from abc import ABC, abstractmethod


class BaseChannel(ABC):
    """Abstract communication channel.

    Concrete subclasses handle a specific transport (CLI stdin/stdout,
    HTTP queue, WebSocket, Slack, etc.) while the agent runtime only
    ever calls the three abstract methods defined here.
    """

    @abstractmethod
    async def receive(self) -> dict:
        """Wait for the next inbound message and return it as a normalised dict.

        Returns
        -------
        dict with keys:
            text        (str)        — plain-text content of the message.
            attachments (list[str])  — zero or more file-system paths.
            session_id  (str)        — stable identifier for the current session.
        """

    @abstractmethod
    async def send(self, message: str) -> None:
        """Deliver a complete response message to the user.

        Parameters
        ----------
        message:
            The full text to deliver.  Channels may apply their own
            formatting (Markdown rendering, Rich markup, etc.).
        """

    @abstractmethod
    async def send_stream(self, token: str) -> None:
        """Deliver a single streaming token as it arrives from the LLM.

        Parameters
        ----------
        token:
            A partial response fragment.  The channel should write it
            immediately without buffering a newline.
        """
