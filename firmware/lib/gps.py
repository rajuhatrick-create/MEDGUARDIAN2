"""
Non-blocking NMEA reader for a UART GPS (e.g. NEO-6M).

"Receiving NMEA" and "having a satellite fix" are reported separately.
Coordinates are only exposed while a valid fix is held.
"""
from compat import ticks_ms, ticks_diff


def nmea_checksum_ok(line):
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, given = line[1:].partition("*")
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(given[:2], 16)
    except ValueError:
        return False


def _to_degrees(value, hemi):
    if not value or hemi not in ("N", "S", "E", "W"):
        return None
    try:
        dot = value.index(".")
        deg = float(value[:dot - 2])
        minutes = float(value[dot - 2:])
    except ValueError:
        return None
    result = deg + minutes / 60.0
    if hemi in ("S", "W"):
        result = -result
    limit = 90 if hemi in ("N", "S") else 180
    return result if -limit <= result <= limit else None


class GPS:
    def __init__(self, uart_id=1, baud=9600, tx_no=8, rx_no=9, uart=None, stale_ms=5000):
        if uart is None:
            from machine import UART, Pin
            uart = UART(uart_id, baudrate=baud, tx=Pin(tx_no), rx=Pin(rx_no), timeout=0)
        self._uart = uart
        self._buf = b""
        self.stale_ms = stale_ms
        self.sentences_ok = 0
        self.checksum_errors = 0
        self.malformed = 0
        self.last_sentence_ms = None
        self._fix = False
        self._fix_ms = None
        self.lat = self.lon = None
        self.satellites = None
        self.hdop = None
        self.utc = None

    def poll(self, now_ms=None):
        now_ms = ticks_ms() if now_ms is None else now_ms
        try:
            n = self._uart.any()
            if n:
                self._buf += self._uart.read(n) or b""
        except Exception:
            self.malformed += 1
            return
        if len(self._buf) > 512:          # garbage without newlines: drop it
            self._buf = self._buf[-128:]
            self.malformed += 1
        while b"\n" in self._buf:
            raw, self._buf = self._buf.split(b"\n", 1)
            try:
                line = raw.decode().strip()
            except Exception:
                self.malformed += 1
                continue
            if line:
                self.feed_line(line, now_ms)

    def feed_line(self, line, now_ms=None):
        now_ms = ticks_ms() if now_ms is None else now_ms
        if not nmea_checksum_ok(line):
            self.checksum_errors += 1
            return
        self.sentences_ok += 1
        self.last_sentence_ms = now_ms
        fields = line[1:line.index("*")].split(",")
        kind = fields[0][2:]
        try:
            if kind == "RMC" and len(fields) >= 7:
                self.utc = fields[1] or None
                if fields[2] == "A":
                    lat, lon = _to_degrees(fields[3], fields[4]), _to_degrees(fields[5], fields[6])
                    if lat is not None and lon is not None:
                        self._set_fix(lat, lon, now_ms)
                        return
                self._fix = False
            elif kind == "GGA" and len(fields) >= 9:
                quality = int(fields[6] or 0)
                self.satellites = int(fields[7]) if fields[7] else None
                self.hdop = float(fields[8]) if fields[8] else None
                if quality > 0:
                    lat, lon = _to_degrees(fields[2], fields[3]), _to_degrees(fields[4], fields[5])
                    if lat is not None and lon is not None:
                        self._set_fix(lat, lon, now_ms)
                        return
                self._fix = False
        except ValueError:
            self.malformed += 1

    def _set_fix(self, lat, lon, now_ms):
        self._fix = True
        self._fix_ms = now_ms
        self.lat, self.lon = lat, lon

    def has_fix(self, now_ms=None):
        now_ms = ticks_ms() if now_ms is None else now_ms
        return self._fix and self._fix_ms is not None and ticks_diff(now_ms, self._fix_ms) <= self.stale_ms

    def state(self, now_ms=None):
        now_ms = ticks_ms() if now_ms is None else now_ms
        if self.last_sentence_ms is None or ticks_diff(now_ms, self.last_sentence_ms) > self.stale_ms:
            return "no_data"
        return "fix" if self.has_fix(now_ms) else "nmea_no_fix"

    def status(self, now_ms=None):
        now_ms = ticks_ms() if now_ms is None else now_ms
        fix = self.has_fix(now_ms)
        return {"state": self.state(now_ms), "fix": fix,
                "lat": round(self.lat, 6) if fix else None,
                "lon": round(self.lon, 6) if fix else None,
                "satellites": self.satellites, "hdop": self.hdop,
                "sentences_ok": self.sentences_ok, "checksum_errors": self.checksum_errors}

    def deinit(self):
        try:
            self._uart.deinit()
        except Exception:
            pass
