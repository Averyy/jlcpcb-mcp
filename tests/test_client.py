"""Tests for JLCPCB API client."""

import pytest
from jlcpcb_mcp.client import JLCPCBClient


class TestClient:
    """Test JLCPCB API client."""

    @pytest.fixture
    def client(self):
        client = JLCPCBClient()
        # Pre-populate category cache for unit tests
        client.set_categories([
            {
                "id": 1,
                "name": "Resistors",
                "count": 1000000,
                "subcategories": [
                    {"id": 2980, "name": "Chip Resistor - Surface Mount", "count": 500000},
                ],
            },
            {
                "id": 5,
                "name": "Transistors/Thyristors",
                "count": 110000,
                "subcategories": [],
            },
            {
                "id": 11,
                "name": "Circuit Protection",
                "count": 159000,
                "subcategories": [],
            },
            {
                "id": 16,
                "name": "Optoelectronics",
                "count": 83000,
                "subcategories": [],
            },
            {
                "id": 29,
                "name": "Data Acquisition",
                "count": 25000,
                "subcategories": [],
            },
        ])
        return client

    def test_build_search_params_keyword(self, client):
        params = client._build_search_params(query="ESP32")
        assert params["keyword"] == "ESP32"
        assert params["currentPage"] == 1
        assert params["pageSize"] == 20

    def test_build_search_params_category(self, client):
        params = client._build_search_params(category_id=1)
        assert params["firstSortId"] == 1
        assert params["firstSortName"] == "Resistors"
        assert params["searchType"] == 3

    def test_build_search_params_subcategory(self, client):
        params = client._build_search_params(subcategory_id=2980)
        assert params["firstSortId"] == 1
        assert params["firstSortName"] == "Resistors"
        assert params["secondSortId"] == 2980
        assert params["secondSortName"] == "Chip Resistor - Surface Mount"
        assert params["searchType"] == 3

    def test_build_search_params_stock(self, client):
        params = client._build_search_params(min_stock=1000)
        assert params["startStockNumber"] == 1000

    def test_build_search_params_library_type_basic(self, client):
        params = client._build_search_params(library_type="basic")
        assert params["componentLibraryType"] == "base"

    def test_build_search_params_library_type_extended(self, client):
        params = client._build_search_params(library_type="extended")
        assert params["componentLibraryType"] == "expand"

    def test_build_search_params_library_type_preferred(self, client):
        params = client._build_search_params(library_type="preferred")
        assert params["preferredComponentFlag"] is True

    def test_build_search_params_library_type_no_fee(self, client):
        """no_fee combines basic + preferred in a single API call."""
        params = client._build_search_params(library_type="no_fee")
        assert params["componentLibraryType"] == "base"
        assert params["preferredComponentFlag"] is True

    def test_build_search_params_sort_by_quantity(self, client):
        """Sort by quantity (highest first)."""
        params = client._build_search_params(sort_by="quantity")
        assert params["sortMode"] == "STOCK_SORT"
        assert params["sortASC"] == "DESC"

    def test_build_search_params_sort_by_price(self, client):
        """Sort by price (cheapest first)."""
        params = client._build_search_params(sort_by="price")
        assert params["sortMode"] == "PRICE_SORT"
        assert params["sortASC"] == "ASC"

    def test_build_search_params_sort_default(self, client):
        """No sorting params when sort_by is None (default relevance)."""
        params = client._build_search_params(query="ESP32")
        assert "sortMode" not in params
        assert "sortASC" not in params

    def test_build_search_params_sort_invalid(self, client):
        """Invalid sort_by value is ignored."""
        params = client._build_search_params(sort_by="invalid")
        assert "sortMode" not in params
        assert "sortASC" not in params

    def test_build_search_params_packages_multi(self, client):
        """Multiple packages use componentSpecificationList (OR filter)."""
        params = client._build_search_params(packages=["0402", "0603", "0805"])
        assert params["componentSpecificationList"] == ["0402", "0603", "0805"]
        assert "componentSpecification" not in params

    def test_build_search_params_packages_empty(self, client):
        """Empty packages list is ignored."""
        params = client._build_search_params(packages=[])
        assert "componentSpecificationList" not in params
        assert "componentSpecification" not in params

    def test_build_search_params_package_single_over_multi(self, client):
        """Multi-select packages takes precedence over single package."""
        params = client._build_search_params(package="0402", packages=["0603", "0805"])
        assert params["componentSpecificationList"] == ["0603", "0805"]
        assert "componentSpecification" not in params

    def test_build_search_params_manufacturers_multi(self, client):
        """Multiple manufacturers use componentBrandList (OR filter)."""
        params = client._build_search_params(manufacturers=["TI", "STMicroelectronics"])
        assert params["componentBrandList"] == ["TI", "STMicroelectronics"]
        assert "componentBrand" not in params

    def test_build_search_params_manufacturers_empty(self, client):
        """Empty manufacturers list is ignored."""
        params = client._build_search_params(manufacturers=[])
        assert "componentBrandList" not in params
        assert "componentBrand" not in params

    def test_build_search_params_manufacturer_single_over_multi(self, client):
        """Multi-select manufacturers takes precedence over single manufacturer."""
        params = client._build_search_params(manufacturer="TI", manufacturers=["STM", "NXP"])
        assert params["componentBrandList"] == ["STM", "NXP"]
        assert "componentBrand" not in params

    def test_transform_part_slim(self, client):
        # Note: API returns firstSortName as subcategory, secondSortName as category
        item = {
            "componentCode": "C82899",
            "componentModelEn": "ESP32-WROOM-32-N4",
            "componentBrandEn": "Espressif Systems",
            "componentSpecificationEn": "SMD,25.5x18mm",
            "stockCount": 11117,
            "componentLibraryType": "expand",
            "preferredComponentFlag": False,
            "firstSortName": "IoT Modules",  # subcategory
            "secondSortName": "WiFi Modules",  # category
            "componentPrices": [{"startNumber": 1, "endNumber": 9, "productPrice": 4.2016}],
        }
        result = client._transform_part(item, slim=True)
        assert result["lcsc"] == "C82899"
        assert result["model"] == "ESP32-WROOM-32-N4"
        assert result["manufacturer"] == "Espressif Systems"
        assert result["stock"] == 11117
        assert result["library_type"] == "extended"
        assert result["price"] == 4.2016
        assert result["category"] == "WiFi Modules"
        assert "datasheet" not in result

    def test_transform_part_full(self, client):
        # Note: API returns firstSortName as subcategory, secondSortName as category
        item = {
            "componentCode": "C82899",
            "componentModelEn": "ESP32-WROOM-32-N4",
            "componentBrandEn": "Espressif Systems",
            "componentSpecificationEn": "SMD,25.5x18mm",
            "stockCount": 11117,
            "componentLibraryType": "base",
            "preferredComponentFlag": True,
            "firstSortName": "IoT Modules",  # subcategory
            "secondSortName": "WiFi Modules",  # category
            "describe": "WiFi module description",
            "minPurchaseNum": 1,
            "encapsulationNumber": 550,
            "dataManualUrl": "https://example.com/datasheet.pdf",
            "lcscGoodsUrl": "https://lcsc.com/product/C82899",
            "componentPrices": [
                {"startNumber": 1, "endNumber": 9, "productPrice": 4.2016},
                {"startNumber": 10, "endNumber": 29, "productPrice": 3.7052},
            ],
            "attributes": [
                {"attribute_name_en": "Voltage", "attribute_value_name": "3.3V"},
            ],
        }
        result = client._transform_part(item, slim=False)
        assert result["lcsc"] == "C82899"
        assert result["library_type"] == "basic"
        assert result["category"] == "WiFi Modules"
        assert result["subcategory"] == "IoT Modules"
        assert result["datasheet"] == "https://example.com/datasheet.pdf"
        assert len(result["prices"]) == 2
        assert result["prices"][0]["qty"] == "1+"
        assert len(result["attributes"]) == 1
        assert result["attributes"][0]["name"] == "Voltage"

    # Tests for abbreviation matching

    def test_match_category_abbreviation_led(self, client):
        """LED abbreviation should match Optoelectronics category."""
        assert client._match_category_by_name("led") == 16
        assert client._match_category_by_name("LED") == 16
        assert client._match_category_by_name("Led") == 16

    def test_match_category_abbreviation_led_plural(self, client):
        """LEDs (plural) should also match Optoelectronics."""
        assert client._match_category_by_name("leds") == 16
        assert client._match_category_by_name("LEDs") == 16

    def test_match_category_abbreviation_esd(self, client):
        """ESD abbreviation should match Circuit Protection category."""
        assert client._match_category_by_name("esd") == 11
        assert client._match_category_by_name("ESD") == 11

    def test_match_category_abbreviation_adc(self, client):
        """ADC abbreviation should match Data Acquisition category."""
        assert client._match_category_by_name("adc") == 29
        assert client._match_category_by_name("ADC") == 29
        assert client._match_category_by_name("adcs") == 29

    def test_match_category_abbreviation_transistors(self, client):
        """BJT and FET abbreviations should match Transistors category."""
        assert client._match_category_by_name("bjt") == 5
        assert client._match_category_by_name("BJT") == 5
        assert client._match_category_by_name("bjts") == 5
        assert client._match_category_by_name("fet") == 5
        assert client._match_category_by_name("FET") == 5
        assert client._match_category_by_name("fets") == 5

    def test_match_category_by_name_exact(self, client):
        """Exact category name match."""
        assert client._match_category_by_name("resistors") == 1
        assert client._match_category_by_name("Resistors") == 1

    def test_match_category_by_name_singular(self, client):
        """Singular form should match plural category."""
        assert client._match_category_by_name("resistor") == 1

    def test_match_category_by_name_no_match(self, client):
        """Non-matching query should return None."""
        assert client._match_category_by_name("xyz123") is None
        assert client._match_category_by_name("") is None
        assert client._match_category_by_name(None) is None

    def test_resolve_abbreviation_requires_categories(self, client):
        """Abbreviation resolution requires categories to be loaded."""
        empty_client = JLCPCBClient()
        # No categories set, should return None
        assert empty_client._match_category_by_name("led") is None


@pytest.mark.asyncio
class TestClientIntegration:
    """Integration tests that hit the real JLCPCB API."""

    @pytest.fixture
    async def client(self):
        client = JLCPCBClient()
        yield client
        await client.close()

    async def test_search_keyword(self, client):
        """Test keyword search."""
        result = await client.search(query="ESP32", limit=5)
        assert "results" in result
        assert len(result["results"]) > 0
        assert result["results"][0]["lcsc"].startswith("C")

    async def test_search_category(self, client):
        """Test category filtering."""
        result = await client.search(category_id=1, min_stock=0, limit=5)
        assert result["total"] > 100000  # Resistors should have >100K parts (when min_stock=0)
        assert all(r["category"] == "Resistors" for r in result["results"])

    async def test_search_stock_filter(self, client):
        """Test stock filtering."""
        result = await client.search(category_id=1, min_stock=10000, limit=5)
        assert all(r["stock"] >= 10000 for r in result["results"])

    async def test_search_library_type_no_fee(self, client):
        """Test no_fee library type returns only basic/preferred parts."""
        result = await client.search(query="resistor", library_type="no_fee", limit=10)
        assert len(result["results"]) > 0
        # no_fee should only return basic or preferred parts (no extended)
        for part in result["results"]:
            assert part["library_type"] in ("basic", "preferred") or part["preferred"] is True, (
                f"Part {part['lcsc']} has library_type={part['library_type']}, preferred={part['preferred']}"
            )

    async def test_get_part(self, client):
        """Test getting part details."""
        result = await client.get_part("C82899")
        assert result is not None
        assert result["lcsc"] == "C82899"
        assert "prices" in result
        assert "datasheet" in result

    async def test_fetch_categories(self, client):
        """Test fetching live category data from API."""
        categories = await client.fetch_categories()

        # Minimum thresholds (90% of expected ~51 categories, ~756 subcategories)
        assert len(categories) >= 46, (
            f"Expected at least 46 categories, got {len(categories)}. "
            "JLCPCB API may have changed or is returning incomplete data."
        )

        # Check structure of a category
        cat = categories[0]
        assert "id" in cat
        assert "name" in cat
        assert "count" in cat
        assert "subcategories" in cat

        # Should have subcategories - minimum threshold (90% of expected)
        total_subs = sum(len(c["subcategories"]) for c in categories)
        assert total_subs >= 680, (
            f"Expected at least 680 subcategories, got {total_subs}. "
            "JLCPCB API may have changed or is returning incomplete data."
        )

    async def test_search_sort_by_quantity(self, client):
        """Test sorting by quantity (highest first)."""
        result = await client.search(query="ESP32", sort_by="quantity", limit=10)
        stocks = [r["stock"] for r in result["results"] if r["stock"] is not None]
        # Check descending order (each value >= next)
        for i in range(len(stocks) - 1):
            assert stocks[i] >= stocks[i + 1], "Results should be sorted by quantity descending"

    async def test_search_sort_by_price(self, client):
        """Test sorting by price (cheapest first)."""
        result = await client.search(query="ESP32", sort_by="price", limit=10)
        prices = [r["price"] for r in result["results"] if r["price"] is not None]
        # Check ascending order (each value <= next)
        for i in range(len(prices) - 1):
            assert prices[i] <= prices[i + 1], "Results should be sorted by price ascending"

    async def test_search_packages_multi(self, client):
        """Test multi-select package filter (OR logic)."""
        # Search capacitors with multiple package sizes
        result = await client.search(
            category_id=2,  # Capacitors
            packages=["0402", "0603", "0805"],
            limit=20,
        )
        # Collect packages from results
        result_packages = {r["package"] for r in result["results"]}
        # Should include at least some of the requested packages
        assert result_packages & {"0402", "0603", "0805"}, (
            f"Expected some of ['0402', '0603', '0805'], got {result_packages}"
        )

    async def test_search_manufacturers_multi(self, client):
        """Test multi-select manufacturer filter (OR logic)."""
        result = await client.search(
            query="microcontroller",
            manufacturers=["STMicroelectronics", "Microchip Tech"],
            limit=20,
        )
        # Collect manufacturers from results
        result_mfrs = {r["manufacturer"] for r in result["results"]}
        # Should include at least one of the requested manufacturers
        assert result_mfrs & {"STMicroelectronics", "Microchip Tech"}, (
            f"Expected some of ['STMicroelectronics', 'Microchip Tech'], got {result_mfrs}"
        )

    async def test_search_combined_filters(self, client):
        """Test combining keyword, category, multi-package, and stock filters."""
        result = await client.search(
            query="100nF",  # Attribute value as keyword
            category_id=2,  # Capacitors
            packages=["0402", "0603"],
            min_stock=1000,
            limit=10,
        )
        assert len(result["results"]) > 0, "Should find 100nF capacitors"
        # Verify all results meet stock requirement
        for part in result["results"]:
            assert part["stock"] >= 1000, f"Part {part['lcsc']} has stock {part['stock']} < 1000"

    async def test_search_sorted_with_multi_filters(self, client):
        """Test sorting combined with multi-select filters."""
        result = await client.search(
            category_id=2,  # Capacitors
            packages=["0402", "0603"],
            sort_by="price",
            min_stock=100,
            limit=10,
        )
        assert len(result["results"]) > 0, "Should find capacitors"
        # Verify price sorting (ascending)
        prices = [r["price"] for r in result["results"] if r["price"] is not None]
        for i in range(len(prices) - 1):
            assert prices[i] <= prices[i + 1], "Results should be sorted by price ascending"
