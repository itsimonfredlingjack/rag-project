"""
SSE Stream Service - Keep-alive wrapper for streaming responses
"""

import asyncio
import json
from typing import AsyncGenerator, Optional


class SSEStreamService:
    """Handle SSE streams with automatic keep-alive pings."""

    async def wrap_stream_with_keepalive(
        self,
        event_generator: AsyncGenerator[str, None],
        keepalive_interval: float = 15.0,
    ) -> AsyncGenerator[str, None]:
        """
        Wrap an SSE event generator and inject keep-alive pings during idle periods.

        Keep-alive format: ":ping\n\n" (SSE comment line).

        Uses a background task + asyncio.Queue so the keepalive timeout never
        cancels the underlying generator.  The previous implementation used
        asyncio.wait_for(anext(generator), timeout=...) which, on timeout,
        injects CancelledError into the generator and permanently closes it —
        meaning all subsequent events (tokens, done) were silently dropped.
        """
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        async def producer() -> None:
            try:
                async for event in event_generator:
                    await queue.put(event)
            except Exception as exc:
                await queue.put(f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n")
            finally:
                await queue.put(None)  # Sentinel: stream finished

        task = asyncio.ensure_future(producer())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=keepalive_interval)
                    if item is None:  # Done sentinel
                        return
                    yield item
                except asyncio.TimeoutError:
                    # Queue was empty for keepalive_interval seconds — send ping.
                    # The producer task keeps running; no events are lost.
                    yield ":ping\n\n"
        finally:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
