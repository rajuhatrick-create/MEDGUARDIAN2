"""
HX711 load-cell amplifier (bit-banged) plus a Scale helper.

read_raw() never waits forever: if DOUT does not go LOW within the timeout an
HX711Error is raised. A weight reading only describes a mass change on the scale;
it cannot identify a tablet or prove it is medically correct.
"""
from compat import ticks_ms, ticks_diff, sleep_us

_GAIN_PULSES = {128: 1, 64: 3, 32: 2}


class HX711Error(Exception):
    pass


class HX711:
    def __init__(self, dout_no, sck_no, gain=128, dout=None, sck=None):
        if gain not in _GAIN_PULSES:
            raise HX711Error("gain must be 128, 64 or 32")
        if dout is None or sck is None:
            from machine import Pin
            dout = Pin(dout_no, Pin.IN)
            sck = Pin(sck_no, Pin.OUT, value=0)
        self._dout, self._sck = dout, sck
        self._extra = _GAIN_PULSES[gain]
        self._sck.value(0)

    def is_ready(self):
        return self._dout.value() == 0

    def read_raw(self, timeout_ms=500):
        start = ticks_ms()
        while not self.is_ready():
            if ticks_diff(ticks_ms(), start) > timeout_ms:
                raise HX711Error("HX711 not ready (check wiring/power)")
            sleep_us(200)
        value = 0
        for _ in range(24):
            self._sck.value(1)
            self._sck.value(0)
            value = (value << 1) | self._dout.value()
        for _ in range(self._extra):
            self._sck.value(1)
            self._sck.value(0)
        if value & 0x800000:
            value -= 0x1000000
        # All-ones / saturated values usually mean a disconnected or broken cell.
        if value in (-0x800000, 0x7FFFFF, -1):
            raise HX711Error("HX711 returned an invalid/saturated value %d" % value)
        return value

    def power_down(self):
        self._sck.value(0)
        self._sck.value(1)
        sleep_us(80)

    def power_up(self):
        self._sck.value(0)


class Scale:
    """Keeps a short history of readings and reports grams, stability and freshness."""

    def __init__(self, hx, offset=None, counts_per_gram=None, samples=8,
                 noise_g=None, stale_ms=3000, timeout_ms=500):
        self.hx = hx
        self.offset = offset
        self.counts_per_gram = counts_per_gram
        self.samples = samples
        self.noise_g = noise_g
        self.stale_ms = stale_ms
        self.timeout_ms = timeout_ms
        self._history = []
        self.last_raw = None
        self.last_ok_ms = None
        self.error = None

    @property
    def calibrated(self):
        return self.offset is not None and bool(self.counts_per_gram) and self.noise_g is not None

    def poll(self, now_ms=None):
        """Non-blocking: takes a reading only if the HX711 is ready."""
        now_ms = ticks_ms() if now_ms is None else now_ms
        try:
            if not self.hx.is_ready():
                return False
            raw = self.hx.read_raw(self.timeout_ms)
        except HX711Error as e:
            self.error = str(e)
            return False
        self.error = None
        self.last_raw = raw
        self.last_ok_ms = now_ms
        self._history.append(raw)
        if len(self._history) > self.samples:
            self._history.pop(0)
        return True

    def fresh(self, now_ms=None):
        now_ms = ticks_ms() if now_ms is None else now_ms
        return self.last_ok_ms is not None and ticks_diff(now_ms, self.last_ok_ms) <= self.stale_ms

    def grams(self, now_ms=None):
        """Average mass in grams, or None if uncalibrated, stale or missing."""
        if not self.calibrated or not self._history or not self.fresh(now_ms):
            return None
        avg = sum(self._history) / len(self._history)
        return (avg - self.offset) / self.counts_per_gram

    def stable(self, now_ms=None):
        """True/False when known; None when it cannot be judged."""
        if not self.calibrated or len(self._history) < self.samples or not self.fresh(now_ms):
            return None
        spread = (max(self._history) - min(self._history)) / abs(self.counts_per_gram)
        return spread <= self.noise_g

    def clear_history(self):
        self._history = []

    def fault(self, now_ms=None):
        if self.error:
            return "hx711_error"
        if self.last_ok_ms is not None and not self.fresh(now_ms):
            return "hx711_stale"
        return None
