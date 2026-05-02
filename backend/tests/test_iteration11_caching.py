"""
Test suite for Iteration 11: DB-level projection, anonymous caching, and performance optimizations.

Tests:
1. GET /api/auctions?view=list returns correct fields (DB projection)
2. Anonymous GET /api/auctions sets Cache-Control headers
3. Authenticated GET /api/auctions does NOT set public Cache-Control
4. GET /api/auctions/featured?view=list has correct Cache-Control
5. GET /api/auctions/sold?view=list has correct Cache-Control
6. Status computation (live/ended/sold/reserve_not_met)
7. has_reserve computed correctly, reserve_met not leaked for active auctions
"""
import pytest
import requests
import os

# Use localhost for Cache-Control testing (Cloudflare preview overrides headers)
LOCAL_URL = "http://localhost:8001"
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@autoandbid.com"
ADMIN_PASSWORD = "Nero08787"


def get_auth_cookie():
    """Login and return the access_token cookie"""
    response = requests.post(f"{LOCAL_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.cookies.get("access_token")
    return None


class TestDBProjection:
    """Tests for MongoDB-level projection (view=list)"""

    def test_auctions_list_view_includes_required_fields(self):
        """GET /api/auctions?view=list&paginated=1 returns all fields needed by AuctionCard.jsx"""
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 20
        })
        assert response.status_code == 200
        data = response.json()
        
        # Verify paginated structure
        assert "items" in data, "Missing 'items' in response"
        assert "total" in data, "Missing 'total' in response"
        assert "offset" in data, "Missing 'offset' in response"
        assert "limit" in data, "Missing 'limit' in response"
        
        if len(data["items"]) > 0:
            item = data["items"][0]
            
            # Fields REQUIRED by AuctionCard.jsx (must be present)
            required_fields = [
                "title", "make", "model", "year", "mileage_km", "fuel",
                "city", "country", "current_bid_eur", "buy_now_eur",
                "bid_count", "has_reserve", "no_reserve", "ends_at",
                "status", "featured", "vat_status", "vat_rate_pct",
                "seller_is_verified_dealer", "thumbnails", "images"
            ]
            
            missing = [f for f in required_fields if f not in item]
            assert len(missing) == 0, f"Missing required fields: {missing}"
            print(f"✓ All required fields present: {required_fields}")

    def test_auctions_list_view_excludes_heavy_fields(self):
        """GET /api/auctions?view=list MUST exclude heavy fields (DB projection)"""
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 20
        })
        assert response.status_code == 200
        data = response.json()
        
        if len(data["items"]) > 0:
            item = data["items"][0]
            
            # Fields that MUST be excluded (per _LIST_MONGO_PROJECTION)
            excluded_fields = [
                "description", "description_en",
                "images_exterior", "images_wheels", "images_bumper", "images_interior",
                "contact_email", "contact_phone", "vin",
                "power_hp", "engine_cc", "price_net_eur", "price_gross_eur",
                "duration_days", "approved_at", "views_count",
                "specs", "documents", "service_history",
                "rejection_reason", "translations"
            ]
            
            present = [f for f in excluded_fields if f in item]
            assert len(present) == 0, f"Heavy fields should be excluded: {present}"
            print(f"✓ All heavy fields correctly excluded")


class TestAnonymousCacheControl:
    """Tests for Cache-Control headers on anonymous requests"""

    def test_auctions_anonymous_has_cache_control(self):
        """GET /api/auctions (anonymous, no cookie) sets Cache-Control header"""
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 20
        })
        assert response.status_code == 200
        
        cache_control = response.headers.get("Cache-Control", "")
        vary = response.headers.get("Vary", "")
        
        print(f"Anonymous Cache-Control: {cache_control}")
        print(f"Anonymous Vary: {vary}")
        
        # Expected: public, max-age=15, s-maxage=30, stale-while-revalidate=60
        assert "public" in cache_control, "Missing 'public' in Cache-Control"
        assert "max-age=15" in cache_control, "Missing 'max-age=15' in Cache-Control"
        assert "s-maxage=30" in cache_control, "Missing 's-maxage=30' in Cache-Control"
        assert "stale-while-revalidate=60" in cache_control, "Missing 'stale-while-revalidate=60'"
        
        # Vary header should include Cookie and Accept-Language
        assert "Cookie" in vary, "Missing 'Cookie' in Vary header"
        assert "Accept-Language" in vary, "Missing 'Accept-Language' in Vary header"

    def test_auctions_authenticated_no_public_cache(self):
        """GET /api/auctions WITH authenticated user must NOT set public Cache-Control"""
        # First login to get token
        login_response = requests.post(f"{LOCAL_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        
        # Get the token from response (cookie has Secure flag, use Bearer token instead)
        token = login_response.json().get("token")
        assert token, "No token in login response"
        
        # Make authenticated request with Bearer token
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 20
        }, headers={"Authorization": f"Bearer {token}"})
        
        assert response.status_code == 200
        
        cache_control = response.headers.get("Cache-Control", "")
        print(f"Authenticated Cache-Control: '{cache_control}'")
        
        # Authenticated users should NOT get public cache header
        # Either no Cache-Control or not "public"
        if cache_control:
            assert "public" not in cache_control, "Authenticated requests should NOT have 'public' Cache-Control"
        print("✓ Authenticated request does not have public Cache-Control")


class TestFeaturedCacheControl:
    """Tests for /api/auctions/featured Cache-Control"""

    def test_featured_view_list_cache_control(self):
        """GET /api/auctions/featured?view=list has correct Cache-Control"""
        response = requests.get(f"{LOCAL_URL}/api/auctions/featured", params={"view": "list"})
        assert response.status_code == 200
        
        cache_control = response.headers.get("Cache-Control", "")
        print(f"Featured Cache-Control: {cache_control}")
        
        # Expected: public, max-age=30, s-maxage=60, stale-while-revalidate=120
        assert "public" in cache_control, "Missing 'public'"
        assert "max-age=30" in cache_control, "Missing 'max-age=30'"
        assert "s-maxage=60" in cache_control, "Missing 's-maxage=60'"

    def test_featured_returns_trimmed_array(self):
        """GET /api/auctions/featured?view=list returns trimmed array"""
        response = requests.get(f"{LOCAL_URL}/api/auctions/featured", params={"view": "list"})
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list), "Featured should return array"
        
        if len(data) > 0:
            item = data[0]
            # Should have required fields
            assert "id" in item
            assert "title" in item
            # Should NOT have heavy fields
            assert "description" not in item
            assert "images_exterior" not in item
            print(f"✓ Featured returns {len(data)} trimmed items")


class TestSoldCacheControl:
    """Tests for /api/auctions/sold Cache-Control"""

    def test_sold_view_list_cache_control(self):
        """GET /api/auctions/sold?view=list has correct Cache-Control"""
        response = requests.get(f"{LOCAL_URL}/api/auctions/sold", params={"view": "list"})
        assert response.status_code == 200
        
        cache_control = response.headers.get("Cache-Control", "")
        print(f"Sold Cache-Control: {cache_control}")
        
        # Expected: public, max-age=60, s-maxage=300, stale-while-revalidate=600
        assert "public" in cache_control, "Missing 'public'"
        assert "max-age=60" in cache_control, "Missing 'max-age=60'"
        assert "s-maxage=300" in cache_control, "Missing 's-maxage=300'"

    def test_sold_returns_trimmed_array(self):
        """GET /api/auctions/sold?view=list returns trimmed array"""
        response = requests.get(f"{LOCAL_URL}/api/auctions/sold", params={"view": "list"})
        assert response.status_code == 200
        data = response.json()
        
        # Could be array or paginated object
        items = data if isinstance(data, list) else data.get("items", [])
        
        if len(items) > 0:
            item = items[0]
            # Should NOT have heavy fields
            assert "description" not in item
            print(f"✓ Sold returns {len(items)} trimmed items")


class TestStatusComputation:
    """Tests for status field computation"""

    def test_status_field_present_and_valid(self):
        """Status field should be computed correctly (live/ended/sold/reserve_not_met)"""
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 50,
            "status": ""  # Get all statuses
        })
        assert response.status_code == 200
        data = response.json()
        
        valid_statuses = {"live", "ended", "sold", "reserve_not_met"}
        
        for item in data.get("items", []):
            status = item.get("status")
            assert status in valid_statuses, f"Invalid status: {status}"
        
        # Count by status
        status_counts = {}
        for item in data.get("items", []):
            s = item.get("status")
            status_counts[s] = status_counts.get(s, 0) + 1
        print(f"Status distribution: {status_counts}")

    def test_has_reserve_computed_correctly(self):
        """has_reserve should be computed correctly"""
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 50
        })
        assert response.status_code == 200
        data = response.json()
        
        for item in data.get("items", []):
            has_reserve = item.get("has_reserve")
            no_reserve = item.get("no_reserve")
            
            # has_reserve and no_reserve should be boolean
            assert isinstance(has_reserve, bool), f"has_reserve should be bool, got {type(has_reserve)}"
            assert isinstance(no_reserve, bool), f"no_reserve should be bool, got {type(no_reserve)}"
            
            # If no_reserve is True, has_reserve should be False
            if no_reserve:
                assert has_reserve == False, "If no_reserve=True, has_reserve should be False"

    def test_reserve_met_not_leaked_for_live_auctions(self):
        """reserve_met should NOT be revealed for live auctions (unless owner/admin)"""
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 50,
            "status": "live"
        })
        assert response.status_code == 200
        data = response.json()
        
        for item in data.get("items", []):
            if item.get("status") == "live" and item.get("has_reserve"):
                reserve_met = item.get("reserve_met")
                # For anonymous users viewing live auctions with reserve,
                # reserve_met should be None (not revealed)
                assert reserve_met is None, f"reserve_met should be None for live auction with reserve, got {reserve_met}"
        
        print("✓ reserve_met correctly hidden for live auctions")


class TestFilteringAndSearch:
    """Tests for filtering and search functionality"""

    def test_filtering_by_make(self):
        """Filtering by make should work correctly"""
        # First get available makes
        facets_response = requests.get(f"{LOCAL_URL}/api/auctions/facets")
        assert facets_response.status_code == 200
        makes = facets_response.json().get("makes", [])
        
        if makes:
            make = makes[0]
            response = requests.get(f"{LOCAL_URL}/api/auctions", params={
                "view": "list",
                "paginated": 1,
                "limit": 20,
                "make": make
            })
            assert response.status_code == 200
            data = response.json()
            
            # All items should have the filtered make
            for item in data.get("items", []):
                assert item.get("make") == make, f"Expected make={make}, got {item.get('make')}"
            print(f"✓ Filtering by make '{make}' works correctly")

    def test_search_query(self):
        """Search query (?q=...) should work correctly"""
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 20,
            "q": "BMW"
        })
        assert response.status_code == 200
        data = response.json()
        
        # Should return paginated structure
        assert "items" in data
        assert "total" in data
        print(f"✓ Search for 'BMW' returned {data['total']} results")


class TestPaginationStructure:
    """Tests for pagination structure"""

    def test_paginated_response_structure(self):
        """Paginated response should have correct structure"""
        response = requests.get(f"{LOCAL_URL}/api/auctions", params={
            "view": "list",
            "paginated": 1,
            "limit": 20,
            "offset": 0
        })
        assert response.status_code == 200
        data = response.json()
        
        # Required fields
        assert "items" in data, "Missing 'items'"
        assert "total" in data, "Missing 'total'"
        assert "offset" in data, "Missing 'offset'"
        assert "limit" in data, "Missing 'limit'"
        
        # Types
        assert isinstance(data["items"], list), "items should be list"
        assert isinstance(data["total"], int), "total should be int"
        assert isinstance(data["offset"], int), "offset should be int"
        assert isinstance(data["limit"], int), "limit should be int"
        
        print(f"✓ Pagination: {len(data['items'])} items, total={data['total']}, offset={data['offset']}, limit={data['limit']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
