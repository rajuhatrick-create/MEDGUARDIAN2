"""
Debounced mechanical switch (limit switch, optional lid switch).

Wiring: COM -> GND, NO -> GPIO, internal pull-up on. Pressed reads LOW.
Call update() often (every loop). Each press produces exactly one "pressed"
edge no matter how much the contacts bounce.
"""
from compat import ticks_ms, ticks_diff


class DebouncedSwitch:
    def __init__(self, pin_no, debounce_ms=30, active_low=True, pin=None, name="switch"):
        self.name = name
        self.debounce_ms = debounce_ms
        self.active_low = active_low
        if pin is None:
            from machine import Pin
            pin = Pin(pin_no, Pin.IN, Pin.PULL_UP)
        self._pin = pin
        self.active = None       # None until a stable reading exists
        self._candidate = None
        self._since = None
        self.press_count = 0
        self._edges = []
        self.fault = None

    def _raw_active(self):
        v = self._pin.value()
        return (v == 0) if self.active_low else (v == 1)

    @property
    def ready(self):
        return self.active is not None and self.fault is None

    def update(self, now_ms=None):
        now_ms = ticks_ms() if now_ms is None else now_ms
        try:
            raw = self._raw_active()
        except Exception as e:
            self.fault = "%s_read_error" % self.name
            self.active = None
            return
        if raw != self._candidate:
            self._candidate = raw
            self._since = now_ms
            return
        if raw != self.active and ticks_diff(now_ms, self._since) >= self.debounce_ms:
            previous = self.active
            self.active = raw
            if previous is not None:          # no edge for the very first stable reading
                self._edges.append("pressed" if raw else "released")
                if raw:
                    self.press_count += 1

    def take_edges(self):
        """Returns and clears the list of edges seen since the last call."""
        edges, self._edges = self._edges, []
        return edges

    def status(self):
        return {"ready": self.ready, "active": self.active, "presses": self.press_count, "fault": self.fault}
