"""Barrier control for the two lanes.

MockGateController stands in for the Arduinos until the serial link exists. It
applies the same safety rules the Arduino sketch must follow:
  * never close while the IR sensor sees a vehicle under the barrier
  * close `close_delay` seconds after the IR sensor is clear
Every state change is pushed to the dashboard as a "barrier" Socket.IO event.
"""
import threading


class GateController:
    def open(self, lane):
        """Lift the barrier: green LED, short beep."""
        raise NotImplementedError

    def hold(self, lane):
        """Keep the barrier closed: red LED, long beep (wait for guard / denied)."""
        raise NotImplementedError

    def set_vehicle_present(self, lane, present):
        """IR sensor reading for the lane."""
        raise NotImplementedError

    def snapshot(self):
        """{lane: {"barrier", "led", "vehicle_present"}} for the dashboard."""
        raise NotImplementedError


class MockGateController(GateController):
    def __init__(self, socketio, lanes, close_delay=3.0, open_timeout=15.0):
        self._socketio = socketio
        self._close_delay = close_delay
        self._open_timeout = open_timeout
        self._lock = threading.Lock()
        self._lanes = {lane: {"barrier": "closed", "led": "off", "vehicle_present": False} for lane in lanes}
        self._timers = {}

    def open(self, lane):
        with self._lock:
            state = self._lanes[lane]
            state.update(barrier="open", led="green")
            if not state["vehicle_present"]:
                self._schedule_close(lane, self._open_timeout)
        self._emit(lane, buzzer="short")

    def hold(self, lane):
        with self._lock:
            self._lanes[lane]["led"] = "red"
        self._emit(lane, buzzer="long")

    def set_vehicle_present(self, lane, present):
        with self._lock:
            state = self._lanes[lane]
            state["vehicle_present"] = present
            if present:
                self._cancel(lane)
            elif state["barrier"] == "open":
                self._schedule_close(lane, self._close_delay)
        self._emit(lane)

    def snapshot(self):
        with self._lock:
            return {lane: dict(state) for lane, state in self._lanes.items()}

    # Callers hold self._lock for the two helpers below.
    def _schedule_close(self, lane, delay):
        self._cancel(lane)
        timer = threading.Timer(delay, lambda: self._close(lane, timer))
        timer.daemon = True
        self._timers[lane] = timer
        timer.start()

    def _cancel(self, lane):
        timer = self._timers.pop(lane, None)
        if timer is not None:
            timer.cancel()

    def _close(self, lane, timer):
        with self._lock:
            if self._timers.get(lane) is not timer:
                return  # replaced or cancelled after it fired
            del self._timers[lane]
            state = self._lanes[lane]
            if state["vehicle_present"]:
                return  # safety: the IR clear event will schedule the close
            state.update(barrier="closed", led="off")
        self._emit(lane)

    def _emit(self, lane, buzzer=None):
        with self._lock:
            payload = {"lane": lane, **self._lanes[lane], "buzzer": buzzer}
        self._socketio.emit("barrier", payload)
