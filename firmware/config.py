"""
Med Guardian portable unit - central configuration.

EVERY GPIO number used by the firmware lives in this file. Use GPIO numbers (GPxx),
never physical header pin numbers. The physical pins are listed in the comments
and in HARDWARE_WIRING.md for wiring only.

Values marked None are UNKNOWN until you measure/commission them. While they are
None the firmware keeps dispensing locked. Do not guess them.
"""

FIRMWARE_VERSION = "2.0.0-four-servo"

# ---------------------------------------------------------------- network
# Board network type. "cyw43" = official Raspberry Pi Pico W built-in Wi-Fi.
# The original project's transport could not be inspected (its ZIP was not supplied).
# If your board uses an ESP8266/ESP8285 AT co-processor instead, this firmware's
# network module will NOT work as-is; see README "Network hardware".
NETWORK_TYPE = "cyw43"
WIFI_SSID = ""          # fill in over USB; never commit real values
WIFI_PASSWORD = ""
WIFI_COUNTRY = "IN"
SERVER_URL = "https://sparkly-souffle-7fe8b2.netlify.app"
DEVICE_ID = ""          # from the dashboard "Register device" panel
DEVICE_KEY = ""         # shown once by the dashboard; keep private
HTTP_TIMEOUT_S = 8      # bounded so the control loop never blocks indefinitely
SYNC_INTERVAL_S = 5     # dashboard treats >30 s without telemetry as offline
NTP_HOST = "pool.ntp.org"
CLOCK_MAX_AGE_S = 24 * 3600  # clock is "untrusted" if not synced within this time

# ---------------------------------------------------------------- GPIO map
# Component                GPIO   physical pin
PIN_SERVO_1 = 18         # GP18   24
PIN_SERVO_2 = 19         # GP19   25
PIN_SERVO_3 = 20         # GP20   26
PIN_SERVO_4 = 21         # GP21   27
PIN_LIMIT_SWITCH = 16    # GP16   21   COM->GND, NO->GP16, internal pull-up
PIN_HX711_DOUT = 2       # GP2    4
PIN_HX711_SCK = 3        # GP3    5
GPS_UART_ID = 1
PIN_GPS_RX = 9           # GP9    12   Pico UART1 RX  <- GPS TX
PIN_GPS_TX = 8           # GP8    11   Pico UART1 TX  -> GPS RX (optional)
# Optional parts - only used when the matching *_ENABLED flag is True.
PIN_BUZZER = 14          # GP14   19
PIN_HCSR04_TRIG = 4      # GP4    6    (reserved, driver not included)
PIN_HCSR04_ECHO = 5      # GP5    7    (reserved; ECHO is 5 V - needs a divider)
PIN_MPU6050_SDA = 6      # GP6    9    (reserved, I2C1 SDA, driver not included)
PIN_MPU6050_SCL = 7      # GP7    10   (reserved, I2C1 SCL, driver not included)
BUZZER_ENABLED = False
HCSR04_ENABLED = False   # no driver in this version; keep False
MPU6050_ENABLED = False  # no driver in this version; keep False

# Lid-closed interlock. The new parts list has no lid sensor, so this is None and
# the lid is reported as UNKNOWN, which keeps dispensing blocked (by design).
# If you add a lid switch (COM->GND, NO->GPIO, closed lid = LOW) put its GPIO here,
# e.g. 17 (GP17, physical pin 22) - it must not clash with any pin above.
PIN_LID_SWITCH = None

# ---------------------------------------------------------------- servos
SERVO_FREQ_HZ = 50
# role: what the servo physically does (from the project owner).
# kind: "positional" = normal 180-degree SG90; "continuous" = 360-degree SG90 (speed, not angle).
# min_angle/max_angle: MECHANICAL limits of YOUR linkage. Commands are clamped to these.
# limits_verified: set True only after you have checked the range with the horn attached.
SERVOS = {
    1: {"pin": PIN_SERVO_1, "role": "portable_flap", "label": "Portable flap open",
        "kind": "positional", "min_pulse_us": 500, "max_pulse_us": 2400,
        "min_angle": 0, "max_angle": 180, "closed_angle": None, "open_angle": None,
        "speed_dps": 90, "limits_verified": False},
    2: {"pin": PIN_SERVO_2, "role": "daily_compartment", "label": "Daily compartment rotation",
        "kind": "positional", "min_pulse_us": 500, "max_pulse_us": 2400,
        "min_angle": 0, "max_angle": 180, "speed_dps": 60, "limits_verified": False},
    3: {"pin": PIN_SERVO_3, "role": "storage_360", "label": "360 storage",
        "kind": "continuous", "min_pulse_us": 500, "max_pulse_us": 2400,
        "stop_pulse_us": 1500, "max_speed_pct": 50, "limits_verified": False},
    4: {"pin": PIN_SERVO_4, "role": "dock_flap", "label": "Dock flap open",
        "kind": "positional", "min_pulse_us": 500, "max_pulse_us": 2400,
        "min_angle": 0, "max_angle": 180, "closed_angle": None, "open_angle": None,
        "speed_dps": 90, "limits_verified": False},
}

# Servo 2 angle that lines up each slot's compartment with the portable flap.
# Unknown until measured. A slot with None can never be dispensed.
COMPARTMENT_ANGLES = {"morning": None, "afternoon": None, "night": None}

# Portable dispense sequence uses servo 2 (rotate) then servo 1 (flap).
# Servo 3 (storage) and servo 4 (dock flap) belong to the docking/refill design,
# which is disabled in this version - they are never moved by the firmware.
DOCK_ENABLED = False
FLAP_OPEN_HOLD_MS = 1500
POST_RELEASE_SETTLE_MS = 2000
MOVE_TIMEOUT_MS = 6000

# Master commissioning lock. Set True only after PHYSICAL_TEST_CHECKLIST.md is complete.
ACTUATION_VERIFIED = False

# ---------------------------------------------------------------- limit switch
# What the limit switch detects. The previous app/firmware used it for DOCK detection,
# so that is the default. Options:
#   "dock_detect"  pressed = unit is docked (dispensing blocked while pressed)
#   "snooze"       pressed = snooze the current reminder (replaces the old push button)
#   "unassigned"   read and reported only
# A limit-switch press NEVER triggers dispensing in any role.
LIMIT_SWITCH_ROLE = "dock_detect"
LIMIT_SWITCH_ACTIVE_LOW = True
LIMIT_SWITCH_DEBOUNCE_MS = 30

# ---------------------------------------------------------------- load cell
HX711_GAIN = 128
HX711_READY_TIMEOUT_MS = 500
HX711_STALE_MS = 3000
SCALE_OFFSET = None            # raw counts with the empty cup removed (from tools/calibrate.py)
SCALE_COUNTS_PER_GRAM = None   # from tools/calibrate.py with a known reference mass
SCALE_STABLE_SAMPLES = 8
SCALE_STABLE_NOISE_G = None    # measured peak-to-peak noise of a still scale
# Dose verification thresholds (mass change into the cup). Unknown until measured
# with your inert test objects. None keeps dispensing locked.
DOSE_MIN_DELTA_G = None
DOSE_MAX_DELTA_G = None

# ---------------------------------------------------------------- GPS
GPS_ENABLED = True
GPS_BAUD = 9600          # common default; check your module's datasheet
GPS_STALE_MS = 5000

# ---------------------------------------------------------------- schedule
TIMEZONE_OFFSET_MIN = 330      # IST (UTC+05:30), matches the dashboard
OCCURRENCE_WINDOW_MIN = 60     # a reminder stays "current" for this long
SNOOZE_MIN = 5

# ---------------------------------------------------------------- watchdog
# RP2040 watchdog max is ~8.3 s. Leave False unless HTTP_TIMEOUT_S is well below that.
WATCHDOG_ENABLED = False
WATCHDOG_TIMEOUT_MS = 8000
