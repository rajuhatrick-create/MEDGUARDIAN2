"""Validates config.py before any hardware is touched."""

VALID_LIMIT_ROLES = ("dock_detect", "snooze", "unassigned")
SLOTS = ("morning", "afternoon", "night")
# GPIOs the Pico W uses internally for its CYW43 Wi-Fi chip.
CYW43_RESERVED = (23, 24, 25, 29)


def used_pins(cfg):
    pins = {
        "servo1": cfg.PIN_SERVO_1, "servo2": cfg.PIN_SERVO_2,
        "servo3": cfg.PIN_SERVO_3, "servo4": cfg.PIN_SERVO_4,
        "limit_switch": cfg.PIN_LIMIT_SWITCH,
        "hx711_dout": cfg.PIN_HX711_DOUT, "hx711_sck": cfg.PIN_HX711_SCK,
    }
    if cfg.GPS_ENABLED:
        pins["gps_rx"] = cfg.PIN_GPS_RX
        pins["gps_tx"] = cfg.PIN_GPS_TX
    if cfg.BUZZER_ENABLED:
        pins["buzzer"] = cfg.PIN_BUZZER
    if cfg.HCSR04_ENABLED:
        pins["hcsr04_trig"] = cfg.PIN_HCSR04_TRIG
        pins["hcsr04_echo"] = cfg.PIN_HCSR04_ECHO
    if cfg.MPU6050_ENABLED:
        pins["mpu_sda"] = cfg.PIN_MPU6050_SDA
        pins["mpu_scl"] = cfg.PIN_MPU6050_SCL
    if cfg.PIN_LID_SWITCH is not None:
        pins["lid_switch"] = cfg.PIN_LID_SWITCH
    return pins


def validate(cfg):
    """Returns (errors, commissioning_issues).

    errors: the configuration is wrong; the firmware will not drive any servo.
    commissioning_issues: values not yet measured; dispensing stays locked.
    """
    errors, issues = [], []
    pins = used_pins(cfg)
    seen = {}
    for name, pin in pins.items():
        if not isinstance(pin, int) or not 0 <= pin <= 28:
            errors.append("%s pin %r is not a valid GPIO" % (name, pin))
            continue
        if cfg.NETWORK_TYPE == "cyw43" and pin in CYW43_RESERVED:
            errors.append("%s uses GP%d, reserved by Pico W Wi-Fi" % (name, pin))
        if pin in seen:
            errors.append("GP%d used by both %s and %s" % (pin, seen[pin], name))
        seen[pin] = name

    if cfg.GPS_ENABLED:
        # RP2040 UART1 valid pin pairs: TX GP4/8/20, RX GP5/9/21.
        if cfg.GPS_UART_ID != 1 or cfg.PIN_GPS_TX not in (4, 8, 20) or cfg.PIN_GPS_RX not in (5, 9, 21):
            errors.append("GPS pins are not a valid UART1 TX/RX pair")

    if sorted(cfg.SERVOS) != [1, 2, 3, 4]:
        errors.append("SERVOS must define servos 1-4")
    servo_pins = [s.get("pin") for s in cfg.SERVOS.values()]
    if len(set(servo_pins)) != len(servo_pins):
        errors.append("two servos share a pin")
    for n, s in cfg.SERVOS.items():
        if s.get("kind") not in ("positional", "continuous"):
            errors.append("servo %s kind must be positional or continuous" % n)
        if not (400 <= s.get("min_pulse_us", 0) < s.get("max_pulse_us", 0) <= 2600):
            errors.append("servo %s pulse range invalid" % n)
        if s.get("kind") == "positional":
            lo, hi = s.get("min_angle"), s.get("max_angle")
            if lo is None or hi is None or not 0 <= lo < hi <= 180:
                errors.append("servo %s angle limits invalid" % n)
            for key in ("closed_angle", "open_angle"):
                v = s.get(key)
                if v is not None and lo is not None and hi is not None and not lo <= v <= hi:
                    errors.append("servo %s %s outside its limits" % (n, key))
    if not 40 <= cfg.SERVO_FREQ_HZ <= 60:
        errors.append("SERVO_FREQ_HZ should be about 50 for SG90 servos")

    if cfg.LIMIT_SWITCH_ROLE not in VALID_LIMIT_ROLES:
        errors.append("LIMIT_SWITCH_ROLE must be one of %s" % (VALID_LIMIT_ROLES,))
    if cfg.HCSR04_ENABLED or cfg.MPU6050_ENABLED:
        errors.append("HC-SR04 / MPU6050 drivers are not included in this firmware")

    # ---- commissioning (not errors, but dispensing stays locked)
    flap = cfg.SERVOS.get(1, {})
    rot = cfg.SERVOS.get(2, {})
    if flap.get("role") != "portable_flap" or rot.get("role") != "daily_compartment":
        issues.append("servo roles for the portable sequence are not configured")
    if flap.get("closed_angle") is None or flap.get("open_angle") is None:
        issues.append("servo 1 flap closed/open angles not measured")
    for n in (1, 2):
        if not cfg.SERVOS.get(n, {}).get("limits_verified"):
            issues.append("servo %d mechanical limits not verified" % n)
    for slot in SLOTS:
        a = cfg.COMPARTMENT_ANGLES.get(slot)
        if a is None:
            issues.append("compartment angle for %s not measured" % slot)
        elif not rot.get("min_angle", 0) <= a <= rot.get("max_angle", 180):
            errors.append("compartment angle for %s outside servo 2 limits" % slot)
    if cfg.SCALE_OFFSET is None or not cfg.SCALE_COUNTS_PER_GRAM:
        issues.append("load cell not calibrated")
    if cfg.SCALE_STABLE_NOISE_G is None:
        issues.append("scale noise not measured")
    if cfg.DOSE_MIN_DELTA_G is None or cfg.DOSE_MAX_DELTA_G is None:
        issues.append("dose verification thresholds not set")
    elif not 0 < cfg.DOSE_MIN_DELTA_G < cfg.DOSE_MAX_DELTA_G:
        errors.append("dose thresholds must satisfy 0 < min < max")
    if cfg.PIN_LID_SWITCH is None:
        issues.append("no lid-closed sensor configured")
    if not cfg.ACTUATION_VERIFIED:
        issues.append("ACTUATION_VERIFIED is False (commissioning lock)")
    if not (cfg.DEVICE_ID and cfg.DEVICE_KEY and cfg.WIFI_SSID):
        issues.append("Wi-Fi or device credentials missing")
    return errors, issues
