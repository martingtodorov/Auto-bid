"""
Backend tests for autoandbid.com Negotiation Flow and Related Features
Tests:
- Admin settings (buyer_fee_pct, SEO, content fields)
- Variable bid steps and buyer fee calculation
- Direct bidding (BaT-style)
- Comments with is_owner flag and admin soft-delete
- Reserve_met visibility rules
- Full negotiation E2E flow (seller opening → buyer counter → seller final)
- Negotiation messaging
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "contact@autoandbid.com"
ADMIN_PASSWORD = "admin123"


# ============ FIXTURES ============

@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.text}")
    return response.json()["token"]


@pytest.fixture(scope="module")
def admin_user(admin_token):
    """Get admin user info"""
    response = requests.get(f"{BASE_URL}/api/auth/me",
                           headers={"Authorization": f"Bearer {admin_token}"})
    return response.json()


@pytest.fixture(scope="module")
def seller_data():
    """Create a seller user for testing"""
    email = f"TEST_seller_{uuid.uuid4().hex[:8]}@test.bg"
    response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "test123",
        "name": "Test Seller"
    })
    if response.status_code != 200:
        pytest.skip(f"Seller registration failed: {response.text}")
    data = response.json()
    return {"token": data["token"], "user": data["user"], "email": email}


@pytest.fixture(scope="module")
def buyer_data():
    """Create a buyer user for testing"""
    email = f"TEST_buyer_{uuid.uuid4().hex[:8]}@test.bg"
    response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "test123",
        "name": "Test Buyer"
    })
    if response.status_code != 200:
        pytest.skip(f"Buyer registration failed: {response.text}")
    data = response.json()
    return {"token": data["token"], "user": data["user"], "email": email}


# ============ SETTINGS TESTS ============

class TestSiteSettings:
    """Tests for GET /api/settings and PUT /api/admin/settings"""
    
    def test_get_public_settings(self):
        """Public settings endpoint returns expected fields"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify expected fields exist
        assert "buyer_fee_pct" in data
        assert "buyer_fee_min_eur" in data
        assert "buyer_fee_max_eur" in data
        assert "seo_title" in data
        assert "seo_description" in data
        assert "faq_content" in data
        assert "terms_content" in data
        assert "contacts_content" in data
        assert "fees_content" in data
        assert "how_it_works_content" in data
        
        # Verify default buyer_fee_pct is 2.0
        assert data["buyer_fee_pct"] == 2.0, f"Expected 2.0, got {data['buyer_fee_pct']}"
        print(f"✓ Public settings returned with buyer_fee_pct={data['buyer_fee_pct']}")
    
    def test_admin_get_settings(self, admin_token):
        """Admin can get full settings"""
        response = requests.get(f"{BASE_URL}/api/admin/settings",
                               headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        data = response.json()
        assert "buyer_fee_pct" in data
        print("✓ Admin GET settings successful")
    
    def test_admin_update_buyer_fee_pct(self, admin_token):
        """Admin can update buyer_fee_pct"""
        # Update to 3%
        response = requests.put(f"{BASE_URL}/api/admin/settings",
                               headers={"Authorization": f"Bearer {admin_token}"},
                               json={"buyer_fee_pct": 3.0})
        assert response.status_code == 200
        data = response.json()
        assert data["buyer_fee_pct"] == 3.0
        
        # Verify public endpoint reflects change
        public = requests.get(f"{BASE_URL}/api/settings").json()
        assert public["buyer_fee_pct"] == 3.0
        
        # Reset back to 2.0
        requests.put(f"{BASE_URL}/api/admin/settings",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"buyer_fee_pct": 2.0})
        print("✓ Admin updated buyer_fee_pct and reset to 2.0")
    
    def test_admin_update_content_fields(self, admin_token):
        """Admin can update content markdown fields"""
        test_content = f"## Test Content {uuid.uuid4().hex[:6]}"
        response = requests.put(f"{BASE_URL}/api/admin/settings",
                               headers={"Authorization": f"Bearer {admin_token}"},
                               json={"faq_content": test_content})
        assert response.status_code == 200
        
        # Verify
        public = requests.get(f"{BASE_URL}/api/settings").json()
        assert public["faq_content"] == test_content
        print("✓ Admin updated faq_content successfully")
    
    def test_admin_update_seo_fields(self, admin_token):
        """Admin can update SEO fields"""
        test_title = f"Test SEO Title {uuid.uuid4().hex[:6]}"
        response = requests.put(f"{BASE_URL}/api/admin/settings",
                               headers={"Authorization": f"Bearer {admin_token}"},
                               json={"seo_title": test_title, "seo_description": "Test description"})
        assert response.status_code == 200
        
        public = requests.get(f"{BASE_URL}/api/settings").json()
        assert public["seo_title"] == test_title
        print("✓ Admin updated SEO fields successfully")
    
    def test_admin_settings_validation(self, admin_token):
        """Invalid buyer_fee_pct should be rejected"""
        # Try setting fee > 25%
        response = requests.put(f"{BASE_URL}/api/admin/settings",
                               headers={"Authorization": f"Bearer {admin_token}"},
                               json={"buyer_fee_pct": 30.0})
        assert response.status_code == 400
        print("✓ Invalid buyer_fee_pct (30%) correctly rejected")
    
    def test_non_admin_cannot_update_settings(self, buyer_data):
        """Non-admin should get 403"""
        response = requests.put(f"{BASE_URL}/api/admin/settings",
                               headers={"Authorization": f"Bearer {buyer_data['token']}"},
                               json={"buyer_fee_pct": 5.0})
        assert response.status_code == 403
        print("✓ Non-admin correctly rejected from updating settings")


# ============ BID STEP AND BUYER FEE TESTS ============

class TestBidStepAndBuyerFee:
    """Tests for /api/auctions/{id}/next-bid endpoint"""
    
    @pytest.fixture
    def live_auction_id(self, admin_token):
        """Get a live auction for testing"""
        response = requests.get(f"{BASE_URL}/api/auctions", params={"status": "live"})
        if response.status_code != 200 or not response.json():
            pytest.skip("No live auctions available")
        return response.json()[0]["id"]
    
    def test_next_bid_returns_correct_fields(self, live_auction_id):
        """next-bid endpoint returns step and buyer_fee"""
        response = requests.get(f"{BASE_URL}/api/auctions/{live_auction_id}/next-bid")
        assert response.status_code == 200
        data = response.json()
        
        assert "current_bid_eur" in data
        assert "step_eur" in data
        assert "min_next_eur" in data
        assert "buyer_fee_eur" in data
        
        # Verify min_next = current + step
        assert data["min_next_eur"] == data["current_bid_eur"] + data["step_eur"]
        print(f"✓ next-bid: current={data['current_bid_eur']}, step={data['step_eur']}, min_next={data['min_next_eur']}, fee={data['buyer_fee_eur']}")
    
    def test_bid_step_at_10000(self, admin_token):
        """At €10,000+ the step should be €500"""
        # Find or create auction at ~10000
        auctions = requests.get(f"{BASE_URL}/api/auctions", params={"status": "live"}).json()
        for a in auctions:
            if 10000 <= a.get("current_bid_eur", 0) < 20000:
                response = requests.get(f"{BASE_URL}/api/auctions/{a['id']}/next-bid")
                data = response.json()
                assert data["step_eur"] == 500.0, f"Expected step=500 at €{data['current_bid_eur']}, got {data['step_eur']}"
                print(f"✓ Bid step at €{data['current_bid_eur']} is €500")
                return
        print("⚠ No auction in €10,000-€20,000 range to test step=500")
    
    def test_bid_step_at_5000_to_10000(self, admin_token):
        """At €5,000-€10,000 the step should be €250"""
        auctions = requests.get(f"{BASE_URL}/api/auctions", params={"status": "live"}).json()
        for a in auctions:
            if 5000 <= a.get("current_bid_eur", 0) < 10000:
                response = requests.get(f"{BASE_URL}/api/auctions/{a['id']}/next-bid")
                data = response.json()
                assert data["step_eur"] == 250.0, f"Expected step=250 at €{data['current_bid_eur']}, got {data['step_eur']}"
                print(f"✓ Bid step at €{data['current_bid_eur']} is €250")
                return
        print("⚠ No auction in €5,000-€10,000 range to test step=250")
    
    def test_buyer_fee_calculation(self, live_auction_id):
        """Buyer fee should be 2% of min_next with min €150 / max €4000"""
        response = requests.get(f"{BASE_URL}/api/auctions/{live_auction_id}/next-bid")
        data = response.json()
        
        min_next = data["min_next_eur"]
        expected_fee = round(min_next * 0.02, 2)
        if expected_fee < 150:
            expected_fee = 150.0
        if expected_fee > 4000:
            expected_fee = 4000.0
        
        assert data["buyer_fee_eur"] == expected_fee, f"Expected fee={expected_fee}, got {data['buyer_fee_eur']}"
        print(f"✓ Buyer fee for €{min_next} is €{data['buyer_fee_eur']} (2% with min/max)")


# ============ DIRECT BIDDING TESTS ============

class TestDirectBidding:
    """Tests for direct bidding (BaT-style)"""
    
    @pytest.fixture
    def bidding_auction(self, admin_token, seller_data):
        """Create a fresh auction for bidding tests"""
        # Create auction as seller
        response = requests.post(f"{BASE_URL}/api/auctions",
                                headers={"Authorization": f"Bearer {seller_data['token']}"},
                                json={
                                    "title": f"TEST_Bidding_Auction_{uuid.uuid4().hex[:6]}",
                                    "make": "TestMake",
                                    "model": "TestModel",
                                    "year": 2020,
                                    "mileage_km": 50000,
                                    "fuel": "Бензин",
                                    "transmission": "Автоматична",
                                    "body_type": "Седан",
                                    "power_hp": 200,
                                    "engine_cc": 2000,
                                    "color": "Черен",
                                    "region": "София",
                                    "city": "София",
                                    "description": "Test auction for bidding",
                                    "images": ["https://example.com/img1.jpg"],
                                    "starting_bid_eur": 5000.0,
                                    "reserve_eur": 50000.0,  # High reserve for negotiation test
                                    "duration_days": 10,
                                    "contact_email": seller_data["email"],
                                    "contact_phone": "+359888123456"
                                })
        if response.status_code != 200:
            pytest.skip(f"Failed to create auction: {response.text}")
        
        auction_id = response.json()["id"]
        
        # Admin approves
        requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/approve",
                     headers={"Authorization": f"Bearer {admin_token}"})
        
        return auction_id
    
    def test_bid_below_min_next_rejected(self, bidding_auction, buyer_data):
        """Bid below min_next should return 400"""
        # Get min_next
        next_bid = requests.get(f"{BASE_URL}/api/auctions/{bidding_auction}/next-bid").json()
        
        # Try to bid below min_next
        response = requests.post(f"{BASE_URL}/api/auctions/{bidding_auction}/bids",
                                headers={"Authorization": f"Bearer {buyer_data['token']}"},
                                json={"amount_eur": next_bid["min_next_eur"] - 1, "payment_method_id": "pm_test_1234"})
        assert response.status_code == 400
        print(f"✓ Bid below min_next (€{next_bid['min_next_eur'] - 1}) correctly rejected")
    
    def test_direct_bid_becomes_current_immediately(self, bidding_auction, buyer_data):
        """Bid at min_next becomes current_bid immediately (not proxy)"""
        # Get min_next
        next_bid = requests.get(f"{BASE_URL}/api/auctions/{bidding_auction}/next-bid").json()
        bid_amount = next_bid["min_next_eur"]
        
        # Place bid
        response = requests.post(f"{BASE_URL}/api/auctions/{bidding_auction}/bids",
                                headers={"Authorization": f"Bearer {buyer_data['token']}"},
                                json={"amount_eur": bid_amount, "payment_method_id": "pm_test_1234"})
        assert response.status_code == 200, f"Bid failed: {response.text}"
        
        # Verify auction current_bid updated immediately
        auction = requests.get(f"{BASE_URL}/api/auctions/{bidding_auction}").json()
        assert auction["current_bid_eur"] == bid_amount, f"Expected current_bid={bid_amount}, got {auction['current_bid_eur']}"
        print(f"✓ Direct bid €{bid_amount} became current_bid immediately")
    
    def test_seller_cannot_bid_own_auction(self, bidding_auction, seller_data):
        """Seller cannot bid on their own auction"""
        next_bid = requests.get(f"{BASE_URL}/api/auctions/{bidding_auction}/next-bid").json()
        
        response = requests.post(f"{BASE_URL}/api/auctions/{bidding_auction}/bids",
                                headers={"Authorization": f"Bearer {seller_data['token']}"},
                                json={"amount_eur": next_bid["min_next_eur"], "payment_method_id": "pm_test_1234"})
        assert response.status_code == 400
        print("✓ Seller correctly prevented from bidding on own auction")


# ============ COMMENTS TESTS ============

class TestComments:
    """Tests for comments with is_owner flag and admin delete"""
    
    @pytest.fixture
    def auction_with_comments(self, admin_token, seller_data, buyer_data):
        """Get an auction and add comments from seller and buyer"""
        # Get a live auction
        auctions = requests.get(f"{BASE_URL}/api/auctions", params={"status": "live"}).json()
        if not auctions:
            pytest.skip("No live auctions")
        
        # Find one owned by seller or use first one
        auction_id = auctions[0]["id"]
        auction = requests.get(f"{BASE_URL}/api/auctions/{auction_id}").json()
        
        return {"auction_id": auction_id, "seller_id": auction.get("seller_id")}
    
    def test_seller_comment_has_is_owner_true(self, auction_with_comments, seller_data, admin_token):
        """Seller's comment should have is_owner=true"""
        # Create auction as seller
        response = requests.post(f"{BASE_URL}/api/auctions",
                                headers={"Authorization": f"Bearer {seller_data['token']}"},
                                json={
                                    "title": f"TEST_Comment_Auction_{uuid.uuid4().hex[:6]}",
                                    "make": "TestMake", "model": "TestModel", "year": 2020,
                                    "mileage_km": 50000, "fuel": "Бензин", "transmission": "Автоматична",
                                    "body_type": "Седан", "power_hp": 200, "engine_cc": 2000,
                                    "color": "Черен", "region": "София", "city": "София",
                                    "description": "Test", "images": ["https://example.com/img.jpg"],
                                    "starting_bid_eur": 5000.0, "duration_days": 10,
                                    "contact_email": seller_data["email"], "contact_phone": "+359888123456"
                                })
        auction_id = response.json()["id"]
        
        # Admin approves
        requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/approve",
                     headers={"Authorization": f"Bearer {admin_token}"})
        
        # Seller adds comment
        comment_resp = requests.post(f"{BASE_URL}/api/auctions/{auction_id}/comments",
                                    headers={"Authorization": f"Bearer {seller_data['token']}"},
                                    json={"text": "This is the seller's comment"})
        assert comment_resp.status_code == 200
        comment = comment_resp.json()
        assert comment["is_owner"] == True, f"Expected is_owner=True for seller comment"
        print("✓ Seller comment has is_owner=true")
    
    def test_buyer_comment_has_is_owner_false(self, buyer_data):
        """Non-seller's comment should have is_owner=false"""
        # Get any auction
        auctions = requests.get(f"{BASE_URL}/api/auctions", params={"status": "live"}).json()
        if not auctions:
            pytest.skip("No live auctions")
        auction_id = auctions[0]["id"]
        
        # Buyer adds comment
        comment_resp = requests.post(f"{BASE_URL}/api/auctions/{auction_id}/comments",
                                    headers={"Authorization": f"Bearer {buyer_data['token']}"},
                                    json={"text": f"Buyer comment {uuid.uuid4().hex[:6]}"})
        assert comment_resp.status_code == 200
        comment = comment_resp.json()
        assert comment["is_owner"] == False, f"Expected is_owner=False for buyer comment"
        print("✓ Buyer comment has is_owner=false")
    
    def test_admin_soft_delete_comment(self, admin_token, buyer_data):
        """Admin can soft-delete a comment, text replaced with moderation notice"""
        # Get auction and add a comment
        auctions = requests.get(f"{BASE_URL}/api/auctions", params={"status": "live"}).json()
        if not auctions:
            pytest.skip("No live auctions")
        auction_id = auctions[0]["id"]
        
        # Add comment
        comment_resp = requests.post(f"{BASE_URL}/api/auctions/{auction_id}/comments",
                                    headers={"Authorization": f"Bearer {buyer_data['token']}"},
                                    json={"text": f"Comment to delete {uuid.uuid4().hex[:6]}"})
        comment_id = comment_resp.json()["id"]
        
        # Admin deletes
        delete_resp = requests.delete(f"{BASE_URL}/api/admin/comments/{comment_id}",
                                     headers={"Authorization": f"Bearer {admin_token}"})
        assert delete_resp.status_code == 200
        
        # Verify comment text is replaced
        comments = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/comments").json()
        deleted_comment = next((c for c in comments if c["id"] == comment_id), None)
        assert deleted_comment is not None
        assert deleted_comment["deleted"] == True
        assert "премахнат" in deleted_comment["text"].lower() or "moderation" in deleted_comment["text"].lower()
        print(f"✓ Admin soft-deleted comment, text replaced with: '{deleted_comment['text'][:50]}...'")


# ============ RESERVE_MET VISIBILITY TESTS ============

class TestReserveMetVisibility:
    """Tests for reserve_met visibility rules"""
    
    def test_live_auction_hides_reserve_met(self):
        """Live auction should NOT expose reserve_met to public"""
        auctions = requests.get(f"{BASE_URL}/api/auctions", params={"status": "live"}).json()
        for a in auctions:
            if a.get("has_reserve"):
                # reserve_met should be None for live auctions
                assert a.get("reserve_met") is None, f"Live auction {a['id']} should not expose reserve_met"
                print(f"✓ Live auction {a['id'][:8]}... correctly hides reserve_met")
                return
        print("⚠ No live auctions with reserve to test")
    
    def test_ended_auction_shows_reserve_met(self):
        """Ended/sold/reserve_not_met auctions should expose reserve_met"""
        for status in ["ended", "sold", "reserve_not_met"]:
            auctions = requests.get(f"{BASE_URL}/api/auctions", params={"status": status}).json()
            for a in auctions:
                if a.get("has_reserve"):
                    # reserve_met should be boolean (True or False), not None
                    assert a.get("reserve_met") is not None, f"{status} auction {a['id']} should expose reserve_met"
                    print(f"✓ {status.upper()} auction {a['id'][:8]}... correctly shows reserve_met={a['reserve_met']}")
                    break


# ============ NEGOTIATION E2E FLOW TESTS ============

class TestNegotiationE2EFlow:
    """Full E2E test of post-auction negotiation flow"""
    
    @pytest.fixture
    def negotiation_setup(self, admin_token, seller_data, buyer_data):
        """Create auction, have buyer bid, force to reserve_not_met"""
        # 1. Create auction with high reserve
        response = requests.post(f"{BASE_URL}/api/auctions",
                                headers={"Authorization": f"Bearer {seller_data['token']}"},
                                json={
                                    "title": f"TEST_Negotiation_{uuid.uuid4().hex[:6]}",
                                    "make": "TestMake", "model": "TestModel", "year": 2020,
                                    "mileage_km": 50000, "fuel": "Бензин", "transmission": "Автоматична",
                                    "body_type": "Седан", "power_hp": 200, "engine_cc": 2000,
                                    "color": "Черен", "region": "София", "city": "София",
                                    "description": "Test auction for negotiation",
                                    "images": ["https://example.com/img1.jpg"],
                                    "starting_bid_eur": 5000.0,
                                    "reserve_eur": 50000.0,  # Very high reserve
                                    "duration_days": 10,
                                    "contact_email": seller_data["email"],
                                    "contact_phone": "+359888123456"
                                })
        if response.status_code != 200:
            pytest.skip(f"Failed to create auction: {response.text}")
        
        auction_id = response.json()["id"]
        
        # 2. Admin approves
        requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/approve",
                     headers={"Authorization": f"Bearer {admin_token}"})
        
        # 3. Buyer places a bid
        next_bid = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/next-bid").json()
        bid_resp = requests.post(f"{BASE_URL}/api/auctions/{auction_id}/bids",
                                headers={"Authorization": f"Bearer {buyer_data['token']}"},
                                json={"amount_eur": next_bid["min_next_eur"], "payment_method_id": "pm_test_1234"})
        if bid_resp.status_code != 200:
            pytest.skip(f"Failed to place bid: {bid_resp.text}")
        
        # 4. Admin forces auction to reserve_not_met by setting ends_at to past
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        requests.put(f"{BASE_URL}/api/admin/auctions/{auction_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"ends_at": past_time})
        
        # Verify status is now reserve_not_met
        auction = requests.get(f"{BASE_URL}/api/auctions/{auction_id}").json()
        assert auction["status"] == "reserve_not_met", f"Expected reserve_not_met, got {auction['status']}"
        
        return {
            "auction_id": auction_id,
            "seller_token": seller_data["token"],
            "buyer_token": buyer_data["token"],
            "admin_token": admin_token
        }
    
    def test_negotiation_auto_creates_on_get(self, negotiation_setup):
        """GET /negotiation auto-creates negotiation for reserve_not_met auction"""
        auction_id = negotiation_setup["auction_id"]
        seller_token = negotiation_setup["seller_token"]
        
        response = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                               headers={"Authorization": f"Bearer {seller_token}"})
        assert response.status_code == 200, f"Failed: {response.text}"
        
        neg = response.json()
        assert neg["status"] == "awaiting_seller_opening"
        assert neg["auction_id"] == auction_id
        assert "deadline_at" in neg
        assert "seconds_left" in neg
        print(f"✓ Negotiation auto-created with status=awaiting_seller_opening")
    
    def test_seller_opening_offer(self, negotiation_setup):
        """Seller can submit opening offer"""
        auction_id = negotiation_setup["auction_id"]
        seller_token = negotiation_setup["seller_token"]
        
        # First ensure negotiation exists
        requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                    headers={"Authorization": f"Bearer {seller_token}"})
        
        # Seller submits opening offer
        response = requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/opening",
                                headers={"Authorization": f"Bearer {seller_token}"},
                                json={"price_eur": 20000})
        assert response.status_code == 200, f"Failed: {response.text}"
        
        neg = response.json()
        assert neg["status"] == "awaiting_buyer_response"
        assert neg["seller_offer_eur"] == 20000
        print(f"✓ Seller opening offer €20,000 accepted, status=awaiting_buyer_response")
    
    def test_buyer_counter_offer(self, negotiation_setup):
        """Buyer can submit counter offer"""
        auction_id = negotiation_setup["auction_id"]
        seller_token = negotiation_setup["seller_token"]
        buyer_token = negotiation_setup["buyer_token"]
        
        # Ensure negotiation is in awaiting_buyer_response state
        neg = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                          headers={"Authorization": f"Bearer {seller_token}"}).json()
        
        if neg["status"] == "awaiting_seller_opening":
            # Submit seller opening first
            requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/opening",
                         headers={"Authorization": f"Bearer {seller_token}"},
                         json={"price_eur": 20000})
        
        # Buyer submits counter
        response = requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/response",
                                headers={"Authorization": f"Bearer {buyer_token}"},
                                json={"action": "counter", "price_eur": 18000})
        assert response.status_code == 200, f"Failed: {response.text}"
        
        neg = response.json()
        assert neg["status"] == "awaiting_seller_final"
        assert neg["buyer_counter_eur"] == 18000
        print(f"✓ Buyer counter €18,000 accepted, status=awaiting_seller_final")
    
    def test_seller_final_accept(self, negotiation_setup):
        """Seller can accept buyer's counter, completing the deal"""
        auction_id = negotiation_setup["auction_id"]
        seller_token = negotiation_setup["seller_token"]
        buyer_token = negotiation_setup["buyer_token"]
        
        # Ensure negotiation is in awaiting_seller_final state
        neg = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                          headers={"Authorization": f"Bearer {seller_token}"}).json()
        
        if neg["status"] == "awaiting_seller_opening":
            requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/opening",
                         headers={"Authorization": f"Bearer {seller_token}"},
                         json={"price_eur": 20000})
        
        neg = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                          headers={"Authorization": f"Bearer {seller_token}"}).json()
        
        if neg["status"] == "awaiting_buyer_response":
            requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/response",
                         headers={"Authorization": f"Bearer {buyer_token}"},
                         json={"action": "counter", "price_eur": 18000})
        
        # Seller accepts
        response = requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/final",
                                headers={"Authorization": f"Bearer {seller_token}"},
                                json={"action": "accept"})
        assert response.status_code == 200, f"Failed: {response.text}"
        
        neg = response.json()
        assert neg["status"] == "accepted"
        assert neg["final_price_eur"] == 18000
        assert "buyer_fee_eur" in neg
        
        # Verify auction is now sold
        auction = requests.get(f"{BASE_URL}/api/auctions/{auction_id}").json()
        assert auction["status"] == "sold"
        assert auction["current_bid_eur"] == 18000
        assert "premium_amount_eur" in auction
        
        print(f"✓ Negotiation completed: final_price=€18,000, buyer_fee=€{neg['buyer_fee_eur']}, auction status=sold")


# ============ NEGOTIATION MESSAGING TESTS ============

class TestNegotiationMessaging:
    """Tests for negotiation messaging"""
    
    @pytest.fixture
    def active_negotiation(self, admin_token, seller_data, buyer_data):
        """Create an active negotiation for messaging tests"""
        # Create auction
        response = requests.post(f"{BASE_URL}/api/auctions",
                                headers={"Authorization": f"Bearer {seller_data['token']}"},
                                json={
                                    "title": f"TEST_Messaging_{uuid.uuid4().hex[:6]}",
                                    "make": "TestMake", "model": "TestModel", "year": 2020,
                                    "mileage_km": 50000, "fuel": "Бензин", "transmission": "Автоматична",
                                    "body_type": "Седан", "power_hp": 200, "engine_cc": 2000,
                                    "color": "Черен", "region": "София", "city": "София",
                                    "description": "Test", "images": ["https://example.com/img.jpg"],
                                    "starting_bid_eur": 5000.0, "reserve_eur": 50000.0,
                                    "duration_days": 10, "contact_email": seller_data["email"],
                                    "contact_phone": "+359888123456"
                                })
        auction_id = response.json()["id"]
        
        # Admin approves
        requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/approve",
                     headers={"Authorization": f"Bearer {admin_token}"})
        
        # Buyer bids
        next_bid = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/next-bid").json()
        requests.post(f"{BASE_URL}/api/auctions/{auction_id}/bids",
                     headers={"Authorization": f"Bearer {buyer_data['token']}"},
                     json={"amount_eur": next_bid["min_next_eur"], "payment_method_id": "pm_test_1234"})
        
        # Force to reserve_not_met
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        requests.put(f"{BASE_URL}/api/admin/auctions/{auction_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"ends_at": past_time})
        
        # Initialize negotiation
        requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                    headers={"Authorization": f"Bearer {seller_data['token']}"})
        
        return {
            "auction_id": auction_id,
            "seller_token": seller_data["token"],
            "buyer_token": buyer_data["token"]
        }
    
    def test_send_message(self, active_negotiation):
        """Can send message in negotiation"""
        auction_id = active_negotiation["auction_id"]
        seller_token = active_negotiation["seller_token"]
        
        response = requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/messages",
                                headers={"Authorization": f"Bearer {seller_token}"},
                                json={"text": "Hello, this is a test message"})
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["ok"] == True
        assert "message" in data
        assert data["message"]["text"] == "Hello, this is a test message"
        assert data["message"]["role"] == "seller"
        print(f"✓ Message sent successfully with role=seller")
    
    def test_messages_appear_in_negotiation(self, active_negotiation):
        """Messages appear in negotiation GET response"""
        auction_id = active_negotiation["auction_id"]
        seller_token = active_negotiation["seller_token"]
        buyer_token = active_negotiation["buyer_token"]
        
        # Send messages from both parties
        requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/messages",
                     headers={"Authorization": f"Bearer {seller_token}"},
                     json={"text": "Seller message"})
        
        requests.post(f"{BASE_URL}/api/auctions/{auction_id}/negotiation/messages",
                     headers={"Authorization": f"Bearer {buyer_token}"},
                     json={"text": "Buyer message"})
        
        # Get negotiation
        neg = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                          headers={"Authorization": f"Bearer {seller_token}"}).json()
        
        assert "messages" in neg
        assert len(neg["messages"]) >= 2
        
        # Verify message structure
        for msg in neg["messages"]:
            assert "id" in msg
            assert "user_id" in msg
            assert "user_name" in msg
            assert "role" in msg
            assert "text" in msg
            assert "created_at" in msg
        
        print(f"✓ Messages array contains {len(neg['messages'])} messages with correct structure")


# ============ NEGOTIATION AUTHORIZATION TESTS ============

class TestNegotiationAuthorization:
    """Tests for negotiation endpoint authorization"""
    
    def test_unauthorized_user_cannot_access_negotiation(self, admin_token, seller_data, buyer_data):
        """User who is not seller/buyer/admin cannot access negotiation"""
        # Create a third user
        third_user_email = f"TEST_third_{uuid.uuid4().hex[:8]}@test.bg"
        third_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": third_user_email,
            "password": "test123",
            "name": "Third User"
        })
        third_token = third_resp.json()["token"]
        
        # Create auction and negotiation
        response = requests.post(f"{BASE_URL}/api/auctions",
                                headers={"Authorization": f"Bearer {seller_data['token']}"},
                                json={
                                    "title": f"TEST_Auth_{uuid.uuid4().hex[:6]}",
                                    "make": "TestMake", "model": "TestModel", "year": 2020,
                                    "mileage_km": 50000, "fuel": "Бензин", "transmission": "Автоматична",
                                    "body_type": "Седан", "power_hp": 200, "engine_cc": 2000,
                                    "color": "Черен", "region": "София", "city": "София",
                                    "description": "Test", "images": ["https://example.com/img.jpg"],
                                    "starting_bid_eur": 5000.0, "reserve_eur": 50000.0,
                                    "duration_days": 10, "contact_email": seller_data["email"],
                                    "contact_phone": "+359888123456"
                                })
        auction_id = response.json()["id"]
        
        # Admin approves
        requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/approve",
                     headers={"Authorization": f"Bearer {admin_token}"})
        
        # Buyer bids
        next_bid = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/next-bid").json()
        requests.post(f"{BASE_URL}/api/auctions/{auction_id}/bids",
                     headers={"Authorization": f"Bearer {buyer_data['token']}"},
                     json={"amount_eur": next_bid["min_next_eur"], "payment_method_id": "pm_test_1234"})
        
        # Force to reserve_not_met
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        requests.put(f"{BASE_URL}/api/admin/auctions/{auction_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"ends_at": past_time})
        
        # Initialize negotiation as seller
        requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                    headers={"Authorization": f"Bearer {seller_data['token']}"})
        
        # Third user tries to access
        response = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                               headers={"Authorization": f"Bearer {third_token}"})
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Unauthorized user correctly rejected from negotiation")
    
    def test_admin_can_access_any_negotiation(self, admin_token, seller_data, buyer_data):
        """Admin can access any negotiation"""
        # Create auction and negotiation
        response = requests.post(f"{BASE_URL}/api/auctions",
                                headers={"Authorization": f"Bearer {seller_data['token']}"},
                                json={
                                    "title": f"TEST_AdminAccess_{uuid.uuid4().hex[:6]}",
                                    "make": "TestMake", "model": "TestModel", "year": 2020,
                                    "mileage_km": 50000, "fuel": "Бензин", "transmission": "Автоматична",
                                    "body_type": "Седан", "power_hp": 200, "engine_cc": 2000,
                                    "color": "Черен", "region": "София", "city": "София",
                                    "description": "Test", "images": ["https://example.com/img.jpg"],
                                    "starting_bid_eur": 5000.0, "reserve_eur": 50000.0,
                                    "duration_days": 10, "contact_email": seller_data["email"],
                                    "contact_phone": "+359888123456"
                                })
        auction_id = response.json()["id"]
        
        # Admin approves
        requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/approve",
                     headers={"Authorization": f"Bearer {admin_token}"})
        
        # Buyer bids
        next_bid = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/next-bid").json()
        requests.post(f"{BASE_URL}/api/auctions/{auction_id}/bids",
                     headers={"Authorization": f"Bearer {buyer_data['token']}"},
                     json={"amount_eur": next_bid["min_next_eur"], "payment_method_id": "pm_test_1234"})
        
        # Force to reserve_not_met
        past_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        requests.put(f"{BASE_URL}/api/admin/auctions/{auction_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"ends_at": past_time})
        
        # Admin accesses negotiation
        response = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/negotiation",
                               headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200, f"Admin should access negotiation, got {response.status_code}"
        print("✓ Admin can access any negotiation")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
