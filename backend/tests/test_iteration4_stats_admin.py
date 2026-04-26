"""
Iteration 4 Tests: Stats Dashboard + Admin Routes Refactor

Tests:
1. NEW: GET /api/stats/sold - public stats endpoint with window filter
2. NEW: Enhanced GET /api/auctions/sold with filters and pagination
3. REFACTOR: Admin routes moved to routers/admin.py
4. REGRESSION: Admin auction lifecycle routes in server.py
5. REGRESSION: Reviews flow
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "contact@autoandbid.com"
ADMIN_PASSWORD = "admin123"
BUYER_EMAIL = "reviewbuyer@test.bg"
BUYER_PASSWORD = "test12345"

# Known IDs
SOLD_AUCTION_ID = "c049f61a-7c0b-4cf5-994f-387776bb2403"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def admin_id(admin_token):
    """Get admin user ID"""
    resp = requests.get(f"{BASE_URL}/api/auth/me", headers={
        "Authorization": f"Bearer {admin_token}"
    })
    assert resp.status_code == 200
    return resp.json()["id"]


@pytest.fixture(scope="module")
def buyer_token():
    """Get buyer auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": BUYER_EMAIL,
        "password": BUYER_PASSWORD
    })
    assert resp.status_code == 200, f"Buyer login failed: {resp.text}"
    return resp.json()["token"]


class TestStatsSoldEndpoint:
    """Tests for NEW GET /api/stats/sold endpoint"""

    def test_stats_sold_no_window(self):
        """GET /api/stats/sold returns all-time stats"""
        resp = requests.get(f"{BASE_URL}/api/stats/sold")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify all expected fields
        assert "window_days" in data
        assert data["window_days"] is None
        assert "total_count" in data
        assert "total_volume_eur" in data
        assert "avg_price_eur" in data
        assert "median_price_eur" in data
        assert "min_price_eur" in data
        assert "max_price_eur" in data
        assert "avg_mileage_km" in data
        assert "by_make" in data
        assert "by_body_type" in data
        assert "by_month" in data
        assert "highest_sale" in data
        
        # Verify data types
        assert isinstance(data["total_count"], int)
        assert isinstance(data["by_make"], list)
        assert isinstance(data["by_body_type"], list)
        assert isinstance(data["by_month"], list)

    def test_stats_sold_30_day_window(self):
        """GET /api/stats/sold?days=30 returns 30-day stats"""
        resp = requests.get(f"{BASE_URL}/api/stats/sold", params={"days": 30})
        assert resp.status_code == 200
        data = resp.json()
        assert data["window_days"] == 30

    def test_stats_sold_90_day_window(self):
        """GET /api/stats/sold?days=90 returns 90-day stats"""
        resp = requests.get(f"{BASE_URL}/api/stats/sold", params={"days": 90})
        assert resp.status_code == 200
        data = resp.json()
        assert data["window_days"] == 90

    def test_stats_sold_365_day_window(self):
        """GET /api/stats/sold?days=365 returns 365-day stats"""
        resp = requests.get(f"{BASE_URL}/api/stats/sold", params={"days": 365})
        assert resp.status_code == 200
        data = resp.json()
        assert data["window_days"] == 365

    def test_stats_sold_by_make_structure(self):
        """Verify by_make array structure"""
        resp = requests.get(f"{BASE_URL}/api/stats/sold")
        assert resp.status_code == 200
        data = resp.json()
        
        if data["by_make"]:
            make_item = data["by_make"][0]
            assert "make" in make_item
            assert "count" in make_item
            assert "avg_eur" in make_item
            assert "total_eur" in make_item

    def test_stats_sold_highest_sale_structure(self):
        """Verify highest_sale object structure"""
        resp = requests.get(f"{BASE_URL}/api/stats/sold")
        assert resp.status_code == 200
        data = resp.json()
        
        if data["highest_sale"]:
            hs = data["highest_sale"]
            assert "id" in hs
            assert "title" in hs
            assert "current_bid_eur" in hs


class TestEnhancedAuctionsSold:
    """Tests for enhanced GET /api/auctions/sold with filters"""

    def test_auctions_sold_no_params_returns_list(self):
        """GET /api/auctions/sold without params returns plain list (backwards compat)"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold")
        assert resp.status_code == 200
        data = resp.json()
        # Should be a plain list for backwards compatibility
        assert isinstance(data, list)

    def test_auctions_sold_with_make_filter(self):
        """GET /api/auctions/sold?make=BMW returns paginated object"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold", params={"make": "BMW"})
        assert resp.status_code == 200
        data = resp.json()
        
        # Should return paginated object when filter is used
        assert isinstance(data, dict)
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data

    def test_auctions_sold_with_body_type_filter(self):
        """GET /api/auctions/sold?body_type=Купе returns paginated object"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold", params={"body_type": "Купе"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "items" in data

    def test_auctions_sold_with_year_filter(self):
        """GET /api/auctions/sold?year_min=2015 returns paginated object"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold", params={"year_min": 2015})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_auctions_sold_with_price_filter(self):
        """GET /api/auctions/sold?price_max=20000 returns paginated object"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold", params={"price_max": 20000})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_auctions_sold_with_search_query(self):
        """GET /api/auctions/sold?q=BMW returns paginated object"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold", params={"q": "BMW"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_auctions_sold_sort_price_desc(self):
        """GET /api/auctions/sold?sort=price_desc returns paginated object"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold", params={"sort": "price_desc", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_auctions_sold_sort_price_asc(self):
        """GET /api/auctions/sold?sort=price_asc returns paginated object"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold", params={"sort": "price_asc", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_auctions_sold_pagination(self):
        """GET /api/auctions/sold with offset returns paginated object"""
        resp = requests.get(f"{BASE_URL}/api/auctions/sold", params={"offset": 0, "limit": 10, "make": "BMW"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert data["offset"] == 0
        assert data["limit"] == 10


class TestAdminSettingsRoutes:
    """Tests for admin settings routes (moved to routers/admin.py)"""

    def test_admin_get_settings(self, admin_token):
        """GET /api/admin/settings returns settings"""
        resp = requests.get(f"{BASE_URL}/api/admin/settings", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "buyer_fee_pct" in data
        assert "buyer_fee_min_eur" in data
        assert "buyer_fee_max_eur" in data

    def test_admin_update_settings_valid(self, admin_token):
        """PUT /api/admin/settings with valid fee"""
        resp = requests.put(f"{BASE_URL}/api/admin/settings", 
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"buyer_fee_pct": 2.5}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["buyer_fee_pct"] == 2.5
        
        # Restore original
        requests.put(f"{BASE_URL}/api/admin/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"buyer_fee_pct": 2.0}
        )

    def test_admin_update_settings_fee_too_high(self, admin_token):
        """PUT /api/admin/settings rejects fee > 25%"""
        resp = requests.put(f"{BASE_URL}/api/admin/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"buyer_fee_pct": 30}
        )
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_admin_update_settings_negative_fee(self, admin_token):
        """PUT /api/admin/settings rejects negative fee"""
        resp = requests.put(f"{BASE_URL}/api/admin/settings",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"buyer_fee_pct": -5}
        )
        assert resp.status_code == 400


class TestAdminStatsRoute:
    """Tests for admin stats route (moved to routers/admin.py)"""

    def test_admin_stats(self, admin_token):
        """GET /api/admin/stats returns platform KPIs"""
        resp = requests.get(f"{BASE_URL}/api/admin/stats", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "auctions" in data
        assert "users" in data
        assert "bids" in data
        assert "revenue" in data

    def test_admin_stats_requires_auth(self):
        """GET /api/admin/stats requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/admin/stats")
        assert resp.status_code == 401


class TestAdminUsersRoutes:
    """Tests for admin users routes (moved to routers/admin.py)"""

    def test_admin_list_users(self, admin_token):
        """GET /api/admin/users returns user list"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_admin_list_users_with_search(self, admin_token):
        """GET /api/admin/users?q=admin filters users"""
        resp = requests.get(f"{BASE_URL}/api/admin/users", 
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"q": "admin"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should find admin user
        assert len(data) >= 1

    def test_admin_get_user(self, admin_token, admin_id):
        """GET /api/admin/users/{id} returns user details"""
        resp = requests.get(f"{BASE_URL}/api/admin/users/{admin_id}", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data
        assert "role" in data

    def test_admin_update_user_phone_validation(self, admin_token):
        """PUT /api/admin/users/{id} validates phone format"""
        # Get a regular user
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        users = [u for u in users_resp.json() if u.get("role") == "user"]
        if not users:
            pytest.skip("No regular users to test")
        
        user_id = users[0]["id"]
        resp = requests.put(f"{BASE_URL}/api/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"phone": "0888123456"}  # Missing + prefix
        )
        assert resp.status_code == 400
        assert "+" in resp.json().get("detail", "")

    def test_admin_update_user_invalid_role(self, admin_token):
        """PUT /api/admin/users/{id} rejects invalid role"""
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        users = [u for u in users_resp.json() if u.get("role") == "user"]
        if not users:
            pytest.skip("No regular users to test")
        
        user_id = users[0]["id"]
        resp = requests.put(f"{BASE_URL}/api/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"role": "superadmin"}
        )
        assert resp.status_code == 400

    def test_admin_cannot_demote_self(self, admin_token, admin_id):
        """PUT /api/admin/users/{admin_id} cannot demote self"""
        resp = requests.put(f"{BASE_URL}/api/admin/users/{admin_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"role": "user"}
        )
        assert resp.status_code == 400


class TestAdminBanRoutes:
    """Tests for admin ban/unban routes (moved to routers/admin.py)"""

    def test_admin_cannot_ban_self(self, admin_token, admin_id):
        """POST /api/admin/users/{admin_id}/ban cannot ban self"""
        resp = requests.post(f"{BASE_URL}/api/admin/users/{admin_id}/ban", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 400

    def test_admin_ban_unban_user(self, admin_token):
        """POST /api/admin/users/{id}/ban and /unban work correctly"""
        # Get a regular user
        users_resp = requests.get(f"{BASE_URL}/api/admin/users", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        users = [u for u in users_resp.json() if u.get("role") == "user"]
        if not users:
            pytest.skip("No regular users to test")
        
        user_id = users[0]["id"]
        
        # Ban
        ban_resp = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/ban", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert ban_resp.status_code == 200
        assert ban_resp.json()["banned"] == True
        
        # Unban
        unban_resp = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/unban", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert unban_resp.status_code == 200
        assert unban_resp.json()["banned"] == False


class TestAdminAuctionLifecycleRoutes:
    """Tests for admin auction routes that stayed in server.py"""

    def test_admin_pending(self, admin_token):
        """GET /api/admin/pending returns pending auctions"""
        resp = requests.get(f"{BASE_URL}/api/admin/pending", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_auctions_list(self, admin_token):
        """GET /api/admin/auctions returns all auctions"""
        resp = requests.get(f"{BASE_URL}/api/admin/auctions", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_admin_auctions_filter_status(self, admin_token):
        """GET /api/admin/auctions?status=sold filters by status"""
        resp = requests.get(f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"status": "sold"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        for auction in data:
            assert auction.get("status") == "sold"

    def test_admin_sold_list(self, admin_token):
        """GET /api/admin/sold returns sold auctions with winner info"""
        resp = requests.get(f"{BASE_URL}/api/admin/sold", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if data:
            # Should have enriched winner info
            assert "winner_email" in data[0]
            assert "commission_eur" in data[0]

    def test_admin_get_auction(self, admin_token):
        """GET /api/admin/auctions/{id} returns auction details"""
        resp = requests.get(f"{BASE_URL}/api/admin/auctions/{SOLD_AUCTION_ID}", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "title" in data
        assert "status" in data


class TestReviewsRegression:
    """Regression tests for reviews flow"""

    def test_get_seller_reviews(self, admin_id):
        """GET /api/users/{seller_id}/reviews returns reviews"""
        resp = requests.get(f"{BASE_URL}/api/users/{admin_id}/reviews")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "rating" in data
        assert "avg" in data["rating"]
        assert "count" in data["rating"]

    def test_get_seller_rating(self, admin_id):
        """GET /api/users/{seller_id}/rating returns rating"""
        resp = requests.get(f"{BASE_URL}/api/users/{admin_id}/rating")
        assert resp.status_code == 200
        data = resp.json()
        assert "avg" in data
        assert "count" in data


class TestAuthRegression:
    """Regression tests for auth"""

    def test_login_success(self):
        """POST /api/auth/login works"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_me_endpoint(self, admin_token):
        """GET /api/auth/me returns user info"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "email" in data
        assert "role" in data


class TestAuctionsRegression:
    """Regression tests for auctions"""

    def test_list_auctions(self):
        """GET /api/auctions returns list"""
        resp = requests.get(f"{BASE_URL}/api/auctions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_auction(self):
        """GET /api/auctions/{id} returns auction"""
        resp = requests.get(f"{BASE_URL}/api/auctions/{SOLD_AUCTION_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert "title" in data
        assert "status" in data
        assert data["status"] == "sold"
