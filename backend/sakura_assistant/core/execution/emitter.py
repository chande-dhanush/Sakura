"""
Sakura V17: Response Emitter
============================
Single authority for response emission with state guard.

v2.1: Guarantees exactly one message per request.
Prevents double-emission which causes UI desync.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class ResponseEmitter:
    """
    Single authority for response emission.
    
    INVARIANT: At most one emission per request.
    
    v2.1: Uses state flag + async lock to prevent:
    - Double emission if responder streamed
    - UI desync if tool events already fired
    - Race conditions in async context
    
    Usage:
        emitter = ResponseEmitter(request_id, broadcaster)
        try:
            response = await process(...)
            await emitter.emit(response, {"status": "success"})
        except Exception as e:
            await emitter.emit(f"Error: {e}", {"status": "error"})
        finally:
            if not emitter.was_emitted:
                await emitter.emit("Something went wrong", {"status": "unknown"})
    """
    
    def __init__(
        self, 
        request_id: str, 
        broadcaster: Optional[Any] = None,
        emit_callback: Optional[Callable[[str, Dict], Awaitable[None]]] = None
    ):
        """
        Initialize emitter.
        
        Args:
            request_id: Unique ID for this request (for logging)
            broadcaster: SSE/WebSocket broadcaster instance
            emit_callback: Alternative async callback for emission
        """
        self._request_id = request_id
        self._broadcaster = broadcaster
        self._emit_callback = emit_callback
        self._emitted = False
        self._lock = asyncio.Lock()
        self._emission_content: Optional[str] = None
        self._emission_metadata: Optional[Dict] = None
    
    async def emit(self, response: str, metadata: Optional[Dict] = None) -> bool:
        """
        Emit a response message.
        
        Args:
            response: The response text to emit
            metadata: Optional metadata (status, latency, etc.)
        
        Returns:
            True if emitted, False if already emitted (blocked)
        """
        async with self._lock:
            if self._emitted:
                logger.warning(
                    f"⚠️ [Emitter] Duplicate emission blocked for request {self._request_id}. "
                    f"Original: {self._emission_content[:50] if self._emission_content else 'None'}... "
                    f"Blocked: {response[:50]}..."
                )
                return False
            
            # Mark as emitted BEFORE actual emission to prevent races
            self._emitted = True
            self._emission_content = response
            self._emission_metadata = metadata or {}
            
            # Perform actual emission
            try:
                if self._emit_callback:
                    await self._emit_callback(response, metadata or {})
                elif self._broadcaster:
                    await self._broadcaster.send_assistant_message(
                        self._request_id, 
                        response, 
                        metadata or {}
                    )
                else:
                    # No broadcaster configured - log only
                    logger.debug(f"[Emitter] Response ready (no broadcaster): {response[:100]}...")
                
                logger.info(f" [Emitter] Response emitted for {self._request_id}")
                return True
                
            except Exception as e:
                # Emission failed but we already marked as emitted
                # This prevents retry loops
                logger.error(f" [Emitter] Emission failed for {self._request_id}: {e}")
                return False
    
    def emit_sync(self, response: str, metadata: Optional[Dict] = None) -> bool:
        """
        Synchronous emission for non-async contexts.
        
        Only use at HTTP boundary where async is not available.
        """
        if self._emitted:
            logger.warning(f"⚠️ [Emitter] Duplicate emission blocked (sync) for {self._request_id}")
            return False
        
        self._emitted = True
        self._emission_content = response
        self._emission_metadata = metadata or {}
        
        logger.info(f" [Emitter] Response ready (sync) for {self._request_id}")
        return True
    
    @property
    def was_emitted(self) -> bool:
        """Check if a response has been emitted."""
        return self._emitted
    
    @property
    def emitted_content(self) -> Optional[str]:
        """Get the emitted content (for testing/debugging)."""
        return self._emission_content
    
    @property
    def emitted_metadata(self) -> Optional[Dict]:
        """Get the emitted metadata (for testing/debugging)."""
        return self._emission_metadata


class EmitterFactory:
    """
    Factory for creating ResponseEmitters with consistent configuration.
    """
    
    def __init__(self, broadcaster: Optional[Any] = None):
        self._broadcaster = broadcaster
        self._request_counter = 0
    
    def create(self, request_id: Optional[str] = None) -> ResponseEmitter:
        """Create a new emitter for a request."""
        if not request_id:
            self._request_counter += 1
            request_id = f"req_{self._request_counter}"
        
        return ResponseEmitter(
            request_id=request_id,
            broadcaster=self._broadcaster
        )
    
    def set_broadcaster(self, broadcaster: Any) -> None:
        """Update the broadcaster (for late binding)."""
        self._broadcaster = broadcaster


# Global factory instance
_emitter_factory: Optional[EmitterFactory] = None


def get_emitter_factory() -> EmitterFactory:
    """Get the global emitter factory."""
    global _emitter_factory
    if _emitter_factory is None:
        _emitter_factory = EmitterFactory()
    return _emitter_factory


def create_emitter(request_id: Optional[str] = None) -> ResponseEmitter:
    """Convenience function to create an emitter."""
    return get_emitter_factory().create(request_id)
