"""
Test suite for Buyer → Seller Review/Rating system (P2 roadmap item).

Tests cover:
- POST /api/users/{seller_id}/reviews — only winning buyer of sold auction may post
- GET /api/users/{seller_id}/reviews — returns items + rating aggregate
- GET /api/users/{seller_id}/rating — returns avg + count
- GET /api/users/{seller_id}/reviews/eligible/{auction_id} — eligibility check
- GET /api/me/reviewable — lists sold auctions user won minus already reviewed
- GET /api/users/{user_id}/profile — now contains rating field
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data
ADMIN_EMAIL = "admin@autobids.bg"
ADMIN_PASSWORD = "admin123"
ADMIN_ID = "2cf85891-68fd-4c9e-8f79-87e704ba6314"
SOLD_AUCTION_ID = "c049f61a-7c0b-4cf5-994f-387776bb2403"

# Existing review buyer (already posted review for the sold auction)
EXISTING_REVIEW_BUYER_EMAIL = "reviewbuyer@test.bg"
EXISTING_REVIEW_BUYER_PASSWORD = "test12345"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def admin_client(api_client, admin_token):
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    })
    return session


@pytest.fixture(scope="module")
def new_test_user(api_client):
    """Create a brand new test user for testing duplicate prevention / not-buyer cases"""
    unique_id = uuid.uuid4().hex[:8]
    email = f"TEST_review_user_{unique_id}@test.bg"
    password = "test12345"
    name = f"Test Review User {unique_id}"
    
    response = api_client.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": password,
        "name": name
    })
    assert response.status_code == 200, f"User registration failed: {response.text}"
    data = response.json()
    return {
        "id": data["user"]["id"],
        "email": email,
        "password": password,
        "name": name,
        "token": data["token"]
    }


@pytest.fixture(scope="module")
def new_user_client(api_client, new_test_user):
    """Session with new test user auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {new_test_user['token']}"
    })
    return session


class TestReviewEndpoints:
    """Test review CRUD and eligibility endpoints"""
    
    def test_get_seller_reviews_returns_items_and_rating(self, api_client):
        """GET /api/users/{seller_id}/reviews returns items array and rating aggregate"""
        response = api_client.get(f"{BASE_URL}/api/users/{ADMIN_ID}/reviews")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "items" in data, "Response should have 'items' field"
        assert "rating" in data, "Response should have 'rating' field"
        assert isinstance(data["items"], list), "items should be a list"
        assert "avg" in data["rating"], "rating should have 'avg'"
        assert "count" in data["rating"], "rating should have 'count'"
        
        print(f"✓ GET /users/{ADMIN_ID}/reviews: {len(data['items'])} reviews, avg={data['rating']['avg']}, count={data['rating']['count']}")
    
    def test_get_seller_rating_returns_aggregate(self, api_client):
        """GET /api/users/{seller_id}/rating returns avg and count"""
        response = api_client.get(f"{BASE_URL}/api/users/{ADMIN_ID}/rating")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "avg" in data, "Response should have 'avg'"
        assert "count" in data, "Response should have 'count'"
        assert isinstance(data["avg"], (int, float)), "avg should be numeric"
        assert isinstance(data["count"], int), "count should be integer"
        
        print(f"✓ GET /users/{ADMIN_ID}/rating: avg={data['avg']}, count={data['count']}")
    
    def test_profile_contains_rating_field(self, api_client):
        """GET /api/users/{user_id}/profile now contains rating field"""
        response = api_client.get(f"{BASE_URL}/api/users/{ADMIN_ID}/profile")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "rating" in data, "Profile should have 'rating' field"
        assert "avg" in data["rating"], "rating should have 'avg'"
        assert "count" in data["rating"], "rating should have 'count'"
        
        print(f"✓ GET /users/{ADMIN_ID}/profile contains rating: avg={data['rating']['avg']}, count={data['rating']['count']}")


class TestReviewEligibility:
    """Test eligibility endpoint for various scenarios"""
    
    def test_eligibility_not_buyer_returns_false(self, new_user_client, new_test_user):
        """User who is not the buyer of the auction should get eligible=false, reason=not_buyer"""
        response = new_user_client.get(f"{BASE_URL}/api/users/{ADMIN_ID}/reviews/eligible/{SOLD_AUCTION_ID}")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["eligible"] == False, "Should not be eligible"
        assert data["reason"] == "not_buyer", f"Reason should be 'not_buyer', got '{data.get('reason')}'"
        
        print(f"✓ Eligibility check for non-buyer: eligible=False, reason=not_buyer")
    
    def test_eligibility_auction_not_found(self, new_user_client):
        """Non-existent auction should return eligible=false, reason=auction_not_found"""
        fake_auction_id = str(uuid.uuid4())
        response = new_user_client.get(f"{BASE_URL}/api/users/{ADMIN_ID}/reviews/eligible/{fake_auction_id}")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["eligible"] == False, "Should not be eligible"
        assert data["reason"] == "auction_not_found", f"Reason should be 'auction_not_found', got '{data.get('reason')}'"
        
        print(f"✓ Eligibility check for non-existent auction: eligible=False, reason=auction_not_found")
    
    def test_eligibility_seller_mismatch(self, new_user_client, new_test_user):
        """Wrong seller_id should return eligible=false, reason=seller_mismatch"""
        wrong_seller_id = new_test_user["id"]  # Use the new user as wrong seller
        response = new_user_client.get(f"{BASE_URL}/api/users/{wrong_seller_id}/reviews/eligible/{SOLD_AUCTION_ID}")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["eligible"] == False, "Should not be eligible"
        assert data["reason"] == "seller_mismatch", f"Reason should be 'seller_mismatch', got '{data.get('reason')}'"
        
        print(f"✓ Eligibility check for wrong seller: eligible=False, reason=seller_mismatch")


class TestReviewCreationValidation:
    """Test review creation validation rules"""
    
    def test_seller_cannot_self_review(self, admin_client):
        """Seller trying to review themselves should get 400"""
        response = admin_client.post(f"{BASE_URL}/api/users/{ADMIN_ID}/reviews", json={
            "auction_id": SOLD_AUCTION_ID,
            "rating": 5,
            "text": "This is a self-review attempt"
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "собствения си профил" in data.get("detail", "").lower() or "не можете" in data.get("detail", "").lower(), \
            f"Error message should mention self-review: {data.get('detail')}"
        
        print(f"✓ Self-review blocked with 400: {data.get('detail')}")
    
    def test_non_buyer_cannot_review(self, new_user_client):
        """User who is not the buyer cannot post review"""
        response = new_user_client.post(f"{BASE_URL}/api/users/{ADMIN_ID}/reviews", json={
            "auction_id": SOLD_AUCTION_ID,
            "rating": 5,
            "text": "This is a review from non-buyer"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert "купувач" in data.get("detail", "").lower(), \
            f"Error message should mention buyer: {data.get('detail')}"
        
        print(f"✓ Non-buyer review blocked with 403: {data.get('detail')}")
    
    def test_review_for_nonexistent_auction(self, new_user_client):
        """Review for non-existent auction should return 404"""
        fake_auction_id = str(uuid.uuid4())
        response = new_user_client.post(f"{BASE_URL}/api/users/{ADMIN_ID}/reviews", json={
            "auction_id": fake_auction_id,
            "rating": 5,
            "text": "Review for fake auction"
        })
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        
        print(f"✓ Review for non-existent auction blocked with 404")


class TestReviewablePurchases:
    """Test /me/reviewable endpoint"""
    
    def test_reviewable_requires_auth(self, api_client):
        """GET /api/me/reviewable requires authentication"""
        response = api_client.get(f"{BASE_URL}/api/me/reviewable")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
        print(f"✓ /me/reviewable requires auth (401)")
    
    def test_reviewable_returns_items_list(self, admin_client):
        """GET /api/me/reviewable returns items list"""
        response = admin_client.get(f"{BASE_URL}/api/me/reviewable")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "items" in data, "Response should have 'items' field"
        assert isinstance(data["items"], list), "items should be a list"
        
        print(f"✓ /me/reviewable returns {len(data['items'])} reviewable purchases")


class TestLiveAuctionReviewBlock:
    """Test that reviews cannot be posted for non-sold auctions"""
    
    def test_review_for_live_auction_blocked(self, api_client, admin_client):
        """Review for live auction should return 400"""
        # First get a live auction
        response = api_client.get(f"{BASE_URL}/api/auctions?status=live&limit=1")
        assert response.status_code == 200
        auctions = response.json()
        
        if not auctions:
            pytest.skip("No live auctions available for testing")
        
        live_auction = auctions[0]
        seller_id = live_auction.get("seller_id")
        auction_id = live_auction.get("id")
        
        if not seller_id or not auction_id:
            pytest.skip("Live auction missing seller_id or id")
        
        # Try to post review for live auction (will fail because user is not buyer anyway)
        response = admin_client.post(f"{BASE_URL}/api/users/{seller_id}/reviews", json={
            "auction_id": auction_id,
            "rating": 5,
            "text": "Review for live auction"
        })
        # Should fail with 400 (not sold) or 403 (not buyer) or 400 (self-review if admin is seller)
        assert response.status_code in [400, 403], f"Expected 400 or 403, got {response.status_code}: {response.text}"
        
        print(f"✓ Review for live auction blocked with {response.status_code}")


class TestRegressionAuth:
    """Regression tests for existing auth endpoints"""
    
    def test_login_works(self, api_client):
        """POST /api/auth/login still works"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Response should have token"
        assert "user" in data, "Response should have user"
        
        print(f"✓ Login works: admin@autobids.bg")
    
    def test_me_endpoint_works(self, admin_client):
        """GET /api/auth/me still works"""
        response = admin_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("email") == ADMIN_EMAIL
        
        print(f"✓ /auth/me works")


class TestRegressionAuctions:
    """Regression tests for existing auction endpoints"""
    
    def test_auctions_list_works(self, api_client):
        """GET /api/auctions still works"""
        response = api_client.get(f"{BASE_URL}/api/auctions")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Should return list"
        
        print(f"✓ /auctions list works: {len(data)} auctions")
    
    def test_auction_detail_works(self, api_client):
        """GET /api/auctions/{id} still works"""
        # Get first auction
        response = api_client.get(f"{BASE_URL}/api/auctions?limit=1")
        assert response.status_code == 200
        auctions = response.json()
        
        if not auctions:
            pytest.skip("No auctions available")
        
        auction_id = auctions[0]["id"]
        response = api_client.get(f"{BASE_URL}/api/auctions/{auction_id}")
        assert response.status_code == 200, f"Failed: {response.text}"
        
        print(f"✓ /auctions/{auction_id} detail works")
    
    def test_sold_auction_detail_works(self, api_client):
        """GET /api/auctions/{sold_id} works for sold auction"""
        response = api_client.get(f"{BASE_URL}/api/auctions/{SOLD_AUCTION_ID}")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data.get("status") == "sold", f"Expected sold status, got {data.get('status')}"
        
        print(f"✓ Sold auction detail works: status={data.get('status')}")


class TestRegressionProfile:
    """Regression tests for profile endpoint"""
    
    def test_profile_endpoint_works(self, api_client):
        """GET /api/users/{id}/profile still works"""
        response = api_client.get(f"{BASE_URL}/api/users/{ADMIN_ID}/profile")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify expected fields
        assert "user" in data, "Should have user field"
        assert "stats" in data, "Should have stats field"
        assert "listings_sold" in data, "Should have listings_sold field"
        assert "purchases" in data, "Should have purchases field"
        assert "active_listings" in data, "Should have active_listings field"
        
        print(f"✓ Profile endpoint works for admin user")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
