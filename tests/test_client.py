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
