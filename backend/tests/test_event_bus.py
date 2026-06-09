from backend.event_bus import EventBus


def test_publish_replay_and_wait():
    bus = EventBus(max_history=10)

    first = bus.publish("job:1", "progress", {"step": "vad", "current": 1})
    second = bus.publish("job:1", "progress", {"step": "vad", "current": 2})

    assert first.seq == 1
    assert second.seq == 2
    assert bus.replay_after("job:1", 0) == [first, second]
    assert bus.replay_after("job:1", 1) == [second]
    assert bus.wait_after("job:1", 1, 0.01) == [second]


def test_latest_can_filter_by_event_name():
    bus = EventBus(max_history=10)

    progress = bus.publish("job:1", "progress", {"step": "vad"})
    bus.publish("job:1", "vad_done", {"pauses_count": 3})

    assert bus.latest("job:1", "progress") == progress
    assert bus.latest("job:1").event == "vad_done"
