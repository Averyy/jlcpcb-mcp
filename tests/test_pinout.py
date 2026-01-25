"""Tests for EasyEDA pinout parser."""

import pytest
from jlcpcb_mcp.pinout import (
    parse_easyeda_pins,
    _detect_pin_type,
    split_pin_functions,
    generate_pinout_summary,
)
from jlcpcb_mcp.client import JLCPCBClient


class TestPinTypeDetection:
    """Test pin type detection from name.

    Note: Color-based detection was removed because EasyEDA uses the same colors
    for different pin types (dark red for both power and I/O, black for both
    ground and passive). Detection is now purely name-based.
    """

    def test_detect_power_by_name(self):
        """Power keywords in name should be detected."""
        assert _detect_pin_type("VCC") == "power"
        assert _detect_pin_type("VDD") == "power"
        assert _detect_pin_type("VBAT") == "power"
        assert _detect_pin_type("3V3") == "power"
        assert _detect_pin_type("5V") == "power"
        assert _detect_pin_type("VBUS") == "power"
        assert _detect_pin_type("VIN") == "power"
        assert _detect_pin_type("VOUT") == "power"
        assert _detect_pin_type("AVCC") == "power"
        assert _detect_pin_type("DVCC") == "power"

    def test_detect_ground_by_name(self):
        """Ground keywords in name should be detected."""
        assert _detect_pin_type("GND") == "ground"
        assert _detect_pin_type("VSS") == "ground"
        assert _detect_pin_type("AGND") == "ground"
        assert _detect_pin_type("DGND") == "ground"
        assert _detect_pin_type("VEE") == "ground"
        assert _detect_pin_type("PGND") == "ground"

    def test_detect_passive(self):
        """Numbered-only pins should be detected as passive."""
        assert _detect_pin_type("1") == "passive"
        assert _detect_pin_type("2") == "passive"
        assert _detect_pin_type("123") == "passive"

    def test_detect_io_default(self):
        """Non-matching pins should default to io."""
        assert _detect_pin_type("PA0") == "io"
        assert _detect_pin_type("G") == "io"
        assert _detect_pin_type("SDA") == "io"
        assert _detect_pin_type("SCL") == "io"
        assert _detect_pin_type("D") == "io"
        assert _detect_pin_type("S") == "io"

    def test_detect_none_or_empty(self):
        """None or empty name should default to io."""
        assert _detect_pin_type(None) == "io"
        assert _detect_pin_type("") == "io"


class TestPinFunctionSplitting:
    """Test splitting MCU pin names into base name and functions."""

    def test_simple_pin_no_functions(self):
        """Simple pins should return empty functions list."""
        base, functions = split_pin_functions("G")
        assert base == "G"
        assert functions == []

        base, functions = split_pin_functions("VCC")
        assert base == "VCC"
        assert functions == []

    def test_dash_delimited(self):
        """Dash-delimited pins should split correctly."""
        base, functions = split_pin_functions("PC13-TAMPER-RTC")
        assert base == "PC13"
        assert functions == ["TAMPER", "RTC"]

    def test_underscore_after_gpio(self):
        """Underscore after GPIO base should trigger function parsing."""
        base, functions = split_pin_functions("PA0_WKUP")
        assert base == "PA0"
        assert "WKUP" in functions

    def test_concatenated_peripherals(self):
        """Concatenated peripheral names should be split."""
        base, functions = split_pin_functions("PA0_WKUPUSART2_CTS")
        assert base == "PA0"
        assert "WKUP" in functions
        assert "USART2_CTS" in functions

    def test_gpio_no_underscore(self):
        """GPIO followed directly by peripheral should split."""
        base, functions = split_pin_functions("PA11USART1_CTS")
        assert base == "PA11"
        assert "USART1_CTS" in functions

    def test_empty_input(self):
        """Empty input should return empty results."""
        base, functions = split_pin_functions("")
        assert base == ""
        assert functions == []

        base, functions = split_pin_functions(None)
        assert base == ""
        assert functions == []

    def test_numeric_only(self):
        """Numeric-only pins should return as-is."""
        base, functions = split_pin_functions("1")
        assert base == "1"
        assert functions == []


class TestParsePins:
    """Test parsing pins from EasyEDA data."""

    def test_parse_simple_mosfet_pins(self):
        """Test parsing simple 3-pin MOSFET."""
        # Simulated EasyEDA data structure for a MOSFET
        data = {
            "dataStr": {
                "shape": [
                    "P~show~0~1~100~100~180~gge1~0^^100~100^^M100,100h10~#880000^^1~110~105~0~G~start~~~#0000FF^^1~100~100~0~1~end~~~#0000FF",
                    "P~show~0~2~100~120~180~gge2~0^^100~120^^M100,120h10~#880000^^1~110~125~0~S~start~~~#0000FF^^1~100~120~0~2~end~~~#0000FF",
                    "P~show~0~3~100~140~180~gge3~0^^100~140^^M100,140h10~#880000^^1~110~145~0~D~start~~~#0000FF^^1~100~140~0~3~end~~~#0000FF",
                ]
            }
        }
        pins = parse_easyeda_pins(data)
        assert len(pins) == 3
        assert pins[0]["number"] == "1"
        assert pins[0]["name"] == "G"
        assert pins[0]["type"] == "io"
        assert pins[1]["number"] == "2"
        assert pins[1]["name"] == "S"
        assert pins[2]["number"] == "3"
        assert pins[2]["name"] == "D"

    def test_parse_capacitor_passive_pins(self):
        """Test parsing 2-pin passive component."""
        data = {
            "dataStr": {
                "shape": [
                    "P~show~0~1~100~100~180~gge1~0^^100~100^^M100,100h10~#0000FF^^1~110~105~0~1~start~~~#0000FF^^1~100~100~0~1~end~~~#0000FF",
                    "P~show~0~2~100~120~180~gge2~0^^100~120^^M100,120h10~#0000FF^^1~110~125~0~2~start~~~#0000FF^^1~100~120~0~2~end~~~#0000FF",
                ]
            }
        }
        pins = parse_easyeda_pins(data)
        assert len(pins) == 2
        assert pins[0]["number"] == "1"
        assert pins[0]["name"] == "1"
        assert pins[0]["type"] == "passive"
        assert pins[1]["number"] == "2"
        assert pins[1]["name"] == "2"
        assert pins[1]["type"] == "passive"

    def test_parse_power_ground_pins_by_name(self):
        """Test parsing power/ground pins by name keywords."""
        data = {
            "dataStr": {
                "shape": [
                    "P~show~0~1~100~100~180~gge1~0^^100~100^^M100,100h10~#FF0000^^1~110~105~0~VDD~start~~~#FF0000^^1~100~100~0~1~end~~~#0000FF",
                    "P~show~0~2~100~120~180~gge2~0^^100~120^^M100,120h10~#000000^^1~110~125~0~VSS~start~~~#000000^^1~100~120~0~2~end~~~#0000FF",
                ]
            }
        }
        pins = parse_easyeda_pins(data)
        assert len(pins) == 2
        assert pins[0]["name"] == "VDD"
        assert pins[0]["type"] == "power"  # Detected by name keyword, not color
        assert pins[1]["name"] == "VSS"
        assert pins[1]["type"] == "ground"  # Detected by name keyword, not color

    def test_parse_empty_shape(self):
        """Test parsing with empty shape array."""
        data = {"dataStr": {"shape": []}}
        pins = parse_easyeda_pins(data)
        assert pins == []

    def test_parse_missing_datastr(self):
        """Test parsing with missing dataStr."""
        data = {}
        pins = parse_easyeda_pins(data)
        assert pins == []

    def test_parse_pins_sorted_by_number(self):
        """Test that pins are sorted by pin number."""
        data = {
            "dataStr": {
                "shape": [
                    "P~show~0~3~100~100~180~gge1~0^^100~100^^M100,100h10~#0000FF^^1~110~105~0~C~start~~~#0000FF^^1~100~100~0~3~end~~~#0000FF",
                    "P~show~0~1~100~100~180~gge2~0^^100~100^^M100,100h10~#0000FF^^1~110~105~0~A~start~~~#0000FF^^1~100~100~0~1~end~~~#0000FF",
                    "P~show~0~2~100~100~180~gge3~0^^100~100^^M100,100h10~#0000FF^^1~110~105~0~B~start~~~#0000FF^^1~100~100~0~2~end~~~#0000FF",
                ]
            }
        }
        pins = parse_easyeda_pins(data)
        assert [p["number"] for p in pins] == ["1", "2", "3"]
        assert [p["name"] for p in pins] == ["A", "B", "C"]


class TestGenerateSummary:
    """Test interface summary generation."""

    def test_no_summary_for_passives(self):
        """Passive components should not have a summary."""
        pins = [
            {"number": "1", "name": "1", "functions": [], "type": "passive"},
            {"number": "2", "name": "2", "functions": [], "type": "passive"},
        ]
        summary = generate_pinout_summary(pins)
        assert summary is None

    def test_no_summary_for_simple_ic(self):
        """Simple ICs without interfaces or power pins should not have a summary."""
        pins = [
            {"number": "1", "name": "G", "functions": [], "type": "io"},
            {"number": "2", "name": "S", "functions": [], "type": "io"},
            {"number": "3", "name": "D", "functions": [], "type": "io"},
        ]
        summary = generate_pinout_summary(pins)
        assert summary is None

    def test_summary_with_power_ground(self):
        """Components with power/ground should have those in summary."""
        pins = [
            {"number": "1", "name": "VCC", "functions": [], "type": "power"},
            {"number": "2", "name": "GND", "functions": [], "type": "ground"},
            {"number": "3", "name": "OUT", "functions": [], "type": "io"},
        ]
        summary = generate_pinout_summary(pins)
        assert summary is not None
        assert "VCC" in summary["power"]
        assert "GND" in summary["ground"]

    def test_summary_with_spi_interface(self):
        """MCU with SPI should show SPI interface in summary."""
        pins = [
            {"number": "1", "name": "VCC", "functions": [], "type": "power"},
            {"number": "2", "name": "PA5", "functions": ["SPI1_SCK"], "type": "io"},
            {"number": "3", "name": "PA6", "functions": ["SPI1_MISO"], "type": "io"},
            {"number": "4", "name": "PA7", "functions": ["SPI1_MOSI"], "type": "io"},
        ]
        summary = generate_pinout_summary(pins)
        assert summary is not None
        assert "interfaces" in summary
        assert "spi" in summary["interfaces"]
        assert summary["interfaces"]["spi"]["count"] == 1
        assert "SPI1" in summary["interfaces"]["spi"]["instances"]

    def test_summary_with_multiple_interfaces(self):
        """MCU with multiple interface types."""
        pins = [
            {"number": "1", "name": "VCC", "functions": [], "type": "power"},
            {"number": "2", "name": "PA0", "functions": ["USART1_TX"], "type": "io"},
            {"number": "3", "name": "PA1", "functions": ["USART1_RX"], "type": "io"},
            {"number": "4", "name": "PA2", "functions": ["I2C1_SDA"], "type": "io"},
            {"number": "5", "name": "PA3", "functions": ["I2C1_SCL"], "type": "io"},
        ]
        summary = generate_pinout_summary(pins)
        assert summary is not None
        assert "usart" in summary["interfaces"]
        assert "i2c" in summary["interfaces"]

    def test_summary_usb_as_boolean(self):
        """USB should be simplified to boolean True."""
        pins = [
            {"number": "1", "name": "VCC", "functions": [], "type": "power"},
            {"number": "2", "name": "PA11", "functions": ["USB_DM"], "type": "io"},
            {"number": "3", "name": "PA12", "functions": ["USB_DP"], "type": "io"},
        ]
        summary = generate_pinout_summary(pins)
        assert summary is not None
        assert summary["interfaces"]["usb"] is True


@pytest.mark.asyncio
class TestPinoutIntegration:
    """Integration tests that hit the real EasyEDA API."""

    @pytest.fixture
    async def client(self):
        client = JLCPCBClient()
        yield client
        await client.close()

    async def test_get_easyeda_component_stm32(self, client):
        """Test fetching STM32 component data from EasyEDA."""
        # First get the part to obtain the UUID
        part = await client.get_part("C8304")  # STM32F103CBT6
        assert part is not None
        assert part.get("has_easyeda_footprint") is True

        uuid = part.get("easyeda_symbol_uuid")
        assert uuid is not None

        # Fetch the component data
        data = await client.get_easyeda_component(uuid)
        assert "dataStr" in data

        # Parse the pins
        pins = parse_easyeda_pins(data)
        assert len(pins) > 0
        # STM32F103CBT6 has 48 pins
        assert len(pins) == 48

        # Check for expected pin types
        pin_types = {p["type"] for p in pins}
        assert "power" in pin_types
        assert "ground" in pin_types
        assert "io" in pin_types

        # Check summary generation
        summary = generate_pinout_summary(pins)
        assert summary is not None
        assert len(summary["power"]) > 0
        assert len(summary["ground"]) > 0
        assert "interfaces" in summary

    async def test_get_easyeda_component_mosfet(self, client):
        """Test fetching MOSFET component data from EasyEDA."""
        part = await client.get_part("C181090")  # AO3400
        assert part is not None
        assert part.get("has_easyeda_footprint") is True

        uuid = part.get("easyeda_symbol_uuid")
        data = await client.get_easyeda_component(uuid)
        pins = parse_easyeda_pins(data)

        assert len(pins) == 3
        pin_names = {p["name"] for p in pins}
        assert pin_names == {"G", "S", "D"}

        # MOSFET should not have a summary (no interfaces)
        summary = generate_pinout_summary(pins)
        assert summary is None

    async def test_get_easyeda_component_capacitor(self, client):
        """Test fetching capacitor component data from EasyEDA."""
        part = await client.get_part("C14663")  # 100nF capacitor
        assert part is not None
        assert part.get("has_easyeda_footprint") is True

        uuid = part.get("easyeda_symbol_uuid")
        data = await client.get_easyeda_component(uuid)
        pins = parse_easyeda_pins(data)

        assert len(pins) == 2
        # Capacitor pins should be passive (numbered)
        for pin in pins:
            assert pin["type"] == "passive"

        # Passive should not have a summary
        summary = generate_pinout_summary(pins)
        assert summary is None

    async def test_get_easyeda_component_lm358(self, client):
        """Test fetching LM358 op-amp (multi-unit) component data."""
        part = await client.get_part("C328566")  # LM358
        assert part is not None
        assert part.get("has_easyeda_footprint") is True

        uuid = part.get("easyeda_symbol_uuid")
        data = await client.get_easyeda_component(uuid)
        pins = parse_easyeda_pins(data)

        # LM358 has 8 pins
        assert len(pins) == 8

        # Should have power and ground pins
        pin_types = {p["type"] for p in pins}
        assert "power" in pin_types
        assert "ground" in pin_types

        # Should have VCC and VEE pins
        pin_names = {p["name"] for p in pins}
        assert "VCC" in pin_names or any("VCC" in name for name in pin_names)
        assert "VEE" in pin_names or any("VEE" in name for name in pin_names)

    async def test_get_easyeda_component_esp32_s3(self, client):
        """Test fetching ESP32-S3 module component data."""
        part = await client.get_part("C2913197")  # ESP32-S3-WROOM
        if not part:
            pytest.skip("Part C2913197 not available")
        if not part.get("has_easyeda_footprint"):
            pytest.skip("No EasyEDA footprint for C2913197")

        uuid = part.get("easyeda_symbol_uuid")
        data = await client.get_easyeda_component(uuid)
        pins = parse_easyeda_pins(data)

        assert len(pins) > 30  # ESP32-S3 has 40+ pins

        # Should detect power and ground
        pin_types = {p["type"] for p in pins}
        assert "power" in pin_types or "ground" in pin_types

    async def test_get_easyeda_component_tps63802(self, client):
        """Test fetching TPS63802 buck-boost regulator component data."""
        part = await client.get_part("C1849531")  # TPS63802
        if not part:
            pytest.skip("Part C1849531 not available")
        if not part.get("has_easyeda_footprint"):
            pytest.skip("No EasyEDA footprint for C1849531")

        uuid = part.get("easyeda_symbol_uuid")
        data = await client.get_easyeda_component(uuid)
        pins = parse_easyeda_pins(data)

        # TPS63802 has ~10 pins
        assert len(pins) >= 8

        # Should have power and ground pins (VIN, VOUT, GND)
        pin_names = {p["name"] for p in pins}
        has_power = any("VIN" in name or "VOUT" in name for name in pin_names)
        has_ground = any("GND" in name or "AGND" in name for name in pin_names)
        assert has_power, f"Expected power pin in {pin_names}"
        assert has_ground, f"Expected ground pin in {pin_names}"

    async def test_get_easyeda_component_invalid_uuid(self, client):
        """Test that invalid UUID format raises appropriate error."""
        with pytest.raises(ValueError, match="Invalid UUID format"):
            await client.get_easyeda_component("invalid-uuid-12345")

    async def test_get_easyeda_component_empty_uuid(self, client):
        """Test that empty UUID raises appropriate error."""
        with pytest.raises(ValueError, match="UUID is required"):
            await client.get_easyeda_component("")

    async def test_get_easyeda_component_nonexistent_uuid(self, client):
        """Test that valid format but non-existent UUID raises appropriate error."""
        # Valid format (32 hex chars) but doesn't exist
        with pytest.raises(ValueError, match="Failed to fetch"):
            await client.get_easyeda_component("00000000000000000000000000000000")
