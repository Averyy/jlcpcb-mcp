"""JLCPCB API client for searching electronic components."""

import asyncio
import random
from typing import Any

from curl_cffi import requests as curl_requests

from .config import (
    get_jlcpcb_headers,
    JLCPCB_SEARCH_URL,
    JLCPCB_DETAIL_URL,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    DEFAULT_MIN_STOCK,
)

# Browser fingerprints for TLS impersonation
BROWSER_FINGERPRINTS = ["chrome131", "chrome133a", "chrome136", "chrome142"]


class JLCPCBClient:
    """Async client for JLCPCB component search API with browser impersonation."""

    def __init__(self):
        self._sessions: list[curl_requests.AsyncSession] = []
        self._session_index = 0
        # Category cache - lazily populated from API or set externally
        self._categories: list[dict[str, Any]] = []
        self._category_map: dict[int, dict[str, Any]] = {}  # id -> category
        self._subcategory_map: dict[int, tuple[int, dict[str, Any]]] = {}  # id -> (parent_id, subcategory)

    def set_categories(self, categories: list[dict[str, Any]]) -> None:
        """Set pre-loaded categories to avoid redundant API calls.

        Call this after fetch_categories() to share the cache.
        """
        self._categories = categories
        self._category_map.clear()
        self._subcategory_map.clear()

        for cat in categories:
            self._category_map[cat["id"]] = cat
            for sub in cat.get("subcategories", []):
                self._subcategory_map[sub["id"]] = (cat["id"], sub)

    def _get_browser(self) -> str:
        """Get a random browser fingerprint."""
        return random.choice(BROWSER_FINGERPRINTS)

    async def _get_session(self) -> curl_requests.AsyncSession:
        """Get or create an HTTP session with browser impersonation.

        Uses a pool of sessions to avoid rate limiting and support concurrency.
        """
        # Create initial session if needed
        if not self._sessions:
            self._sessions.append(curl_requests.AsyncSession(
                impersonate=self._get_browser(),
                timeout=REQUEST_TIMEOUT,
            ))

        # Round-robin through sessions
        session = self._sessions[self._session_index % len(self._sessions)]
        self._session_index += 1

        return session

    async def _new_session(self) -> curl_requests.AsyncSession:
        """Create a new session with a fresh browser fingerprint."""
        session = curl_requests.AsyncSession(
            impersonate=self._get_browser(),
            timeout=REQUEST_TIMEOUT,
        )
        self._sessions.append(session)
        return session

    async def close(self):
        """Close all HTTP sessions."""
        for session in self._sessions:
            await session.close()
        self._sessions = []

    async def _ensure_categories(self) -> None:
        """Ensure categories are loaded (lazy initialization)."""
        if self._categories:
            return

        self._categories = await self.fetch_categories()

        # Build lookup maps
        for cat in self._categories:
            self._category_map[cat["id"]] = cat
            for sub in cat.get("subcategories", []):
                self._subcategory_map[sub["id"]] = (cat["id"], sub)

    def _get_category(self, category_id: int) -> dict[str, Any] | None:
        """Get category by ID from cache."""
        return self._category_map.get(category_id)

    def _get_subcategory(self, subcategory_id: int) -> tuple[int, dict[str, Any]] | None:
        """Get subcategory by ID from cache. Returns (parent_id, subcategory) or None."""
        return self._subcategory_map.get(subcategory_id)

    def _match_category_by_name(self, query: str) -> int | None:
        """Match a query string against category names.

        Returns category_id if query matches a category name (case-insensitive).
        Handles common variations like singular/plural ("capacitor" -> "Capacitors").
        """
        if not query or not self._categories:
            return None

        query_lower = query.lower().strip()

        for cat in self._categories:
            cat_name = cat["name"].lower()
            # Exact match
            if query_lower == cat_name:
                return cat["id"]
            # Query is singular form of category (e.g., "capacitor" matches "capacitors")
            if cat_name.endswith("s") and query_lower == cat_name[:-1]:
                return cat["id"]
            # Query matches start of category name (e.g., "resistor" matches "resistors")
            if cat_name.startswith(query_lower) and len(query_lower) >= 4:
                return cat["id"]

        return None

    async def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute request with retry logic and browser impersonation."""
        session = await self._get_session()
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                # Fresh randomized headers for each request
                headers = get_jlcpcb_headers()
                response = await session.post(
                    url,
                    json=params,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                # Check for API-level errors
                if data.get("code") != 200:
                    error_msg = data.get("message", "Unknown API error")
                    raise ValueError(f"JLCPCB API error: {error_msg}")

                return data
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    # On retry, create a new session with a fresh fingerprint
                    session = await self._new_session()
                    await asyncio.sleep(0.3 * (attempt + 1))
                else:
                    raise

        raise last_error  # type: ignore

    def _build_search_params(
        self,
        query: str | None = None,
        category_id: int | None = None,
        subcategory_id: int | None = None,
        min_stock: int | None = None,
        library_type: str | None = None,
        package: str | None = None,
        manufacturer: str | None = None,
        page: int = 1,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        """Build search request parameters."""
        # Enforce valid limit range (1 to MAX_PAGE_SIZE)
        effective_limit = max(1, min(limit, MAX_PAGE_SIZE))
        params: dict[str, Any] = {
            "currentPage": page,
            "pageSize": effective_limit,
            "searchSource": "search",
        }

        # Keyword search
        if query:
            params["keyword"] = query

        # Category filtering (requires searchType: 3)
        if category_id:
            cat = self._get_category(category_id)
            if cat:
                params["firstSortId"] = category_id
                params["firstSortName"] = cat["name"]
                params["searchType"] = 3

        # Subcategory filtering
        if subcategory_id:
            result = self._get_subcategory(subcategory_id)
            if result:
                parent_cat_id, sub = result
                # Ensure parent category is set
                if not category_id:
                    parent_cat = self._get_category(parent_cat_id)
                    if parent_cat:
                        params["firstSortId"] = parent_cat_id
                        params["firstSortName"] = parent_cat["name"]
                        params["searchType"] = 3
                params["secondSortId"] = subcategory_id
                params["secondSortName"] = sub["name"]

        # Stock filtering
        if min_stock is not None:
            params["startStockNumber"] = min_stock

        # Library type filtering
        if library_type:
            if library_type == "basic":
                params["componentLibraryType"] = "base"
            elif library_type == "extended":
                params["componentLibraryType"] = "expand"
            elif library_type == "preferred":
                params["preferredComponentFlag"] = True
            elif library_type == "no_fee":
                # Combines basic + preferred in single API call
                params["componentLibraryType"] = "base"
                params["preferredComponentFlag"] = True

        # Package filtering
        if package:
            params["componentSpecification"] = package

        # Manufacturer filtering
        if manufacturer:
            params["componentBrand"] = manufacturer

        return params

    def _transform_part(self, item: dict[str, Any], slim: bool = True) -> dict[str, Any]:
        """Transform API response to our format."""
        # Get price from first tier
        prices = item.get("componentPrices", [])
        price = prices[0]["productPrice"] if prices else None

        # Map library type
        lib_type = item.get("componentLibraryType", "")
        if lib_type == "base":
            library_type = "basic"
        elif lib_type == "expand":
            library_type = "extended"
        else:
            library_type = lib_type

        # Note: API returns firstSortName as subcategory, secondSortName as category
        result: dict[str, Any] = {
            "lcsc": item.get("componentCode"),
            "model": item.get("componentModelEn"),
            "manufacturer": item.get("componentBrandEn"),
            "package": item.get("componentSpecificationEn"),
            "stock": item.get("stockCount"),
            "price": round(price, 4) if price else None,
            "library_type": library_type,
            "preferred": item.get("preferredComponentFlag", False),
            "category": item.get("secondSortName"),  # Primary category
        }

        if not slim:
            # Full details
            result["subcategory"] = item.get("firstSortName")  # Subcategory
            result["description"] = item.get("describe")
            result["min_order"] = item.get("minPurchaseNum")
            result["reel_qty"] = item.get("encapsulationNumber")
            result["datasheet"] = item.get("dataManualUrl")
            result["lcsc_url"] = item.get("lcscGoodsUrl")

            # Transform prices
            if prices:
                result["prices"] = [
                    {
                        "qty": f"{p['startNumber']}+",
                        "price": round(p["productPrice"], 4),
                    }
                    for p in prices
                ]

            # Transform attributes
            attrs = item.get("attributes", [])
            if attrs:
                result["attributes"] = [
                    {
                        "name": a.get("attribute_name_en"),
                        "value": a.get("attribute_value_name"),
                    }
                    for a in attrs
                    if a.get("attribute_name_en")
                ]

        return result

    async def search(
        self,
        query: str | None = None,
        category_id: int | None = None,
        subcategory_id: int | None = None,
        min_stock: int = DEFAULT_MIN_STOCK,
        library_type: str | None = None,
        package: str | None = None,
        manufacturer: str | None = None,
        page: int = 1,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        """Search for components."""
        # Load categories if filtering by category/subcategory, or if we have a query
        # that might match a category name
        if category_id or subcategory_id or query:
            await self._ensure_categories()

        # Auto-match query to category if no category specified
        # e.g., "capacitor" -> category_id=2 (Capacitors)
        if query and not category_id and not subcategory_id:
            matched_category = self._match_category_by_name(query)
            if matched_category:
                category_id = matched_category
                query = None  # Use category filter instead of keyword

        # Build and execute search
        params = self._build_search_params(
            query=query,
            category_id=category_id,
            subcategory_id=subcategory_id,
            min_stock=min_stock,
            library_type=library_type,
            package=package,
            manufacturer=manufacturer,
            page=page,
            limit=limit,
        )

        response = await self._request(JLCPCB_SEARCH_URL, params)
        data = response.get("data") or {}
        page_info = data.get("componentPageInfo") or {}

        items = page_info.get("list") or []
        total = page_info.get("total") or 0

        results = [self._transform_part(item, slim=True) for item in items]

        return {
            "results": results,
            "page": page,
            "per_page": limit,
            "total": total,
            "has_more": page * limit < total,
        }

    async def get_part(self, lcsc: str) -> dict[str, Any] | None:
        """Get full details for a specific part."""
        # Normalize LCSC code to uppercase (e.g., c20917 -> C20917)
        lcsc = lcsc.upper()

        # Search for the exact part code
        params = {
            "keyword": lcsc,
            "currentPage": 1,
            "pageSize": 10,
            "searchSource": "search",
        }

        response = await self._request(JLCPCB_SEARCH_URL, params)
        data = response.get("data", {})
        items = data.get("componentPageInfo", {}).get("list", [])

        # Find exact match
        for item in items:
            if item.get("componentCode") == lcsc:
                return self._transform_part(item, slim=False)

        return None

    async def fetch_categories(self) -> list[dict[str, Any]]:
        """Fetch current categories and subcategories from JLCPCB API.

        Returns a list of categories, each with:
        - id: Category ID (componentSortKeyId)
        - name: Category name
        - count: Number of components
        - subcategories: List of subcategories with same structure
        """
        # Use searchType=3 to get category data in response
        params = {
            "currentPage": 1,
            "pageSize": 1,
            "searchSource": "search",
            "searchType": 3,
        }

        response = await self._request(JLCPCB_SEARCH_URL, params)
        data = response.get("data", {})
        sort_list = data.get("sortAndCountVoList", [])

        if not sort_list:
            return []

        categories = []
        for cat in sort_list:
            subcategories = []
            for sub in cat.get("childSortList") or []:
                subcategories.append({
                    "id": sub.get("componentSortKeyId"),
                    "name": sub.get("sortName"),
                    "count": sub.get("componentCount", 0),
                })

            categories.append({
                "id": cat.get("componentSortKeyId"),
                "name": cat.get("sortName"),
                "count": cat.get("componentCount", 0),
                "subcategories": subcategories,
            })

        return categories
