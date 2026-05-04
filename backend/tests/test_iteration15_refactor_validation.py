"""
Iteration 15: Backend Refactor Validation Tests

Tests the newly extracted routers after the 2026-05-04 refactor:
- /api/leaderboard (leaderboard.py) - 4 types: reputation, sellers, commenters, bidders
- /api/auctions/{id}/watch-status, /api/auctions/{id}/watch, /api/me/watchlist (watchlist.py)
- /api/me/listings, /api/me/bids (watchlist.py)
- /api/stripe/authorizations/my-credits, /api/stripe/authorizations/{id}/release (stripe_holds.py)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://auction-drive-bg.preview.emergentagent.com"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@autoandbid.com"
ADMIN_PASSWORD = "Nero08787"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for authenticated requests"""
    return {"Authorization": f"Bearer {admin_token}"}


class TestHealthCheck:
    """Basic health check to ensure backend is running"""

    def test_healthz(self):
        resp = requests.get(f"{BASE_URL}/api/healthz")
        assert resp.status_code == 200
        assert resp.json().get("status") == "ok"

    def test_readyz(self):
        resp = requests.get(f"{BASE_URL}/api/readyz")
        assert resp.status_code == 200
        assert resp.json().get("status") == "ready"


class TestLeaderboardRouter:
    """Tests for /api/leaderboard endpoint (routers/leaderboard.py)"""

    def test_leaderboard_reputation(self):
        """GET /api/leaderboard?type=reputation returns list with rank/user_id/score"""
        resp = requests.get(f"{BASE_URL}/api/leaderboard", params={"type": "reputation", "limit": 20})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # If there are results, validate structure
        if data:
            item = data[0]
            assert "rank" in item
            assert "user_id" in item
            assert "score" in item
            assert "name" in item
            assert item["rank"] == 1

    def test_leaderboard_sellers(self):
        """GET /api/leaderboard?type=sellers works"""
        resp = requests.get(f"{BASE_URL}/api/leaderboard", params={"type": "sellers", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_leaderboard_commenters(self):
        """GET /api/leaderboard?type=commenters works"""
        resp = requests.get(f"{BASE_URL}/api/leaderboard", params={"type": "commenters", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if data:
            item = data[0]
            assert "rank" in item
            assert "user_id" in item
            assert "score" in item
            assert "extra" in item
            assert "comments" in item.get("extra", {})

    def test_leaderboard_bidders(self):
        """GET /api/leaderboard?type=bidders works"""
        resp = requests.get(f"{BASE_URL}/api/leaderboard", params={"type": "bidders", "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_leaderboard_invalid_type(self):
        """GET /api/leaderboard with invalid type returns 422"""
        resp = requests.get(f"{BASE_URL}/api/leaderboard", params={"type": "invalid"})
        assert resp.status_code == 422

    def test_leaderboard_period_month(self):
        """GET /api/leaderboard with period=month works"""
        resp = requests.get(f"{BASE_URL}/api/leaderboard", params={"type": "reputation", "period": "month"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestWatchlistRouter:
    """Tests for watchlist endpoints (routers/watchlist.py)"""

    @pytest.fixture(scope="class")
    def live_auction_id(self):
        """Get a live auction ID for testing"""
        resp = requests.get(f"{BASE_URL}/api/auctions", params={"status": "live", "limit": 1})
        assert resp.status_code == 200
        auctions = resp.json()
        if isinstance(auctions, dict):
            auctions = auctions.get("items", [])
        if auctions:
            return auctions[0]["id"]
        pytest.skip("No live auctions available for testing")

    def test_watch_status_requires_auth(self, live_auction_id):
        """GET /api/auctions/{id}/watch-status requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/auctions/{live_auction_id}/watch-status")
        assert resp.status_code == 401

    def test_watch_status_authenticated(self, auth_headers, live_auction_id):
        """GET /api/auctions/{id}/watch-status returns {watching: bool}"""
        resp = requests.get(
            f"{BASE_URL}/api/auctions/{live_auction_id}/watch-status",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "watching" in data
        assert isinstance(data["watching"], bool)

    def test_watch_toggle(self, auth_headers, live_auction_id):
        """POST /api/auctions/{id}/watch toggles watch status"""
        # Get initial status
        resp1 = requests.get(
            f"{BASE_URL}/api/auctions/{live_auction_id}/watch-status",
            headers=auth_headers,
        )
        initial_watching = resp1.json().get("watching")

        # Toggle
        resp2 = requests.post(
            f"{BASE_URL}/api/auctions/{live_auction_id}/watch",
            headers=auth_headers,
        )
        assert resp2.status_code == 200
        toggled = resp2.json().get("watching")
        assert toggled != initial_watching

        # Toggle back
        resp3 = requests.post(
            f"{BASE_URL}/api/auctions/{live_auction_id}/watch",
            headers=auth_headers,
        )
        assert resp3.status_code == 200
        assert resp3.json().get("watching") == initial_watching

    def test_my_watchlist_requires_auth(self):
        """GET /api/me/watchlist requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/me/watchlist")
        assert resp.status_code == 401

    def test_my_watchlist_authenticated(self, auth_headers):
        """GET /api/me/watchlist returns list of watched auctions"""
        resp = requests.get(f"{BASE_URL}/api/me/watchlist", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_my_listings_requires_auth(self):
        """GET /api/me/listings requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/me/listings")
        assert resp.status_code == 401

    def test_my_listings_authenticated(self, auth_headers):
        """GET /api/me/listings returns list of user's auctions"""
        resp = requests.get(f"{BASE_URL}/api/me/listings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Admin has listings, verify structure
        if data:
            item = data[0]
            assert "id" in item
            assert "title" in item
            assert "status" in item

    def test_my_bids_requires_auth(self):
        """GET /api/me/bids requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/me/bids")
        assert resp.status_code == 401

    def test_my_bids_authenticated(self, auth_headers):
        """GET /api/me/bids returns list of user's bids"""
        resp = requests.get(f"{BASE_URL}/api/me/bids", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestStripeHoldsRouter:
    """Tests for Stripe authorization endpoints (routers/stripe_holds.py)"""

    def test_my_credits_requires_auth(self):
        """GET /api/stripe/authorizations/my-credits requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/stripe/authorizations/my-credits")
        assert resp.status_code == 401

    def test_my_credits_authenticated(self, auth_headers):
        """GET /api/stripe/authorizations/my-credits returns rolled-up summary"""
        resp = requests.get(
            f"{BASE_URL}/api/stripe/authorizations/my-credits",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Validate response structure
        assert "holds" in data
        assert "total_available_eur" in data
        assert "total_limit_eur" in data
        assert "total_hold_eur" in data
        assert "count" in data
        assert isinstance(data["holds"], list)
        assert isinstance(data["count"], int)

    def test_release_nonexistent_auth(self, auth_headers):
        """POST /api/stripe/authorizations/{id}/release returns 404 for non-existent auth"""
        resp = requests.post(
            f"{BASE_URL}/api/stripe/authorizations/nonexistent-auth-id/release",
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert "не е намерена" in resp.json().get("detail", "").lower() or "not found" in resp.json().get("detail", "").lower()

    def test_release_requires_auth(self):
        """POST /api/stripe/authorizations/{id}/release requires authentication"""
        resp = requests.post(f"{BASE_URL}/api/stripe/authorizations/some-id/release")
        assert resp.status_code == 401

    def test_stripe_config(self):
        """GET /api/stripe/config returns Stripe configuration"""
        resp = requests.get(f"{BASE_URL}/api/stripe/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "configured" in data
        assert "mode" in data
        assert "hold_percent" in data


class TestAuctionsEndpoints:
    """Regression tests for core auction endpoints"""

    def test_auctions_list(self):
        """GET /api/auctions returns list of auctions"""
        resp = requests.get(f"{BASE_URL}/api/auctions", params={"limit": 5})
        assert resp.status_code == 200

    def test_auctions_featured(self):
        """GET /api/auctions/featured returns featured auctions"""
        resp = requests.get(f"{BASE_URL}/api/auctions/featured")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_auctions_facets(self):
        """GET /api/auctions/facets returns filter options"""
        resp = requests.get(f"{BASE_URL}/api/auctions/facets")
        assert resp.status_code == 200
        data = resp.json()
        assert "makes" in data
        assert "fuels" in data


class TestAuthEndpoints:
    """Regression tests for auth endpoints"""

    def test_login_success(self):
        """POST /api/auth/login with valid credentials returns token"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "user" in data

    def test_login_invalid_credentials(self):
        """POST /api/auth/login with invalid credentials returns 401"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@email.com", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_me_requires_auth(self):
        """GET /api/auth/me requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 401

    def test_me_authenticated(self, auth_headers):
        """GET /api/auth/me returns user info when authenticated"""
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "email" in data
        assert data["email"] == ADMIN_EMAIL


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
