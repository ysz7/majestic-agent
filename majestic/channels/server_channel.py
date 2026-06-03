"""
HTTP-backed server channel.

Used when the agent runs as a background daemon: an HTTP server pushes
tasks into the queue via ``enqueue()``, the agent runtime calls
``receive()`` to block until a task arrives, then reads the response
from ``_last_response`` / ``_stream_buffer`` after the turn completes.
"""

from __future__ import annotations

import asyncio

from .base import BaseChannel


class ServerChannel(BaseChannel):
    """Receives tasks via an in-process asyncio queue.

    The HTTP layer (FastAPI routes or a thin WSGI adapter) calls
    ``enqueue()`` to submit work.  The agent runtime calls ``receive()``
    and blocks until an item is available, then processes it and calls
    ``send()`` / ``send_stream()`` to store the result.

    Parameters
    ----------
    session_id:
        Stable identifier for this agent session (e.g. the profile name
        combined with a launch timestamp).
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._last_response: str = ""
        self._stream_buffer: str = ""
        # task_id -> Future resolved when the agent loop stores that task's result.
        # Lets the HTTP layer (e.g. WorkflowRunner) await a specific task.
        self._results: dict[str, asyncio.Future[str]] = {}
        # Results that arrived before anyone awaited them (avoids a lost-wakeup race).
        self._completed: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Queue management (called by the HTTP layer)
    # ------------------------------------------------------------------

    async def enqueue(self, task: dict) -> None:
        """Submit a task dict to the internal queue.

        The dict should follow the standard channel input format::

            {
                "text":        str,          # natural-language instruction
                "attachments": list[str],    # optional file paths
                "session_id":  str,          # may override self.session_id
            }

        Parameters
        ----------
        task:
            Task payload pushed by the HTTP handler.
        """
        # Ensure session_id is always present so the agent never has to
        # guard against a missing key.
        task.setdefault("session_id", self.session_id)
        task.setdefault("text", "")
        task.setdefault("attachments", [])
        await self._queue.put(task)

    def try_enqueue(self, task: dict) -> bool:
        """Non-blocking enqueue. Returns False if queue is full."""
        task.setdefault("session_id", self.session_id)
        task.setdefault("text", "")
        task.setdefault("attachments", [])
        try:
            self._queue.put_nowait(task)
            return True
        except asyncio.QueueFull:
            return False

    # ------------------------------------------------------------------
    # BaseChannel interface
    # ------------------------------------------------------------------

    async def receive(self) -> dict:
        """Block until a task is available in the queue and return it.

        Returns
        -------
        dict with keys:
            text        (str)       — instruction text.
            attachments (list[str]) — file paths (may be empty).
            session_id  (str)       — session identifier.
        """
        # Reset response buffers for the upcoming turn.
        self._last_response = ""
        self._stream_buffer = ""
        return await self._queue.get()

    async def send(self, message: str) -> None:
        """Store *message* as the last complete response.

        The HTTP handler can retrieve it via ``channel._last_response``
        once the agent turn has finished.

        Parameters
        ----------
        message:
            Full response text produced by the agent for this turn.
        """
        self._last_response = message

    async def send_stream(self, token: str) -> None:
        """Accumulate *token* in the stream buffer.

        The HTTP layer may expose this buffer via Server-Sent Events or a
        polling endpoint to deliver incremental output to the client.

        Parameters
        ----------
        token:
            A single streaming fragment from the LLM.
        """
        self._stream_buffer = self._stream_buffer + token

    # ------------------------------------------------------------------
    # Convenience helpers for the HTTP layer
    # ------------------------------------------------------------------

    def store_result(self, task_id: str, result: str) -> None:
        """Record a finished task's result and wake any awaiter.

        Called by the agent loop after ``runtime.run()`` returns. Resolves the
        Future created by :meth:`await_result` so the HTTP layer can retrieve
        the output of a specific task by id.
        """
        if not task_id:
            return
        fut = self._results.get(task_id)
        if fut is not None and not fut.done():
            fut.set_result(result)
        else:
            # No awaiter yet — stash so a later await_result returns immediately.
            self._completed[task_id] = result

    async def await_result(self, task_id: str, timeout: float = 300.0) -> str:
        """Block until the task with *task_id* completes, returning its result.

        Raises
        ------
        asyncio.TimeoutError
            If the task does not finish within *timeout* seconds.
        """
        if task_id in self._completed:
            return self._completed.pop(task_id)
        loop = asyncio.get_running_loop()
        fut = self._results.get(task_id)
        if fut is None:
            fut = loop.create_future()
            self._results[task_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._results.pop(task_id, None)

    def get_response(self) -> str:
        """Return the last complete response stored by ``send()``."""
        return self._last_response

    def get_stream_buffer(self) -> str:
        """Return all streamed tokens accumulated so far."""
        return self._stream_buffer

    def queue_size(self) -> int:
        """Return the number of pending tasks currently in the queue."""
        return self._queue.qsize()
