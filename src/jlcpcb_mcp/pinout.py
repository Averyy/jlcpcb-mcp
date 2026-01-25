"""EasyEDA pinout parser for extracting pin information from component symbols."""

import json
import re
from typing import Any

# Keywords for name-based type detection fallback
# Note: Order matters - ground checked before power to handle VSS before VS
POWER_KEYWORDS = ['VCC', 'VDD', 'VBAT', '3V3', '5V', '3.3V', 'VBUS', 'VIN', 'VOUT', 'V+', 'AVCC', 'DVCC']
GROUND_KEYWORDS = ['GND', 'VSS', 'AGND', 'DGND', 'VEE', 'V-', 'EP', 'PGND']

# Peripheral prefixes for function splitting
PERIPHERAL_PREFIXES = [
    'USART', 'UART', 'SPI', 'I2C', 'ADC', 'DAC', 'TIM', 'CAN',
    'USB', 'COMP', 'OPAMP', 'WKUP', 'JTAG', 'SWD', 'ETH', 'SDIO',
    'FSMC', 'RTC', 'MCO', 'TRACECLK', 'TAMPER', 'OSC', 'BOOT'
]

# Pre-compiled regex patterns for pin parsing (performance optimization)
_START_LABEL_PATTERN = re.compile(r"~([^~]+)~start~~~")
_END_LABEL_PATTERN = re.compile(r"~([^~]+)~end~~~")
_COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}")
_GPIO_UNDERSCORE_PATTERN = re.compile(r"^(P[A-K]\d+)_(.+)$")
_GPIO_NOUNDERSCORE_PATTERN = re.compile(r"^(P[A-K]\d+)([A-Z].*)$")
_PERIPHERAL_PATTERN = re.compile(f"({"|".join(PERIPHERAL_PREFIXES)})")

# Interface detection patterns for summary generation (pre-compiled)
INTERFACE_PATTERNS = {
    'i2c': re.compile(r'I2C(\d*)'),
    'spi': re.compile(r'SPI(\d*)'),
    'usart': re.compile(r'USART(\d*)'),
    'uart': re.compile(r'UART(\d*)'),
    'can': re.compile(r'CAN(\d*)'),
    'usb': re.compile(r'USB'),
    'adc': re.compile(r'ADC\d*_IN(\d+)'),
    'dac': re.compile(r'DAC(\d*)'),
    'timer': re.compile(r'TIM(\d+)'),
    'eth': re.compile(r'ETH'),
    'sdio': re.compile(r'SDIO'),
    'i2s': re.compile(r'I2S(\d*)'),
}


def parse_easyeda_pins(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse pin data from EasyEDA component response.

    Pin format varies by orientation:
    - Left-side pins: ~{NAME}~start~~~...~{NUM}~end~~~
    - Right-side pins: ~{NUM}~start~~~...~{NAME}~end~~~

    We check both positions and pick the non-numeric label as the name.

    Args:
        data: EasyEDA component response dict with dataStr.shape array

    Returns:
        List of pin dicts with number, name, functions, and type.
    """
    pins = []
    data_str = data.get("dataStr", {})

    # Handle both string and dict dataStr
    if isinstance(data_str, str):
        try:
            data_str = json.loads(data_str)
        except (json.JSONDecodeError, TypeError):
            return []

    # Type guard for non-dict dataStr
    if not isinstance(data_str, dict):
        return []

    shape = data_str.get("shape", [])
    if not shape:
        return []

    for element in shape:
        if not isinstance(element, str) or not element.startswith("P~"):
            continue

        # Extract pin number (field index 3 after P~show~0~)
        parts = element.split("~")
        pin_num = parts[3] if len(parts) > 3 else None

        # Extract labels from both positions (using pre-compiled patterns)
        start_match = _START_LABEL_PATTERN.search(element)
        end_match = _END_LABEL_PATTERN.search(element)
        start_label = start_match.group(1) if start_match else None
        end_label = end_match.group(1) if end_match else None

        # Name is whichever label is NOT just a number
        if start_label and not start_label.isdigit():
            pin_name = start_label
        elif end_label and not end_label.isdigit():
            pin_name = end_label
        else:
            pin_name = pin_num  # Passive: use pin number as name

        # Get first color for type detection (using pre-compiled pattern)
        colors = _COLOR_PATTERN.findall(element)
        first_color = colors[0].upper() if colors else None

        pin_type = _detect_pin_type(first_color, pin_name)
        base_name, functions = split_pin_functions(pin_name)

        pins.append({
            "number": pin_num,
            "name": base_name,
            "functions": functions,
            "type": pin_type
        })

    # Sort by pin number
    pins.sort(key=lambda p: _sort_key(p["number"]))
    return pins


def _detect_pin_type(color: str | None, name: str | None) -> str:
    """Detect pin type from color and name.

    Priority: color (if red/black) -> name keywords -> passive check -> io
    """
    name_upper = (name or "").upper()

    # Color-based detection (reliable for red/black)
    if color == "#FF0000":
        return "power"
    if color == "#000000":
        return "ground"

    # Name-based fallback (for pins like VBAT, 3V3 that use generic colors)
    # Check ground before power to properly detect VSS (not VS)
    if any(kw in name_upper for kw in GROUND_KEYWORDS):
        return "ground"
    if any(kw in name_upper for kw in POWER_KEYWORDS):
        return "power"

    # Passive components have numbered-only pins
    if name and name.isdigit():
        return "passive"

    return "io"


def split_pin_functions(raw_name: str | None) -> tuple[str, list[str]]:
    """Split MCU pin names into base name + alternate functions.

    Examples:
    - 'PA0_WKUPUSART2_CTSADC12_IN0' -> ('PA0', ['WKUP', 'USART2_CTS', 'ADC12_IN0'])
    - 'PC13-TAMPER-RTC' -> ('PC13', ['TAMPER', 'RTC'])
    - 'PA11USART1_CTSCAN_RXTIM1_CH4USBDM' -> ('PA11', ['USART1_CTS', 'CAN_RX', 'TIM1_CH4', 'USBDM'])
    """
    if not raw_name:
        return (raw_name or "", [])

    # Case 1: Dash-delimited (reliable splitting)
    if "-" in raw_name:
        parts = raw_name.split("-")
        return (parts[0], parts[1:])

    # Case 2: Underscore after GPIO base name (e.g., PA0_WKUP...)
    gpio_match = _GPIO_UNDERSCORE_PATTERN.match(raw_name)
    if gpio_match:
        base = gpio_match.group(1)
        remainder = gpio_match.group(2)
        functions = _split_concatenated_functions(remainder)
        return (base, functions)

    # Case 3: No underscore, but GPIO base name followed by peripherals
    gpio_match = _GPIO_NOUNDERSCORE_PATTERN.match(raw_name)
    if gpio_match:
        base = gpio_match.group(1)
        remainder = gpio_match.group(2)
        functions = _split_concatenated_functions(remainder)
        return (base, functions)

    return (raw_name, [])


def _split_concatenated_functions(remainder: str) -> list[str]:
    """Split concatenated peripheral functions like 'WKUPUSART2_CTSADC12_IN0'.

    Uses peripheral prefixes to identify boundaries between functions.
    """
    if not remainder:
        return []

    functions = []
    last_end = 0

    for match in _PERIPHERAL_PATTERN.finditer(remainder):
        start = match.start()

        # Text before this match belongs to the previous function
        if functions and start > last_end:
            functions[-1] += remainder[last_end:start]
        elif start > last_end:
            # Text before first match is a standalone function
            functions.append(remainder[last_end:start])

        # Start new function with this prefix
        functions.append(match.group(1))
        last_end = match.end()

    # Add remaining text to last function
    if functions and last_end < len(remainder):
        functions[-1] += remainder[last_end:]
    elif not functions and remainder:
        functions = [remainder]

    return functions


def _sort_key(num: str | None) -> tuple:
    """Sort pin numbers numerically when possible."""
    try:
        return (0, int(num))  # type: ignore
    except (ValueError, TypeError):
        return (1, num or "")


def generate_pinout_summary(pins: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Generate interface summary from parsed pins.

    Scans all pin functions for known interface patterns and groups them.
    Only included for components with alternate functions (MCUs, complex ICs).

    Args:
        pins: List of parsed pin dicts

    Returns:
        Summary dict with power, ground, and interfaces, or None for simple components.
    """
    # Collect power/ground pins
    power_pins = [p["name"] for p in pins if p["type"] == "power"]
    ground_pins = [p["name"] for p in pins if p["type"] == "ground"]

    # Scan all functions for interface patterns (using pre-compiled patterns)
    interfaces: dict[str, dict[str, Any]] = {}
    for pin in pins:
        for func in pin.get("functions", []):
            for iface_name, pattern in INTERFACE_PATTERNS.items():
                match = pattern.search(func)
                if match:
                    if iface_name not in interfaces:
                        interfaces[iface_name] = {"instances": set()}
                    # Extract instance number if present
                    if match.groups() and match.group(1):
                        instance = f"{iface_name.upper()}{match.group(1)}"
                        interfaces[iface_name]["instances"].add(instance)
                    else:
                        interfaces[iface_name]["instances"].add(iface_name.upper())

    # Convert sets to sorted lists and add counts
    processed_interfaces: dict[str, Any] = {}
    for iface_name, data in interfaces.items():
        instances = sorted(data["instances"])
        # Simplify boolean interfaces (USB, ETH)
        if iface_name in ('usb', 'eth', 'sdio') and len(instances) == 1:
            processed_interfaces[iface_name] = True
        else:
            processed_interfaces[iface_name] = {
                "count": len(instances),
                "instances": instances
            }

    # Only return summary if there are interfaces (skip for passives/simple components)
    if not processed_interfaces and not power_pins:
        return None

    summary: dict[str, Any] = {
        "power": power_pins,
        "ground": ground_pins,
    }
    if processed_interfaces:
        summary["interfaces"] = processed_interfaces

    return summary
