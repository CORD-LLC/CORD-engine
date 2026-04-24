"""
CORD Engine — Event Logger
Builds typed, timestamped event log entries for CORD envelopes.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from api.models import EventLogEntry


class EventLogger:
    """
    Builds and accumulates event log entries for a CORD envelope.
    Entries are ordered by the sequence they are added.
    """

    def __init__(self):
        self._entries: List[EventLogEntry] = []

    def utterance(self, actor: str, content: str, timestamp: Optional[str] = None) -> "EventLogger":
        """Record a spoken or typed utterance from a user or agent."""
        self._entries.append(EventLogEntry(
            event_type="utterance",
            timestamp=timestamp or self._now(),
            actor=actor,
            content=content,
        ))
        return self

    def classification(self, actor: str, field: str, timestamp: Optional[str] = None) -> "EventLogger":
        """Record an AI classification event that produced a field value."""
        self._entries.append(EventLogEntry(
            event_type="classification",
            timestamp=timestamp or self._now(),
            actor=actor,
            field=field,
        ))
        return self

    def input(self, actor: str, content: str, timestamp: Optional[str] = None) -> "EventLogger":
        """Record a structured input event (form submission, API call, etc.)."""
        self._entries.append(EventLogEntry(
            event_type="input",
            timestamp=timestamp or self._now(),
            actor=actor,
            content=content,
        ))
        return self

    def signal(self, actor: str, data: Dict[str, Any], timestamp: Optional[str] = None) -> "EventLogger":
        """Record an external signal (behavioral event, webhook, etc.)."""
        self._entries.append(EventLogEntry(
            event_type="signal",
            timestamp=timestamp or self._now(),
            actor=actor,
            data=data,
        ))
        return self

    def handoff(self, actor: str, content: str, timestamp: Optional[str] = None) -> "EventLogger":
        """Record a handoff between systems or agents."""
        self._entries.append(EventLogEntry(
            event_type="handoff",
            timestamp=timestamp or self._now(),
            actor=actor,
            content=content,
        ))
        return self

    def error(self, actor: str, content: str, timestamp: Optional[str] = None) -> "EventLogger":
        """Record an error event."""
        self._entries.append(EventLogEntry(
            event_type="error",
            timestamp=timestamp or self._now(),
            actor=actor,
            content=content,
        ))
        return self

    def entries(self) -> List[EventLogEntry]:
        """Return all accumulated event log entries."""
        return list(self._entries)

    def reset(self) -> None:
        """Clear all entries."""
        self._entries = []

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat() + "Z"
