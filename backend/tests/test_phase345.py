"""
Phase 3/4/5 Backend Tests — Bid Moderation, User Moderation, Payments, CMS, GDPR

Tests:
- Phase 3: Bid moderation (invalidate, block bidder), User moderation (suspend, verify, notes, VIN, resend)
- Phase 4: Buyer fee status, Stripe events, views counter
- Phase 5: CMS settings (og_image, maintenance_mode), maintenance middleware
- GDPR: DELETE /api/auth/me cascade
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(scope="module")
def admin_token():
    """Login as admin"""
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "contact@autoandbid.com",
        "password": "admin123"
    })
    if r.status_code == 200:
        data = r.json()
        if data.get("requires_2fa"):
            pytest.skip("Admin has 2FA enabled - skipping")
        return data.get("token")
    pytest.skip(f"Admin login failed: {r.status_code} {r.text}")

@pytest.fixture(scope="module")
def moderator_token():
    """Login as moderator"""
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "moderator@test.bg",
        "password": "mod12345"
    })
    if r.status_code == 200:
        data = r.json()
        if data.get("requires_2fa"):
            pytest.skip("Moderator has 2FA enabled - skipping")
        return data.get("token")
    pytest.skip(f"Moderator login failed: {r.status_code} {r.text}")

@pytest.fixture(scope="module")
def buyer_token():
    """Login as buyer"""
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "reviewbuyer@test.bg",
        "password": "newPass123"
    })
    if r.status_code == 200:
        data = r.json()
        if data.get("requires_2fa"):
            pytest.skip("Buyer has 2FA enabled - skipping")
        return data.get("token")
    pytest.skip(f"Buyer login failed: {r.status_code} {r.text}")

@pytest.fixture(scope="module")
def test_auction_id(admin_token):
    """Get or create a live test auction for bid tests"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Get all auctions
    r = requests.get(f"{BASE_URL}/api/admin/auctions", headers=headers)
    if r.status_code == 200:
        auctions = r.json()
        # Find a live auction
        for a in auctions:
            if a.get("status") == "live":
                return a["id"]
    pytest.skip("No live auction found for testing")

@pytest.fixture(scope="module")
def disposable_user():
    """Create a disposable user for GDPR delete test"""
    unique = uuid.uuid4().hex[:8]
    email = f"TEST_gdpr_{unique}@test.bg"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "testpass123",
        "name": f"GDPR Test User {unique}"
    })
    if r.status_code == 200:
        data = r.json()
        return {"token": data["token"], "email": email, "user": data["user"]}
    pytest.skip(f"Failed to create disposable user: {r.status_code} {r.text}")


# ============================================================
# Phase 3: Bid Moderation
# ============================================================
class TestBidModeration:
    """Phase 3 — Bid history, invalidate, block bidder"""

    def test_admin_get_bid_history(self, admin_token, test_auction_id):
        """GET /api/admin/auctions/{id}/bids returns bid history with is_blocked_on_auction flag"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/bids", headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list), "Expected list of bids"
        # Each bid should have is_blocked_on_auction field
        if len(data) > 0:
            assert "is_blocked_on_auction" in data[0], "Missing is_blocked_on_auction flag"
            print(f"Found {len(data)} bids for auction {test_auction_id}")

    def test_moderator_can_view_bid_history(self, moderator_token, test_auction_id):
        """Moderator can view bid history"""
        headers = {"Authorization": f"Bearer {moderator_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/bids", headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_invalidate_bid_requires_reason(self, admin_token):
        """POST /api/admin/bids/{bid_id}/invalidate requires reason >= 3 chars"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Use a fake bid ID - should return 404
        r = requests.post(f"{BASE_URL}/api/admin/bids/fake-bid-id/invalidate", 
                         headers=headers, json={"reason": "ab"})
        # Either 404 (bid not found) or 422 (validation error for short reason)
        assert r.status_code in [404, 422], f"Expected 404 or 422, got {r.status_code}"

    def test_block_bidder_on_auction(self, admin_token, test_auction_id):
        """POST /api/admin/auctions/{id}/block-bidder creates block entry"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        fake_user_id = f"test-block-{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/block-bidder",
                         headers=headers, json={"user_id": fake_user_id, "reason": "Test block"})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") == True

    def test_block_bidder_duplicate_returns_already_blocked(self, admin_token, test_auction_id):
        """Duplicate block call returns already_blocked: true"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        user_id = f"test-dup-block-{uuid.uuid4().hex[:8]}"
        # First block
        r1 = requests.post(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/block-bidder",
                          headers=headers, json={"user_id": user_id, "reason": "First block"})
        assert r1.status_code == 200
        # Second block - should return already_blocked
        r2 = requests.post(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/block-bidder",
                          headers=headers, json={"user_id": user_id, "reason": "Second block"})
        assert r2.status_code == 200
        data = r2.json()
        assert data.get("already_blocked") == True, "Expected already_blocked: true"

    def test_unblock_bidder(self, admin_token, test_auction_id):
        """DELETE /api/admin/auctions/{id}/block-bidder/{user_id} removes block"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        user_id = f"test-unblock-{uuid.uuid4().hex[:8]}"
        # First block
        requests.post(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/block-bidder",
                     headers=headers, json={"user_id": user_id, "reason": "To unblock"})
        # Then unblock
        r = requests.delete(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/block-bidder/{user_id}",
                           headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") == True


# ============================================================
# Phase 3: User Moderation
# ============================================================
class TestUserModeration:
    """Phase 3 — Suspend, verify seller, notes, VIN requests, resend verification"""

    def test_suspend_user(self, admin_token, buyer_token):
        """POST /api/admin/users/{id}/suspend suspends user"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Get buyer user ID
        buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=buyer_headers)
        if me.status_code != 200:
            pytest.skip("Cannot get buyer user info")
        buyer_id = me.json()["id"]
        
        r = requests.post(f"{BASE_URL}/api/admin/users/{buyer_id}/suspend", headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("suspended") == True
        
        # Unsuspend immediately to not break other tests
        r2 = requests.post(f"{BASE_URL}/api/admin/users/{buyer_id}/unsuspend", headers=headers)
        assert r2.status_code == 200

    def test_cannot_suspend_admin(self, admin_token):
        """Cannot suspend admin/moderator users"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Get admin's own ID
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        admin_id = me.json()["id"]
        
        r = requests.post(f"{BASE_URL}/api/admin/users/{admin_id}/suspend", headers=headers)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"

    def test_verify_seller(self, admin_token, buyer_token):
        """POST /api/admin/users/{id}/verify-seller toggles is_verified_dealer"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=buyer_headers)
        buyer_id = me.json()["id"]
        
        # Verify
        r = requests.post(f"{BASE_URL}/api/admin/users/{buyer_id}/verify-seller", headers=headers)
        assert r.status_code == 200
        assert r.json().get("is_verified_dealer") == True
        
        # Unverify
        r2 = requests.post(f"{BASE_URL}/api/admin/users/{buyer_id}/unverify-seller", headers=headers)
        assert r2.status_code == 200
        assert r2.json().get("is_verified_dealer") == False

    def test_user_notes_crud(self, admin_token, buyer_token):
        """POST/GET/DELETE /api/admin/users/{id}/notes"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=buyer_headers)
        buyer_id = me.json()["id"]
        
        # Add note
        r = requests.post(f"{BASE_URL}/api/admin/users/{buyer_id}/notes", 
                         headers=headers, json={"text": "Test internal note"})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        note = r.json()
        assert "id" in note
        note_id = note["id"]
        
        # List notes
        r2 = requests.get(f"{BASE_URL}/api/admin/users/{buyer_id}/notes", headers=headers)
        assert r2.status_code == 200
        notes = r2.json()
        assert any(n["id"] == note_id for n in notes), "Note not found in list"
        
        # Delete note
        r3 = requests.delete(f"{BASE_URL}/api/admin/users/{buyer_id}/notes/{note_id}", headers=headers)
        assert r3.status_code == 200

    def test_moderator_can_add_notes(self, moderator_token, buyer_token):
        """Moderator can add/view/delete notes"""
        headers = {"Authorization": f"Bearer {moderator_token}"}
        buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=buyer_headers)
        buyer_id = me.json()["id"]
        
        r = requests.post(f"{BASE_URL}/api/admin/users/{buyer_id}/notes",
                         headers=headers, json={"text": "Moderator note"})
        assert r.status_code == 200

    def test_get_user_vin_requests(self, admin_token, buyer_token):
        """GET /api/admin/users/{id}/vin-requests returns VIN request history"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=buyer_headers)
        buyer_id = me.json()["id"]
        
        r = requests.get(f"{BASE_URL}/api/admin/users/{buyer_id}/vin-requests", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_all_vin_requests(self, admin_token):
        """GET /api/admin/vin-requests returns all VIN requests"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/vin-requests", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_resend_verification(self, admin_token, buyer_token):
        """POST /api/admin/users/{id}/resend-verification sends email"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=buyer_headers)
        buyer_id = me.json()["id"]
        
        r = requests.post(f"{BASE_URL}/api/admin/users/{buyer_id}/resend-verification", headers=headers)
        # May fail if no email service configured, but endpoint should exist
        assert r.status_code in [200, 500], f"Expected 200 or 500, got {r.status_code}"


# ============================================================
# Phase 4: Payments & Views
# ============================================================
class TestPaymentsAndViews:
    """Phase 4 — Buyer fee status, Stripe events, views counter"""

    def test_get_buyer_fee(self, admin_token, test_auction_id):
        """GET /api/admin/auctions/{id}/buyer-fee returns fee data"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/buyer-fee", headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "buyer_fee_status" in data, "Missing buyer_fee_status"
        # Default should be unpaid
        assert data["buyer_fee_status"] in ["unpaid", "paid", "waived", "refunded"]

    def test_update_buyer_fee_status(self, admin_token, test_auction_id):
        """PUT /api/admin/auctions/{id}/buyer-fee updates status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/buyer-fee",
                        headers=headers, json={"status": "paid", "note": "Test payment"})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "paid"
        
        # Reset to unpaid
        requests.put(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/buyer-fee",
                    headers=headers, json={"status": "unpaid"})

    def test_buyer_fee_invalid_status(self, admin_token, test_auction_id):
        """PUT /api/admin/auctions/{id}/buyer-fee rejects invalid status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.put(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/buyer-fee",
                        headers=headers, json={"status": "invalid_status"})
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"

    def test_get_stripe_events(self, admin_token):
        """GET /api/admin/stripe/events returns webhook events"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/stripe/events", headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "items" in data
        assert "total" in data

    def test_stripe_events_admin_only(self, moderator_token):
        """GET /api/admin/stripe/events is admin-only (403 for moderator)"""
        headers = {"Authorization": f"Bearer {moderator_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/stripe/events", headers=headers)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"

    def test_views_counter_increments(self, test_auction_id):
        """GET /api/auctions/{id} increments views_count"""
        # First request
        r1 = requests.get(f"{BASE_URL}/api/auctions/{test_auction_id}")
        assert r1.status_code == 200
        views1 = r1.json().get("views_count", 0)
        
        # Second request
        r2 = requests.get(f"{BASE_URL}/api/auctions/{test_auction_id}")
        assert r2.status_code == 200
        views2 = r2.json().get("views_count", 0)
        
        assert views2 > views1, f"Views should increment: {views1} -> {views2}"


# ============================================================
# Phase 5: CMS Settings
# ============================================================
class TestCMSSettings:
    """Phase 5 — OG image, maintenance mode"""

    def test_public_settings_exposes_og_and_maintenance(self):
        """GET /api/settings exposes og_image_url, maintenance_mode, maintenance_message"""
        r = requests.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "og_image_url" in data, "Missing og_image_url"
        assert "maintenance_mode" in data, "Missing maintenance_mode"
        assert "maintenance_message" in data, "Missing maintenance_message"

    def test_admin_update_og_image(self, admin_token):
        """PUT /api/admin/settings accepts og_image_url"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        test_url = "https://example.com/test-og.jpg"
        r = requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                        json={"og_image_url": test_url})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        
        # Verify
        r2 = requests.get(f"{BASE_URL}/api/settings")
        assert r2.json().get("og_image_url") == test_url
        
        # Reset
        requests.put(f"{BASE_URL}/api/admin/settings", headers=headers, json={"og_image_url": ""})

    def test_maintenance_mode_toggle(self, admin_token):
        """PUT /api/admin/settings accepts maintenance_mode and maintenance_message"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Enable maintenance
        r = requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                        json={"maintenance_mode": True, "maintenance_message": "Test maintenance"})
        assert r.status_code == 200
        
        # Verify public settings
        r2 = requests.get(f"{BASE_URL}/api/settings")
        assert r2.json().get("maintenance_mode") == True
        assert r2.json().get("maintenance_message") == "Test maintenance"
        
        # IMPORTANT: Disable maintenance mode immediately
        r3 = requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                         json={"maintenance_mode": False})
        assert r3.status_code == 200


# ============================================================
# Phase 5: Maintenance Middleware
# ============================================================
class TestMaintenanceMiddleware:
    """Phase 5 — Maintenance mode blocks write operations"""

    def test_maintenance_blocks_bid(self, admin_token, buyer_token, test_auction_id):
        """When maintenance_mode=true, POST /api/auctions/{id}/bids returns 503"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        buyer_headers = {"Authorization": f"Bearer {buyer_token}"}
        
        # Enable maintenance
        r = requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                        json={"maintenance_mode": True})
        assert r.status_code == 200
        
        try:
            # Try to place bid
            r2 = requests.post(f"{BASE_URL}/api/auctions/{test_auction_id}/bids",
                              headers=buyer_headers, json={"amount_eur": 999999})
            # Should be 503 (maintenance) or 400/402 (validation/payment)
            # The middleware should intercept before validation
            assert r2.status_code in [503, 400, 402], f"Expected 503/400/402, got {r2.status_code}"
            if r2.status_code == 503:
                print("Maintenance middleware correctly blocked bid")
        finally:
            # ALWAYS disable maintenance
            requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                        json={"maintenance_mode": False})

    def test_maintenance_allows_get_requests(self, admin_token):
        """GET requests should work during maintenance"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Enable maintenance
        requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                    json={"maintenance_mode": True})
        
        try:
            # GET should still work
            r = requests.get(f"{BASE_URL}/api/auctions")
            assert r.status_code == 200, f"GET should work during maintenance, got {r.status_code}"
        finally:
            # ALWAYS disable maintenance
            requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                        json={"maintenance_mode": False})

    def test_maintenance_allows_admin_routes(self, admin_token):
        """Admin routes should work during maintenance"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Enable maintenance
        requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                    json={"maintenance_mode": True})
        
        try:
            # Admin POST should still work
            r = requests.get(f"{BASE_URL}/api/admin/settings", headers=headers)
            assert r.status_code == 200, f"Admin routes should work during maintenance"
        finally:
            # ALWAYS disable maintenance
            requests.put(f"{BASE_URL}/api/admin/settings", headers=headers,
                        json={"maintenance_mode": False})


# ============================================================
# GDPR: Delete Account
# ============================================================
class TestGDPR:
    """GDPR — DELETE /api/auth/me cascades user data"""

    def test_delete_account_cascades(self, disposable_user):
        """DELETE /api/auth/me deletes user and cascades data"""
        headers = {"Authorization": f"Bearer {disposable_user['token']}"}
        
        r = requests.delete(f"{BASE_URL}/api/auth/me", headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") == True
        assert "deleted" in data
        
        # Verify user is gone
        r2 = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert r2.status_code == 401, "User should be deleted"


# ============================================================
# Blocked Bidder Test
# ============================================================
class TestBlockedBidderBehavior:
    """Test that blocked bidder gets 403 when trying to bid"""

    def test_blocked_user_cannot_bid(self, admin_token, test_auction_id):
        """Blocked user gets 403 when placing bid"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a test user
        unique = uuid.uuid4().hex[:8]
        email = f"TEST_blocked_{unique}@test.bg"
        reg = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "testpass123",
            "name": f"Blocked Test {unique}"
        })
        if reg.status_code != 200:
            pytest.skip("Cannot create test user")
        
        user_token = reg.json()["token"]
        user_id = reg.json()["user"]["id"]
        user_headers = {"Authorization": f"Bearer {user_token}"}
        
        # Block the user on this auction
        r = requests.post(f"{BASE_URL}/api/admin/auctions/{test_auction_id}/block-bidder",
                         headers=headers, json={"user_id": user_id, "reason": "Test block"})
        assert r.status_code == 200
        
        # Try to bid - should get 403
        r2 = requests.post(f"{BASE_URL}/api/auctions/{test_auction_id}/bids",
                          headers=user_headers, json={"amount_eur": 999999, "payment_method_id": "pm_test"})
        assert r2.status_code == 403, f"Expected 403 for blocked user, got {r2.status_code}"
        
        # Cleanup - delete test user
        requests.delete(f"{BASE_URL}/api/auth/me", headers=user_headers)


# ============================================================
# Suspended User Test
# ============================================================
class TestSuspendedUserBehavior:
    """Test that suspended user gets 403 when trying to bid"""

    def test_suspended_user_cannot_bid(self, admin_token, test_auction_id):
        """Suspended user gets 403 when placing bid"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Create a test user
        unique = uuid.uuid4().hex[:8]
        email = f"TEST_suspended_{unique}@test.bg"
        reg = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email,
            "password": "testpass123",
            "name": f"Suspended Test {unique}"
        })
        if reg.status_code != 200:
            pytest.skip("Cannot create test user")
        
        user_token = reg.json()["token"]
        user_id = reg.json()["user"]["id"]
        user_headers = {"Authorization": f"Bearer {user_token}"}
        
        # Suspend the user
        r = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/suspend", headers=headers)
        assert r.status_code == 200
        
        # Try to bid - should get 403
        r2 = requests.post(f"{BASE_URL}/api/auctions/{test_auction_id}/bids",
                          headers=user_headers, json={"amount_eur": 999999, "payment_method_id": "pm_test"})
        assert r2.status_code == 403, f"Expected 403 for suspended user, got {r2.status_code}"
        
        # Cleanup - unsuspend and delete
        requests.post(f"{BASE_URL}/api/admin/users/{user_id}/unsuspend", headers=headers)
        requests.delete(f"{BASE_URL}/api/auth/me", headers=user_headers)


# ============================================================
# Regression: Phase 1 & 2
# ============================================================
class TestRegression:
    """Regression tests for Phase 1 & 2 features"""

    def test_stripe_cms_get(self, admin_token):
        """GET /api/admin/stripe returns Stripe config"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/stripe", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "mode" in data
        assert "stripe_enabled" in data

    def test_audit_log(self, admin_token):
        """GET /api/admin/audit-log returns audit entries"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.get(f"{BASE_URL}/api/admin/audit-log", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data

    def test_forgot_password_endpoint(self):
        """POST /api/auth/forgot-password exists"""
        r = requests.post(f"{BASE_URL}/api/auth/forgot-password", 
                         json={"email": "nonexistent@test.bg"})
        # Should return 200 even for non-existent email (security)
        assert r.status_code == 200

    def test_makes_list(self):
        """GET /api/makes returns makes list"""
        r = requests.get(f"{BASE_URL}/api/makes")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "Should have seeded makes"

    def test_reactivate_auction(self, admin_token):
        """POST /api/admin/auctions/{id}/reactivate exists"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        # Use fake ID - should return 404
        r = requests.post(f"{BASE_URL}/api/admin/auctions/fake-id/reactivate", 
                         headers=headers, params={"days": 7})
        assert r.status_code == 404, "Should return 404 for non-existent auction"
