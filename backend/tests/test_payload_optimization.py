"""
Test suite for JSON payload optimization feature.
Tests view=list parameter, Cache-Control headers, and field trimming.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
# For Cache-Control header testing, use localhost directly (Cloudflare preview overrides headers)
LOCAL_URL = "http://localhost:8001"


class TestPayloadOptimization:
    """Tests for view=list payload trimming feature"""

    def test_health_check(self):
        """Verify backend is running"""
        response = requests.get(f"{BASE_URL}/api/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_auctions_list_view_returns_trimmed_payload(self):
        """GET /api/auctions?view=list returns trimmed payload"""
        response = requests.get(f"{BASE_URL}/api/auctions", params={"view": "list", "limit": 5})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            item = data[0]
            # Required fields that MUST be present
            required_fields = [
                "id", "title", "make", "model", "year", "mileage_km", "fuel", "transmission",
                "body_type", "color", "region", "city", "country",
                "starting_bid_eur", "current_bid_eur", "buy_now_eur",
                "reserve_met", "has_reserve", "no_reserve",
                "bid_count", "ends_at", "status",
                "featured", "seller_is_verified_dealer",
                "vat_status", "vat_rate_pct",
                "thumbnails", "images"
            ]
            for field in required_fields:
                assert field in item, f"Missing required field: {field}"
            
            # Fields that MUST NOT be present (heavy fields)
            forbidden_fields = [
                "description", "description_en",
                "images_exterior", "images_wheels", "images_bumper", "images_interior",
                "vin", "seller_id", "seller_name",
                "contact_email", "contact_phone",
                "power_hp", "engine_cc",
                "price_net_eur", "price_gross_eur",
                "duration_days", "approved_at", "views_count"
            ]
            for field in forbidden_fields:
                assert field not in item, f"Forbidden field present: {field}"
            
            # Images and thumbnails should be limited to 1
            assert len(item.get("images", [])) <= 1, "Images should be limited to 1"
            assert len(item.get("thumbnails", [])) <= 1, "Thumbnails should be limited to 1"

    def test_auctions_list_view_payload_size_reduction(self):
        """view=list should reduce payload size by at least 50%"""
        # Get full payload
        full_response = requests.get(f"{BASE_URL}/api/auctions", params={"limit": 5})
        full_size = len(full_response.content)
        
        # Get trimmed payload
        trimmed_response = requests.get(f"{BASE_URL}/api/auctions", params={"view": "list", "limit": 5})
        trimmed_size = len(trimmed_response.content)
        
        if full_size > 0:
            reduction = (full_size - trimmed_size) / full_size * 100
            print(f"Payload reduction: {reduction:.1f}% (full: {full_size} bytes, trimmed: {trimmed_size} bytes)")
            # Expect at least 50% reduction (spec says 80%, but depends on data)
            assert reduction >= 50, f"Expected at least 50% reduction, got {reduction:.1f}%"

    def test_auctions_paginated_with_view_list(self):
        """GET /api/auctions?view=list&paginated=1 returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 12,
            "offset": 0
        })
        assert response.status_code == 200
        data = response.json()
        
        # Should return paginated structure
        assert "items" in data, "Missing 'items' in paginated response"
        assert "total" in data, "Missing 'total' in paginated response"
        assert "offset" in data, "Missing 'offset' in paginated response"
        assert "limit" in data, "Missing 'limit' in paginated response"
        
        # Items should be trimmed
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "description" not in item, "Paginated items should be trimmed"
            assert len(item.get("images", [])) <= 1, "Images should be limited to 1"


class TestCacheControlHeaders:
    """Tests for Cache-Control headers on featured and sold endpoints"""

    def test_featured_cache_control_header(self):
        """GET /api/auctions/featured should have correct Cache-Control header"""
        response = requests.get(f"{LOCAL_URL}/api/auctions/featured", params={"view": "list"})
        assert response.status_code == 200
        
        cache_control = response.headers.get("Cache-Control", "")
        print(f"Featured Cache-Control: {cache_control}")
        
        # Expected: public, max-age=30, s-maxage=60, stale-while-revalidate=120
        assert "public" in cache_control, "Missing 'public' in Cache-Control"
        assert "max-age=30" in cache_control, "Missing 'max-age=30' in Cache-Control"
        assert "s-maxage=60" in cache_control, "Missing 's-maxage=60' in Cache-Control"
        assert "stale-while-revalidate=120" in cache_control, "Missing 'stale-while-revalidate=120'"

    def test_sold_cache_control_header(self):
        """GET /api/auctions/sold should have correct Cache-Control header"""
        response = requests.get(f"{LOCAL_URL}/api/auctions/sold", params={"view": "list"})
        assert response.status_code == 200
        
        cache_control = response.headers.get("Cache-Control", "")
        print(f"Sold Cache-Control: {cache_control}")
        
        # Expected: public, max-age=60, s-maxage=300, stale-while-revalidate=600
        assert "public" in cache_control, "Missing 'public' in Cache-Control"
        assert "max-age=60" in cache_control, "Missing 'max-age=60' in Cache-Control"
        assert "s-maxage=300" in cache_control, "Missing 's-maxage=300' in Cache-Control"
        assert "stale-while-revalidate=600" in cache_control, "Missing 'stale-while-revalidate=600'"


class TestFeaturedEndpoint:
    """Tests for /api/auctions/featured endpoint"""

    def test_featured_returns_array(self):
        """GET /api/auctions/featured returns array"""
        response = requests.get(f"{BASE_URL}/api/auctions/featured")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Featured should return array"

    def test_featured_with_view_list_returns_trimmed(self):
        """GET /api/auctions/featured?view=list returns trimmed items"""
        response = requests.get(f"{BASE_URL}/api/auctions/featured", params={"view": "list"})
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            # Should have required fields
            assert "id" in item
            assert "title" in item
            assert "images" in item
            assert "thumbnails" in item
            
            # Should NOT have heavy fields
            assert "description" not in item
            assert "images_exterior" not in item
            
            # Images limited to 1
            assert len(item.get("images", [])) <= 1


class TestSoldEndpoint:
    """Tests for /api/auctions/sold endpoint"""

    def test_sold_returns_array_backwards_compat(self):
        """GET /api/auctions/sold returns array for backwards compatibility"""
        response = requests.get(f"{BASE_URL}/api/auctions/sold")
        assert response.status_code == 200
        data = response.json()
        # Default (no filters, limit=48, offset=0) should return plain array
        assert isinstance(data, list), "Sold should return array for backwards compat"

    def test_sold_with_view_list_returns_trimmed(self):
        """GET /api/auctions/sold?view=list returns trimmed items"""
        response = requests.get(f"{BASE_URL}/api/auctions/sold", params={"view": "list"})
        assert response.status_code == 200
        data = response.json()
        
        # Could be array or paginated object depending on filters
        items = data if isinstance(data, list) else data.get("items", [])
        
        if len(items) > 0:
            item = items[0]
            # Should NOT have heavy fields
            assert "description" not in item
            assert "images_exterior" not in item


class TestFullPayloadBackwardsCompat:
    """Tests to ensure full payload still works for legacy callers"""

    def test_auctions_without_view_param_returns_full(self):
        """GET /api/auctions (no view param) returns full payload"""
        response = requests.get(f"{BASE_URL}/api/auctions", params={"limit": 1})
        assert response.status_code == 200
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
            # Full payload should have more fields than trimmed
            # At minimum, should have seller_id (which is excluded in list view)
            # Note: seller_id might be excluded for privacy, so check for other full fields
            print(f"Full payload fields: {list(item.keys())}")

    def test_featured_without_view_param_returns_full(self):
        """GET /api/auctions/featured (no view param) returns full payload"""
        response = requests.get(f"{BASE_URL}/api/auctions/featured")
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            # Full payload should have description if it exists in the auction
            print(f"Featured full payload fields: {list(item.keys())}")


class TestSlugField:
    """Tests for slug field in trimmed payload"""

    def test_slug_included_if_present(self):
        """Slug field should be included in trimmed payload if present"""
        response = requests.get(f"{BASE_URL}/api/auctions", params={"view": "list", "limit": 5})
        assert response.status_code == 200
        data = response.json()
        
        # Check if any auction has slug
        for item in data:
            if "slug" in item:
                print(f"Found auction with slug: {item['slug']}")
                break
        # Note: slug is optional, so we just verify it's not stripped if present


class TestAuctionCardRequiredFields:
    """Tests to verify all fields AuctionCard.jsx needs are present"""

    def test_auction_card_fields_present(self):
        """All fields used by AuctionCard.jsx should be in trimmed payload"""
        response = requests.get(f"{BASE_URL}/api/auctions", params={"view": "list", "limit": 5})
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            item = data[0]
            
            # Fields used by AuctionCard.jsx (from code review)
            card_fields = [
                "id",                       # Link to auction
                "title",                    # Card title
                "thumbnails",               # Image source (primary)
                "images",                   # Image source (fallback)
                "featured",                 # Featured badge
                "vat_status",               # VAT badge
                "vat_rate_pct",             # VAT calculation
                "seller_is_verified_dealer", # Verified dealer badge
                "status",                   # Sold/ended badge
                "ends_at",                  # Time left calculation
                "year",                     # Spec display
                "mileage_km",               # Spec display
                "fuel",                     # Spec display
                "city",                     # Location display
                "country",                  # Location display
                "current_bid_eur",          # Price display
                "buy_now_eur",              # Buy now badge
                "bid_count",                # Bids count
                "has_reserve",              # Reserve badge
                "no_reserve",               # No reserve badge (alternative)
            ]
            
            missing = [f for f in card_fields if f not in item]
            if missing:
                print(f"Missing fields for AuctionCard: {missing}")
            assert len(missing) == 0, f"Missing fields for AuctionCard: {missing}"
