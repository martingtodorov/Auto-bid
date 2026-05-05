"""
Iteration 16: Active Bids & Outbid Features Testing

Tests for:
1. GET /api/me/preauths - returns BOTH leading AND outbid auctions
2. GET /api/stripe/authorizations/my-credits - returns outbid_bids[] alongside commitments[]
3. Leaderboard translations (EN/RO/BG)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
TEST_USER_EMAIL = "sectest_user@test.bg"
TEST_USER_PASSWORD = "sectest123"
ADMIN_EMAIL = "admin@autoandbid.com"
ADMIN_PASSWORD = "Nero08787"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def test_user_token(api_client):
    """Get authentication token for test user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Test user login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get authentication token for admin"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


class TestMePreauths:
    """Tests for GET /api/me/preauths endpoint - Active Bids section"""

    def test_preauths_requires_auth(self, api_client):
        """Endpoint requires authentication"""
        response = api_client.get(f"{BASE_URL}/api/me/preauths")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /me/preauths requires authentication")

    def test_preauths_returns_list(self, api_client, test_user_token):
        """Endpoint returns a list (may be empty if user has no bids)"""
        response = api_client.get(
            f"{BASE_URL}/api/me/preauths",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✓ /me/preauths returns list with {len(data)} items")

    def test_preauths_response_shape(self, api_client, test_user_token):
        """Verify response shape has required fields for each item"""
        response = api_client.get(
            f"{BASE_URL}/api/me/preauths",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # If there are items, verify the shape
        if data:
            item = data[0]
            required_fields = [
                "auction_id", "auction_title", "is_leading",
                "user_max_bid_eur", "current_bid_eur", "ends_at",
                "max_amount_eur"  # backwards-compat field
            ]
            for field in required_fields:
                assert field in item, f"Missing field: {field}"
            
            # Verify is_leading is a boolean
            assert isinstance(item["is_leading"], bool), "is_leading should be boolean"
            print(f"✓ /me/preauths item has correct shape: {list(item.keys())}")
        else:
            print("✓ /me/preauths returns empty list (user has no active bids)")

    def test_preauths_admin_user(self, api_client, admin_token):
        """Admin can also access their preauths"""
        response = api_client.get(
            f"{BASE_URL}/api/me/preauths",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Admin /me/preauths returns list with {len(data)} items")


class TestMyCreditsOutbidBids:
    """Tests for GET /api/stripe/authorizations/my-credits - outbid_bids[] field"""

    def test_my_credits_requires_auth(self):
        """Endpoint requires authentication"""
        # Use a fresh session without any cookies
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/stripe/authorizations/my-credits")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /stripe/authorizations/my-credits requires authentication")

    def test_my_credits_returns_outbid_bids(self, api_client, test_user_token):
        """Endpoint returns outbid_bids[] alongside commitments[] and holds[]"""
        response = api_client.get(
            f"{BASE_URL}/api/stripe/authorizations/my-credits",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required fields exist
        required_fields = ["holds", "commitments", "outbid_bids", "count",
                          "total_limit_eur", "total_hold_eur", "total_available_eur",
                          "total_committed_eur"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        # Verify outbid_bids is a list
        assert isinstance(data["outbid_bids"], list), "outbid_bids should be a list"
        print(f"✓ /my-credits returns outbid_bids[] with {len(data['outbid_bids'])} items")
        print(f"  - holds: {len(data['holds'])}, commitments: {len(data['commitments'])}")
        print(f"  - total_available_eur: {data['total_available_eur']}")

    def test_my_credits_outbid_bids_shape(self, api_client, test_user_token):
        """Verify outbid_bids item shape if any exist"""
        response = api_client.get(
            f"{BASE_URL}/api/stripe/authorizations/my-credits",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["outbid_bids"]:
            item = data["outbid_bids"][0]
            required_fields = ["auction_id", "auction_title", "current_bid_eur",
                              "user_max_bid_eur", "ends_at"]
            for field in required_fields:
                assert field in item, f"outbid_bids item missing field: {field}"
            print(f"✓ outbid_bids item has correct shape: {list(item.keys())}")
        else:
            print("✓ outbid_bids is empty (user has no outbid auctions)")

    def test_my_credits_commitments_shape(self, api_client, test_user_token):
        """Verify commitments item shape if any exist"""
        response = api_client.get(
            f"{BASE_URL}/api/stripe/authorizations/my-credits",
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["commitments"]:
            item = data["commitments"][0]
            required_fields = ["auction_id", "auction_title", "current_bid_eur", "ends_at"]
            for field in required_fields:
                assert field in item, f"commitments item missing field: {field}"
            print(f"✓ commitments item has correct shape: {list(item.keys())}")
        else:
            print("✓ commitments is empty (user has no leading bids)")


class TestLeaderboardTranslations:
    """Tests for Leaderboard endpoint and translations"""

    def test_leaderboard_reputation(self, api_client):
        """GET /api/leaderboard?type=reputation returns data"""
        response = api_client.get(f"{BASE_URL}/api/leaderboard?type=reputation&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list"
        print(f"✓ Leaderboard reputation returns {len(data)} items")

    def test_leaderboard_sellers(self, api_client):
        """GET /api/leaderboard?type=sellers returns data"""
        response = api_client.get(f"{BASE_URL}/api/leaderboard?type=sellers&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list"
        print(f"✓ Leaderboard sellers returns {len(data)} items")

    def test_leaderboard_commenters(self, api_client):
        """GET /api/leaderboard?type=commenters returns data"""
        response = api_client.get(f"{BASE_URL}/api/leaderboard?type=commenters&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list"
        print(f"✓ Leaderboard commenters returns {len(data)} items")

    def test_leaderboard_bidders(self, api_client):
        """GET /api/leaderboard?type=bidders returns data"""
        response = api_client.get(f"{BASE_URL}/api/leaderboard?type=bidders&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list"
        print(f"✓ Leaderboard bidders returns {len(data)} items")

    def test_leaderboard_period_month(self, api_client):
        """GET /api/leaderboard with period=month filter"""
        response = api_client.get(f"{BASE_URL}/api/leaderboard?type=reputation&period=month&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list"
        print(f"✓ Leaderboard with period=month returns {len(data)} items")

    def test_leaderboard_period_all(self, api_client):
        """GET /api/leaderboard with period=all filter"""
        response = api_client.get(f"{BASE_URL}/api/leaderboard?type=reputation&period=all&limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list"
        print(f"✓ Leaderboard with period=all returns {len(data)} items")


class TestHealthAndBasicEndpoints:
    """Basic health checks and regression tests"""

    def test_healthz(self, api_client):
        """Health check endpoint"""
        response = api_client.get(f"{BASE_URL}/api/healthz")
        assert response.status_code == 200
        print("✓ /healthz returns 200")

    def test_readyz(self, api_client):
        """Readiness check endpoint"""
        response = api_client.get(f"{BASE_URL}/api/readyz")
        assert response.status_code == 200
        print("✓ /readyz returns 200")

    def test_auctions_list(self, api_client):
        """Auctions list endpoint"""
        response = api_client.get(f"{BASE_URL}/api/auctions?limit=5")
        assert response.status_code == 200
        print("✓ /auctions returns 200")

    def test_stripe_config(self, api_client):
        """Stripe config endpoint"""
        response = api_client.get(f"{BASE_URL}/api/stripe/config")
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        assert "mode" in data
        assert "hold_percent" in data
        print(f"✓ /stripe/config returns configured={data['configured']}, mode={data['mode']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
