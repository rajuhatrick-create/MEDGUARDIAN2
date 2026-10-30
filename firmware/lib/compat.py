"""Small helpers so the same code runs on MicroPython (Pico W) and on a PC for tests."""
import time

try:
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    ticks_add = time.ticks_add
    sleep_ms = time.sleep_ms
    sleep_us = time.sleep_us
    ticks_us = time.ticks_us
except AttributeError:  # CPython (host tests)
    def ticks_ms():
        return int(time.monotonic() * 1000)

    def ticks_us():
        return int(time.monotonic() * 1000000)

    def ticks_diff(a, b):
        return a - b

    def ticks_add(a, b):
        return a + b

    def sleep_ms(ms):
        time.sleep(ms / 1000)

    def sleep_us(us):
        time.sleep(us / 1000000)

# Some MicroPython ports count seconds from 2000-01-01 instead of 1970-01-01.
EPOCH_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0


def unix_time():
    """Seconds since 1970-01-01 UTC from the local RTC (may be untrusted)."""
    return int(time.time()) + EPOCH_OFFSET


def log(*parts):
    print("[%d]" % (ticks_ms() // 1000), *parts)
