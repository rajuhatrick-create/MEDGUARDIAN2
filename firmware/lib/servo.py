"""
SG90-style servo drivers.

No pulse is sent until attach() is called, and attach() does not move the horn:
it only starts PWM when the first move is requested. The firmware only knows the
COMMANDED position; SG90 servos have no position feedback.
"""
from compat import ticks_ms, ticks_diff


def pulse_to_duty_u16(pulse_us, freq_hz):
    period_us = 1000000 / freq_hz
    duty = int(round(pulse_us * 65535 / period_us))
    return max(0, min(65535, duty))


def angle_to_pulse_us(angle, min_pulse_us, max_pulse_us):
    """0..180 degrees -> pulse width. Angle is clamped to 0..180 first."""
    angle = max(0.0, min(180.0, float(angle)))
    return min_pulse_us + (max_pulse_us - min_pulse_us) * angle / 180.0


class ServoError(Exception):
    pass


class _BaseServo:
    def __init__(self, number, cfg, freq_hz=50, pwm_factory=None):
        self.number = number
        self.cfg = cfg
        self.role = cfg.get("role", "unassigned")
        self.freq_hz = freq_hz
        self._pwm_factory = pwm_factory
        self._pwm = None
        self.fault = None
        lo, hi = cfg["min_pulse_us"], cfg["max_pulse_us"]
        if not (400 <= lo < hi <= 2600):
            raise ServoError("servo %d pulse range %s-%s us is invalid" % (number, lo, hi))

    def _ensure_pwm(self):
        if self._pwm is None:
            if self._pwm_factory is None:
                from machine import Pin, PWM
                pwm = PWM(Pin(self.cfg["pin"]))
            else:
                pwm = self._pwm_factory(self.cfg["pin"])
            pwm.freq(self.freq_hz)
            self._pwm = pwm
        return self._pwm

    def _write_pulse(self, pulse_us):
        lo, hi = self.cfg["min_pulse_us"], self.cfg["max_pulse_us"]
        pulse_us = max(lo, min(hi, pulse_us))
        try:
            self._ensure_pwm().duty_u16(pulse_to_duty_u16(pulse_us, self.freq_hz))
        except Exception as e:
            self.fault = "servo%d_pwm_error" % self.number
            raise ServoError("servo %d PWM write failed: %s" % (self.number, e))

    def relax(self):
        """Stop sending pulses (servo goes limp)."""
        if self._pwm is not None:
            try:
                self._pwm.duty_u16(0)
            except Exception:
                pass

    def deinit(self):
        self.relax()
        if self._pwm is not None:
            try:
                self._pwm.deinit()
            finally:
                self._pwm = None


class PositionalServo(_BaseServo):
    """Normal 180-degree SG90. Moves are ramped so the main loop keeps running."""

    def __init__(self, number, cfg, freq_hz=50, pwm_factory=None):
        _BaseServo.__init__(self, number, cfg, freq_hz, pwm_factory)
        self.min_angle = float(cfg["min_angle"])
        self.max_angle = float(cfg["max_angle"])
        if not (0 <= self.min_angle < self.max_angle <= 180):
            raise ServoError("servo %d angle limits are invalid" % number)
        self.speed_dps = float(cfg.get("speed_dps", 60))
        self.commanded = None   # last angle actually sent; None = unknown since boot
        self.target = None
        self._last_ms = None

    def clamp(self, angle):
        return max(self.min_angle, min(self.max_angle, float(angle)))

    def move_to(self, angle, now_ms=None):
        """Start a ramped move. Returns the clamped target."""
        self.target = self.clamp(angle)
        self._last_ms = ticks_ms() if now_ms is None else now_ms
        if self.commanded is None:
            # Position unknown after boot: we cannot ramp from an unknown angle,
            # so the first command goes directly to the (clamped) target.
            self._send(self.target)
        return self.target

    def _send(self, angle):
        self._write_pulse(angle_to_pulse_us(angle, self.cfg["min_pulse_us"], self.cfg["max_pulse_us"]))
        self.commanded = angle

    def update(self, now_ms=None):
        if self.target is None or self.commanded is None or self.commanded == self.target:
            return
        now_ms = ticks_ms() if now_ms is None else now_ms
        dt = ticks_diff(now_ms, self._last_ms) / 1000.0
        if dt <= 0:
            return
        self._last_ms = now_ms
        step = self.speed_dps * dt
        diff = self.target - self.commanded
        nxt = self.target if abs(diff) <= step else self.commanded + (step if diff > 0 else -step)
        self._send(nxt)

    def at_target(self):
        return self.target is not None and self.commanded == self.target

    def status(self):
        return {"n": self.number, "role": self.role, "kind": "positional",
                "commanded_deg": self.commanded, "target_deg": self.target,
                "position_feedback": False, "fault": self.fault}


class ContinuousServo(_BaseServo):
    """360-degree SG90: the pulse sets speed/direction, not position."""

    def __init__(self, number, cfg, freq_hz=50, pwm_factory=None):
        _BaseServo.__init__(self, number, cfg, freq_hz, pwm_factory)
        self.stop_pulse_us = cfg.get("stop_pulse_us", 1500)
        self.max_speed_pct = max(0, min(100, cfg.get("max_speed_pct", 50)))
        self.speed_pct = 0
        self._stop_at = None

    def run(self, speed_pct, duration_ms, now_ms=None):
        """Run at speed_pct (-100..100, clamped to max_speed_pct) for duration_ms, then stop."""
        if duration_ms <= 0:
            raise ServoError("continuous servo needs a positive duration")
        speed = max(-self.max_speed_pct, min(self.max_speed_pct, speed_pct))
        half = (self.cfg["max_pulse_us"] - self.cfg["min_pulse_us"]) / 2.0
        self._write_pulse(self.stop_pulse_us + half * speed / 100.0)
        self.speed_pct = speed
        now_ms = ticks_ms() if now_ms is None else now_ms
        self._stop_at = now_ms + duration_ms
        return speed

    def stop(self):
        if self._pwm is not None:
            self._write_pulse(self.stop_pulse_us)
            self.relax()
        self.speed_pct = 0
        self._stop_at = None

    def update(self, now_ms=None):
        now_ms = ticks_ms() if now_ms is None else now_ms
        if self._stop_at is not None and ticks_diff(now_ms, self._stop_at) >= 0:
            self.stop()

    def at_target(self):
        return self._stop_at is None

    def status(self):
        return {"n": self.number, "role": self.role, "kind": "continuous",
                "speed_pct": self.speed_pct, "position_feedback": False, "fault": self.fault}


def build_servos(servo_cfg, freq_hz=50, pwm_factory=None):
    """Create all servo objects without sending any pulse."""
    out = {}
    for number in sorted(servo_cfg):
        cfg = servo_cfg[number]
        cls = ContinuousServo if cfg.get("kind") == "continuous" else PositionalServo
        out[number] = cls(number, cfg, freq_hz, pwm_factory)
    return out
