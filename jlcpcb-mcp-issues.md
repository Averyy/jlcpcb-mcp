# JLCPCB MCP Server - Issues & Improvement Tracking

**Original Version Tested**: 1.10.1
**Current Version**: 1.10.2
**Last Updated**: 2026-01-26

---

## Status Summary

| Issue | Status | Version |
|-------|--------|---------|
| BUG-004: get_pinout crashes on invalid part | FIXED | v1.10.2 |
| GAP-001: Battery Management rules | FIXED | v1.10.2 |
| GAP-004: DC-DC topology verification | Already existed | v1.10.1 |
| GAP-005: Level Shifters rules | FIXED | v1.10.2 |
| FIX 4: WiFi/BT/LoRa Module rules | FIXED | v1.10.2 |
| OBS-004: CASE-A/B mounting detection | FIXED | v1.10.2 |
| Parametric/attribute filtering | NOT SUPPORTED BY API | - |

---

## Regression Test Queries

Use these queries to validate behavior in future versions:

### Should Work
```python
# Structured searches
search_parts(subcategory_id=71, package="0603")  # LEDs
search_parts(subcategory_name="Chip Resistor - Surface Mount", package="0402")
search_parts(query="ESP32", limit=5)
search_parts(query="STM32F103C8T6")  # Exact model

# find_alternatives - supported categories
find_alternatives(lcsc="C6186")   # LDO - AMS1117-3.3
find_alternatives(lcsc="C8678")   # Schottky - SS34
find_alternatives(lcsc="C318884") # Tactile switch
find_alternatives(lcsc="C20917")  # MOSFET - AO3400A
find_alternatives(lcsc="C84817")  # DC-DC - MT3608 (topology verified)
find_alternatives(lcsc="C16581")  # Battery Mgmt - TP4056 (v1.10.2)
find_alternatives(lcsc="C17206")  # Level Shifter - TXS0108EPWR (v1.10.2)
find_alternatives(lcsc="C82899")  # WiFi - ESP32-WROOM (v1.10.2)

# BOM
validate_bom(parts=[{"lcsc": "C1525", "designators": ["C1"]}])
```

### Known API Limitations (0 results expected)
```python
# BUG-001: keyword + subcategory = 0 results (JLCPCB API limitation)
search_parts(query="green 0603", subcategory_id=71)
search_parts(query="green", subcategory_id=71, package="0603")

# BUG-002: keyword + library_type = 0 results
search_parts(query="LED 0603", library_type="basic")

# BUG-003: Wrong category returned
search_parts(query="green LED 0603", limit=5)  # Returns switch caps, not LEDs

# SEARCH-008: Notation not normalized
search_parts(query="10K 0402", subcategory_name="Chip Resistor - Surface Mount")  # Misses 10kΩ
```

---

## JLCPCB API Behavior (Investigation Results)

### keyword + subcategory WORKS (for model name searches)

**Key Finding:** The API DOES support `keyword` + `searchType=3` (subcategory filter), but it only searches **model names**, NOT **attribute values**.

**Tested 2026-01-26:**
```
Query "530nm" + LED subcategory (71): 217 results ✓ (wavelength in model name)
Query "0603" + LED subcategory (71): 771 results ✓ (package in model name)
Query "KT-0603" + LED subcategory (71): 9 results ✓ (model prefix)
Query "green" + LED subcategory (71): 0 results ✗ (color is attribute, not in model)
```

**Why "green" fails:** The LED color "Green" is stored in the `Illumination Color` attribute, which is NOT indexed for keyword search. However, wavelength values like "530nm" DO appear in model names, so they work.

**What API page size supports:**
- Max page size enforced: 100 (requesting higher returns 100)
- Subcategory sizes vary widely: LEDs ~50k, Resistors ~460k, Tactile Switches ~24k

### Search Strategies That Work

1. **Wavelength for LED colors:**
   - Green: search "525nm" or "530nm"
   - Red: search "620nm" or "630nm"
   - Blue: search "460nm" or "470nm"

2. **Package + subcategory:** Works perfectly
   ```python
   search_parts(subcategory_id=71, package="0603")  # 771 LEDs
   ```

3. **Model prefix + subcategory:** Works if you know the manufacturer's naming
   ```python
   search_parts(query="KT-0603", subcategory_id=71)  # 9 results
   ```

### What DOES NOT Work

1. **Attribute value searches:** "green", "100nF", "10K" often fail because these are attribute values, not in model names
2. **Color names:** "green LED", "red LED" - color is an attribute
3. **Some searchSource/searchType combos:** Only `searchSource="search"` + `searchType=3` works for subcategory filtering

---

## Remaining Work

### Investigated - Not Feasible
- **Parametric/attribute filtering:** API does not support filtering by attribute values (LED color, etc.). Tested `componentAttrList`, `attributeFilters`, and other formats - all return 0 results or are ignored.

### Low Priority
- [ ] OBS-005: Validate category_id against known categories
- [ ] GAP-002: Cross-family alternatives (ESP32 variants)
- [ ] GAP-006: MCU alternative support (complex)

---

## Components Tested

| LCSC | Part | find_alternatives |
|------|------|-------------------|
| C82899 | ESP32-WROOM-32-N4 | WORKS (v1.10.2) |
| C16581 | TP4056-42-ESOP8 | WORKS (v1.10.2) |
| C17206 | TXS0108EPWR | WORKS (v1.10.2) |
| C84817 | MT3608 Boost | WORKS (topology verified) |
| C6186 | AMS1117-3.3 | WORKS |
| C8678 | SS34 Schottky | WORKS |
| C318884 | Tactile Switch | WORKS |
| C20917 | AO3400A MOSFET | WORKS |
| C8734 | STM32F103C8T6 | similar_parts (expected) |

---

## What Works Well

- `search_parts` with structured filters (package, manufacturer, subcategory_name)
- `get_part` with full details and EasyEDA footprint info
- `validate_bom` / `export_bom` with cost calculation
- `find_alternatives` for 125+ supported categories
- `get_pinout` for valid parts
- Manufacturer alias resolution (TI → Texas Instruments)
- Multi-value filters (`packages[]`, `manufacturers[]`)
