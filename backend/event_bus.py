"""Thread-safe in-process pub/sub with bounded event replay.

The backend currently runs as one worker process. This hub gives SSE clients
reload-safe fanout inside that process without coupling publishers to live
connection queues. If the deployment is later scaled to multiple workers or
replicas, this module is the boundary to replace with Redis or another broker.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Condition, Lock
from typing import Any, Deque, Dict, Optional


@dataclass(frozen=True)
class BusEvent:
    seq: int
    event: str
    data: Any


class _Channel:
    def __init__(self, maxlen: int):
        self.condition = Condition()
        self.events: Deque[BusEvent] = deque(maxlen=maxlen)
        self.next_seq = 1


class EventBus:
    def __init__(self, max_history: int = 200):
        self._max_history = max_history
        self._channels: Dict[str, _Channel] = {}
        self._lock = Lock()

    def _channel(self, topic: str) -> _Channel:
        with self._lock:
            channel = self._channels.get(topic)
            if channel is None:
                channel = _Channel(self._max_history)
                self._channels[topic] = channel
            return channel

    def publish(self, topic: str, event: str, data: Any) -> BusEvent:
        channel = self._channel(topic)
        with channel.condition:
            item = BusEvent(seq=channel.next_seq, event=event, data=data)
            channel.next_seq += 1
            channel.events.append(item)
            channel.condition.notify_all()
            return item

    def latest(self, topic: str, event: Optional[str] = None) -> Optional[BusEvent]:
        channel = self._channel(topic)
        with channel.condition:
            for item in reversed(channel.events):
                if event is None or item.event == event:
                    return item
        return None

    def replay_after(self, topic: str, after_seq: int) -> list[BusEvent]:
        channel = self._channel(topic)
        with channel.condition:
            return [item for item in channel.events if item.seq > after_seq]

    def wait_after(self, topic: str, after_seq: int, timeout_s: float) -> list[BusEvent]:
        channel = self._channel(topic)
        with channel.condition:
            ready = [item for item in channel.events if item.seq > after_seq]
            if ready:
                return ready
            channel.condition.wait(timeout_s)
            return [item for item in channel.events if item.seq > after_seq]


event_bus = EventBus()
