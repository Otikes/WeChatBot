"""MemoryConsolidator — triggers and orchestrates group memory updates.

Core logic:
- After every N new messages (default 30), or
- After T hours since last consolidation (default 2h),
  consolidate the new messages into the group's memory diary.

Uses the configured summarizer backend for low-cost, low-latency consolidation.
"""

import concurrent.futures
import logging
import queue
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..db.store import MessageStore
    from ..summarize.base import AbstractSummarizer

logger = logging.getLogger(__name__)

# ── Tuning constants ─────────────────────────────────────────────────

# Trigger consolidation after this many NEW messages
CONSOLIDATE_MSG_THRESHOLD = 50
# Or after this many seconds since last consolidation (with new messages)
CONSOLIDATE_TIME_THRESHOLD_SEC = 1 * 3600  # 1 hour
# Maximum new messages to send per consolidation (limits prompt size)
MAX_NEW_MSGS_PER_CONSOLIDATION = 400


class MemoryConsolidator:
    """Checks consolidation triggers and orchestrates memory updates.

    Usage:
        consolidator = MemoryConsolidator(store, summarizer)

        # In router.handle(), after persisting each message:
        consolidator.schedule(chat_id)  # non-blocking, coalesced per chat

        # At shutdown:
        consolidator.close()
    """

    def __init__(self, store: "MessageStore",
                 summarizer: "AbstractSummarizer"):
        self._store = store
        self._summarizer = summarizer
        # Consolidation runs on a single background worker so a 2–4 s AI
        # call never blocks message callbacks or reply sending.  Requests
        # for the same chat are coalesced: at most one run per chat, and
        # bursts of messages collapse into a single follow-up run.
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.Lock()
        self._inflight: set[str] = set()
        self._pending: set[str] = set()
        self._worker: threading.Thread | None = None
        self._closed = False

    def schedule(self, chat_id: str) -> None:
        """Queue a consolidation check without blocking the caller."""
        with self._lock:
            if self._closed:
                return
            if chat_id in self._inflight:
                self._pending.add(chat_id)
                return
            self._inflight.add(chat_id)
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run_worker,
                    name="memory-consolidator",
                    daemon=True,
                )
                self._worker.start()
        self._queue.put(chat_id)

    def close(self) -> None:
        """Stop the background worker (in-flight work may be abandoned)."""
        with self._lock:
            self._closed = True
            worker = self._worker
        if worker is None:
            return
        self._queue.put(None)
        worker.join(timeout=1.0)

    def check_and_consolidate(self, chat_id: str) -> bool:
        """Check if consolidation is needed and run it if so.

        Returns True if consolidation was performed, False if skipped.
        Never raises — all errors are caught and logged internally.
        """
        try:
            return self._check_and_consolidate_impl(chat_id)
        except Exception as e:
            logger.error(
                "Memory consolidation error for chat %s: %s",
                chat_id[:30], e,
            )
            return False

    # ── Internal ───────────────────────────────────────────────────

    def _run_worker(self) -> None:
        """Background loop: run queued checks, re-running coalesced bursts."""
        while True:
            chat_id = self._queue.get()
            if chat_id is None:
                return
            try:
                self.check_and_consolidate(chat_id)
            finally:
                with self._lock:
                    self._inflight.discard(chat_id)
                    rerun = chat_id in self._pending and not self._closed
                    self._pending.discard(chat_id)
                    if rerun:
                        self._inflight.add(chat_id)
                if rerun:
                    self._queue.put(chat_id)

    def _check_and_consolidate_impl(self, chat_id: str) -> bool:
        """Internal: check triggers and run consolidation."""
        memory = self._store.get_group_memory(chat_id)
        last_id = memory["last_message_id"] if memory else None
        last_consolidated = memory["last_consolidated"] if memory else None

        # Count new messages since last consolidation
        new_count = self._store.get_new_message_count(chat_id, last_id)

        # Trigger check
        # 首次合并使用 Unix epoch 作为虚拟基点，使时间阈值自然生效
        effective_last = last_consolidated if last_consolidated is not None else 0
        time_ok = (time.time() - effective_last) >= CONSOLIDATE_TIME_THRESHOLD_SEC
        msg_ok = new_count >= CONSOLIDATE_MSG_THRESHOLD

        if not time_ok and not msg_ok:
            return False  # nothing to do

        if new_count == 0:
            return False  # no new messages to incorporate

        # Fetch new messages
        new_messages = self._store.get_messages_since_id(
            chat_id, last_id, limit=MAX_NEW_MSGS_PER_CONSOLIDATION,
        )
        if not new_messages:
            return False

        existing_memory = memory["memory_text"] if memory else ""

        logger.info(
            "Consolidating memory for %s (%d new msgs, existing memory=%d chars)...",
            chat_id[:30], len(new_messages), len(existing_memory),
        )

        # Call AI consolidation with a 30s timeout so a hung API
        # doesn't block the message-processing loop indefinitely.
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    self._summarizer.consolidate_memory,
                    existing_memory=existing_memory,
                    new_messages=new_messages,
                )
                updated = future.result(timeout=30)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "Memory consolidation timed out after 30s for %s — skipping this cycle",
                chat_id[:30],
            )
            return False

        if not updated or updated == existing_memory:
            logger.info(
                "Memory consolidation returned unchanged text for %s — skipping write",
                chat_id[:30],
            )
            return False

        # Persist
        total_count = (memory["message_count"] if memory else 0) + len(new_messages)
        last_msg_id = new_messages[-1]["message_id"]

        self._store.upsert_group_memory(
            chat_id=chat_id,
            memory_text=updated,
            message_count=total_count,
            last_message_id=last_msg_id,
        )

        logger.info(
            "Memory consolidated for %s: %d msgs → %d chars (total %d msgs processed)",
            chat_id[:30], len(new_messages), len(updated), total_count,
        )
        return True
