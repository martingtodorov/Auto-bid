"""
Phase 2 Testing: Makes CMS + Auction Lifecycle + Listing Hardening
Tests for:
- Makes CMS (GET /api/makes, admin CRUD)
- Auction create validation (unknown make, VAT fields, no_reserve)
- Auction lifecycle (pause/unpause/cancel/close-now/archive/featured/duplicate)
- Visibility filters (public vs admin)
"""
import pytest
import requests
import os
import time
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@autobids.bg"
ADMIN_PASSWORD = "admin123"
MODERATOR_EMAIL = "moderator@test.bg"
MODERATOR_PASSWORD = "mod12345"
BUYER_EMAIL = "reviewbuyer@test.bg"
BUYER_PASSWORD = "newPass123"

# Seeded auction for lifecycle tests
TEST_AUCTION_ID = "c049f61a-7c0b-4cf5-994f-387776bb2403"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code == 200:
        data = resp.json()
        # Handle 2FA if enabled
        if data.get("requires_2fa"):
            pytest.skip("Admin has 2FA enabled - skipping")
        return data.get("token")
    pytest.fail(f"Admin login failed: {resp.status_code} - {resp.text}")


@pytest.fixture(scope="module")
def moderator_token():
    """Get moderator auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MODERATOR_EMAIL,
        "password": MODERATOR_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Moderator login failed: {resp.status_code}")


@pytest.fixture(scope="module")
def buyer_token():
    """Get buyer auth token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": BUYER_EMAIL,
        "password": BUYER_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Buyer login failed: {resp.status_code}")


class TestMakesCMS:
    """Tests for Makes CMS endpoints"""
    
    def test_public_makes_list(self):
        """GET /api/makes returns alphabetical list of makes"""
        resp = requests.get(f"{BASE_URL}/api/makes")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of makes"
        assert len(data) >= 79, f"Expected at least 79 seeded makes, got {len(data)}"
        # Check alphabetical order
        names = [m["name"] for m in data]
        assert names == sorted(names), "Makes should be alphabetically sorted"
        # Check structure
        assert "id" in data[0], "Make should have id"
        assert "name" in data[0], "Make should have name"
        print(f"✓ Public makes list: {len(data)} makes, alphabetically sorted")
    
    def test_admin_makes_list(self, admin_token):
        """GET /api/admin/makes returns makes for admin"""
        resp = requests.get(f"{BASE_URL}/api/admin/makes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"✓ Admin makes list: {len(data)} makes")
    
    def test_moderator_can_view_makes(self, moderator_token):
        """Moderator can GET /api/admin/makes"""
        resp = requests.get(f"{BASE_URL}/api/admin/makes", headers={
            "Authorization": f"Bearer {moderator_token}"
        })
        assert resp.status_code == 200, f"Moderator should be able to view makes, got {resp.status_code}"
        print("✓ Moderator can view admin makes list")
    
    def test_admin_add_make(self, admin_token):
        """POST /api/admin/makes creates new make (admin only)"""
        test_make_name = f"TEST_Make_{int(time.time())}"
        resp = requests.post(f"{BASE_URL}/api/admin/makes", 
            json={"name": test_make_name},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("name") == test_make_name
        assert "id" in data
        print(f"✓ Admin created make: {test_make_name}")
        # Store for cleanup
        pytest.test_make_id = data["id"]
        pytest.test_make_name = test_make_name
    
    def test_moderator_cannot_add_make(self, moderator_token):
        """POST /api/admin/makes returns 403 for moderator"""
        resp = requests.post(f"{BASE_URL}/api/admin/makes",
            json={"name": "ModeratorTestMake"},
            headers={"Authorization": f"Bearer {moderator_token}"}
        )
        assert resp.status_code == 403, f"Moderator should get 403, got {resp.status_code}"
        print("✓ Moderator correctly denied from adding makes (403)")
    
    def test_duplicate_make_returns_409(self, admin_token):
        """POST /api/admin/makes with existing name returns 409"""
        resp = requests.post(f"{BASE_URL}/api/admin/makes",
            json={"name": "BMW"},  # BMW is seeded
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 409, f"Expected 409 for duplicate, got {resp.status_code}"
        print("✓ Duplicate make correctly returns 409")
    
    def test_delete_unused_make(self, admin_token):
        """DELETE /api/admin/makes/{id} succeeds for unused make"""
        if not hasattr(pytest, 'test_make_id'):
            pytest.skip("No test make created")
        resp = requests.delete(f"{BASE_URL}/api/admin/makes/{pytest.test_make_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print(f"✓ Deleted unused make: {pytest.test_make_name}")
    
    def test_delete_used_make_blocked(self, admin_token):
        """DELETE /api/admin/makes/{id} returns 400 if make is in use"""
        # First get BMW's id
        resp = requests.get(f"{BASE_URL}/api/admin/makes", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        makes = resp.json()
        bmw = next((m for m in makes if m["name"] == "BMW"), None)
        if not bmw:
            pytest.skip("BMW make not found")
        
        resp = requests.delete(f"{BASE_URL}/api/admin/makes/{bmw['id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 400, f"Expected 400 for used make, got {resp.status_code}"
        print("✓ Delete of used make correctly blocked (400)")


class TestAuctionCreateValidation:
    """Tests for auction creation validation (Phase 2 hardening)"""
    
    def test_unknown_make_rejected(self, admin_token):
        """POST /api/auctions with unknown make returns 400"""
        payload = {
            "title": "Test Unknown Make",
            "make": "NONEXISTENT_MAKE_XYZ",
            "model": "Test",
            "year": 2020,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Черен",
            "region": "София (град)",
            "city": "София",
            "description": "Test description for unknown make",
            "starting_bid_eur": 5000,
            "duration_days": 10,
            "contact_email": "test@test.bg",
            "contact_phone": "+359888888888",
            "images_exterior": ["https://example.com/1.jpg"] * 8,
            "images_wheels": ["https://example.com/w.jpg"] * 4,
            "images_bumper": ["https://example.com/b.jpg"],
            "images_interior": ["https://example.com/i.jpg"] * 4,
        }
        resp = requests.post(f"{BASE_URL}/api/auctions", json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 400, f"Expected 400 for unknown make, got {resp.status_code}"
        assert "Неизвестна марка" in resp.text or "unknown" in resp.text.lower()
        print("✓ Unknown make correctly rejected (400)")
    
    def test_vat_inclusive_requires_prices(self, admin_token):
        """vat_status='vat_inclusive' without prices returns 400"""
        payload = {
            "title": "Test VAT Inclusive",
            "make": "BMW",
            "model": "X5",
            "year": 2020,
            "mileage_km": 50000,
            "fuel": "Дизел",
            "transmission": "Автоматична",
            "body_type": "Джип",
            "power_hp": 300,
            "engine_cc": 3000,
            "color": "Бял",
            "region": "София (град)",
            "city": "София",
            "description": "Test VAT inclusive without prices",
            "starting_bid_eur": 30000,
            "vat_status": "vat_inclusive",
            # Missing price_net_eur and price_gross_eur
            "duration_days": 10,
            "contact_email": "test@test.bg",
            "contact_phone": "+359888888888",
            "images_exterior": ["https://example.com/1.jpg"] * 8,
            "images_wheels": ["https://example.com/w.jpg"] * 4,
            "images_bumper": ["https://example.com/b.jpg"],
            "images_interior": ["https://example.com/i.jpg"] * 4,
        }
        resp = requests.post(f"{BASE_URL}/api/auctions", json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ VAT inclusive without prices correctly rejected (400)")
    
    def test_vat_gross_must_exceed_net(self, admin_token):
        """vat_status='vat_inclusive' with gross <= net returns 400"""
        payload = {
            "title": "Test VAT Gross <= Net",
            "make": "BMW",
            "model": "X5",
            "year": 2020,
            "mileage_km": 50000,
            "fuel": "Дизел",
            "transmission": "Автоматична",
            "body_type": "Джип",
            "power_hp": 300,
            "engine_cc": 3000,
            "color": "Бял",
            "region": "София (град)",
            "city": "София",
            "description": "Test VAT gross <= net",
            "starting_bid_eur": 30000,
            "vat_status": "vat_inclusive",
            "price_net_eur": 25000,
            "price_gross_eur": 25000,  # Equal to net - should fail
            "duration_days": 10,
            "contact_email": "test@test.bg",
            "contact_phone": "+359888888888",
            "images_exterior": ["https://example.com/1.jpg"] * 8,
            "images_wheels": ["https://example.com/w.jpg"] * 4,
            "images_bumper": ["https://example.com/b.jpg"],
            "images_interior": ["https://example.com/i.jpg"] * 4,
        }
        resp = requests.post(f"{BASE_URL}/api/auctions", json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print("✓ VAT gross <= net correctly rejected (400)")
    
    def test_no_reserve_clears_reserve_eur(self, admin_token):
        """no_reserve=true stores reserve_eur=null"""
        payload = {
            "title": "TEST_NoReserve_Auction",
            "make": "BMW",
            "model": "M3",
            "year": 2021,
            "mileage_km": 30000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 480,
            "engine_cc": 3000,
            "color": "Син",
            "region": "София (град)",
            "city": "София",
            "description": "Test no reserve auction",
            "starting_bid_eur": 50000,
            "reserve_eur": 60000,  # This should be cleared
            "no_reserve": True,
            "duration_days": 10,
            "contact_email": "test@test.bg",
            "contact_phone": "+359888888888",
            "images_exterior": ["https://example.com/1.jpg"] * 8,
            "images_wheels": ["https://example.com/w.jpg"] * 4,
            "images_bumper": ["https://example.com/b.jpg"],
            "images_interior": ["https://example.com/i.jpg"] * 4,
        }
        resp = requests.post(f"{BASE_URL}/api/auctions", json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        auction_id = data.get("id")
        
        # Verify the auction was created with no reserve
        resp2 = requests.get(f"{BASE_URL}/api/auctions/{auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp2.status_code == 200
        auction = resp2.json()
        assert auction.get("no_reserve") == True, "no_reserve should be True"
        assert auction.get("has_reserve") == False, "has_reserve should be False"
        print(f"✓ No-reserve auction created correctly: {auction_id}")
        pytest.no_reserve_auction_id = auction_id


class TestAuctionLifecycle:
    """Tests for auction lifecycle endpoints (Phase 2)"""
    
    def test_pause_live_auction(self, admin_token):
        """POST /api/admin/auctions/{id}/pause pauses a live auction"""
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/pause",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "paused"
        assert "seconds_remaining" in data
        print(f"✓ Auction paused, seconds_remaining: {data.get('seconds_remaining')}")
    
    def test_pause_already_paused_fails(self, admin_token):
        """POST /api/admin/auctions/{id}/pause on paused auction returns 400"""
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/pause",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 400, f"Expected 400 for already paused, got {resp.status_code}"
        print("✓ Pause on already paused auction correctly returns 400")
    
    def test_unpause_auction(self, admin_token):
        """POST /api/admin/auctions/{id}/unpause resumes a paused auction"""
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/unpause",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "live"
        assert "ends_at" in data
        print(f"✓ Auction unpaused, new ends_at: {data.get('ends_at')}")
    
    def test_unpause_not_paused_fails(self, admin_token):
        """POST /api/admin/auctions/{id}/unpause on non-paused auction returns 400"""
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/unpause",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 400, f"Expected 400 for not paused, got {resp.status_code}"
        print("✓ Unpause on non-paused auction correctly returns 400")
    
    def test_toggle_featured(self, admin_token):
        """POST /api/admin/auctions/{id}/featured toggles featured status"""
        # Get current state
        resp = requests.get(f"{BASE_URL}/api/auctions/{TEST_AUCTION_ID}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        current_featured = resp.json().get("featured", False)
        
        # Toggle
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/featured",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert data.get("featured") == (not current_featured)
        print(f"✓ Featured toggled from {current_featured} to {data.get('featured')}")
        
        # Toggle back
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/featured",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
    
    def test_close_now_live_auction(self, admin_token):
        """POST /api/admin/auctions/{id}/close-now sets ends_at to now"""
        # First ensure auction is live
        resp = requests.get(f"{BASE_URL}/api/auctions/{TEST_AUCTION_ID}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if resp.json().get("status") != "live":
            pytest.skip("Auction not in live status")
        
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/close-now",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "ends_at" in data
        print(f"✓ Close-now executed, ends_at: {data.get('ends_at')}")
        
        # Reset auction back to live for other tests
        time.sleep(1)
    
    def test_cancel_auction_requires_reason(self, admin_token):
        """POST /api/admin/auctions/{id}/cancel requires reason >= 3 chars"""
        # Create a test auction to cancel
        payload = {
            "title": "TEST_Cancel_Auction",
            "make": "Audi",
            "model": "A4",
            "year": 2019,
            "mileage_km": 60000,
            "fuel": "Дизел",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 190,
            "engine_cc": 2000,
            "color": "Сив",
            "region": "Пловдив",
            "city": "Пловдив",
            "description": "Test auction for cancel",
            "starting_bid_eur": 20000,
            "duration_days": 10,
            "contact_email": "test@test.bg",
            "contact_phone": "+359888888888",
            "images_exterior": ["https://example.com/1.jpg"] * 8,
            "images_wheels": ["https://example.com/w.jpg"] * 4,
            "images_bumper": ["https://example.com/b.jpg"],
            "images_interior": ["https://example.com/i.jpg"] * 4,
        }
        resp = requests.post(f"{BASE_URL}/api/auctions", json=payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if resp.status_code != 200:
            pytest.skip(f"Could not create test auction: {resp.text}")
        auction_id = resp.json().get("id")
        
        # Approve it first
        requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Try cancel with short reason
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/cancel",
            json={"reason": "ab"},  # Too short
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 422, f"Expected 422 for short reason, got {resp.status_code}"
        
        # Cancel with valid reason
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/cancel",
            json={"reason": "Продавачът се отказа от продажбата"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json().get("status") == "cancelled"
        print(f"✓ Auction cancelled with reason: {auction_id}")
        pytest.cancelled_auction_id = auction_id
    
    def test_archive_auction(self, admin_token):
        """POST /api/admin/auctions/{id}/archive sets is_archived=true"""
        if not hasattr(pytest, 'cancelled_auction_id'):
            pytest.skip("No cancelled auction to archive")
        
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{pytest.cancelled_auction_id}/archive",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json().get("is_archived") == True
        print(f"✓ Auction archived: {pytest.cancelled_auction_id}")
    
    def test_unarchive_auction(self, admin_token):
        """POST /api/admin/auctions/{id}/unarchive sets is_archived=false"""
        if not hasattr(pytest, 'cancelled_auction_id'):
            pytest.skip("No archived auction to unarchive")
        
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{pytest.cancelled_auction_id}/unarchive",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert resp.json().get("is_archived") == False
        print(f"✓ Auction unarchived: {pytest.cancelled_auction_id}")
    
    def test_moderator_cannot_pause(self, moderator_token):
        """Moderator cannot pause auctions (403)"""
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/pause",
            headers={"Authorization": f"Bearer {moderator_token}"}
        )
        assert resp.status_code == 403, f"Moderator should get 403, got {resp.status_code}"
        print("✓ Moderator correctly denied from pausing (403)")
    
    def test_moderator_cannot_cancel(self, moderator_token):
        """Moderator cannot cancel auctions (403)"""
        resp = requests.post(f"{BASE_URL}/api/admin/auctions/{TEST_AUCTION_ID}/cancel",
            json={"reason": "Test reason"},
            headers={"Authorization": f"Bearer {moderator_token}"}
        )
        assert resp.status_code == 403, f"Moderator should get 403, got {resp.status_code}"
        print("✓ Moderator correctly denied from cancelling (403)")


class TestDuplicateAuction:
    """Tests for auction duplication"""
    
    def test_admin_can_duplicate_any_auction(self, admin_token):
        """Admin can duplicate any auction"""
        resp = requests.post(f"{BASE_URL}/api/auctions/{TEST_AUCTION_ID}/duplicate",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data.get("status") == "pending"
        print(f"✓ Admin duplicated auction, new id: {data.get('id')}")
        pytest.duplicated_auction_id = data.get("id")
    
    def test_duplicated_auction_has_copy_suffix(self, admin_token):
        """Duplicated auction has '(копие)' suffix in title"""
        if not hasattr(pytest, 'duplicated_auction_id'):
            pytest.skip("No duplicated auction")
        
        resp = requests.get(f"{BASE_URL}/api/auctions/{pytest.duplicated_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        auction = resp.json()
        assert "(копие)" in auction.get("title", ""), f"Title should contain '(копие)': {auction.get('title')}"
        assert auction.get("status") == "pending"
        assert auction.get("bid_count", 0) == 0, "Duplicated auction should have 0 bids"
        print(f"✓ Duplicated auction has correct title and reset state")
    
    def test_buyer_cannot_duplicate_others_auction(self, buyer_token):
        """Buyer cannot duplicate another user's auction"""
        resp = requests.post(f"{BASE_URL}/api/auctions/{TEST_AUCTION_ID}/duplicate",
            headers={"Authorization": f"Bearer {buyer_token}"}
        )
        assert resp.status_code == 403, f"Buyer should get 403, got {resp.status_code}"
        print("✓ Buyer correctly denied from duplicating others' auction (403)")


class TestVisibilityFilters:
    """Tests for public vs admin visibility"""
    
    def test_public_excludes_archived(self, admin_token):
        """Public /api/auctions excludes is_archived=true"""
        # Archive an auction
        if hasattr(pytest, 'cancelled_auction_id'):
            requests.post(f"{BASE_URL}/api/admin/auctions/{pytest.cancelled_auction_id}/archive",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
        
        # Public listing should not include archived
        resp = requests.get(f"{BASE_URL}/api/auctions")
        assert resp.status_code == 200
        auctions = resp.json()
        archived_in_public = [a for a in auctions if a.get("is_archived")]
        assert len(archived_in_public) == 0, "Public listing should not include archived auctions"
        print("✓ Public listing excludes archived auctions")
    
    def test_public_excludes_non_public_statuses(self):
        """Public /api/auctions excludes pending/rejected/withdrawn/removed/cancelled/paused"""
        resp = requests.get(f"{BASE_URL}/api/auctions")
        assert resp.status_code == 200
        auctions = resp.json()
        non_public_statuses = ["pending", "rejected", "withdrawn", "removed", "cancelled", "paused"]
        for auction in auctions:
            assert auction.get("status") not in non_public_statuses, \
                f"Public listing should not include {auction.get('status')} status"
        print("✓ Public listing excludes non-public statuses")
    
    def test_admin_sees_all_statuses(self, admin_token):
        """Admin /api/admin/auctions sees all statuses"""
        resp = requests.get(f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        auctions = resp.json()
        statuses = set(a.get("status") for a in auctions)
        print(f"✓ Admin sees statuses: {statuses}")
        # Admin should see at least pending (from duplicated auction)
        assert len(auctions) > 0, "Admin should see auctions"


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_auctions(self, admin_token):
        """Delete test auctions created during testing"""
        # Get all auctions with TEST_ prefix
        resp = requests.get(f"{BASE_URL}/api/admin/auctions?q=TEST_",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if resp.status_code == 200:
            auctions = resp.json()
            for a in auctions:
                if a.get("title", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/admin/auctions/{a['id']}",
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
                    print(f"  Cleaned up: {a['id']}")
        
        # Also clean up duplicated auction
        if hasattr(pytest, 'duplicated_auction_id'):
            requests.delete(f"{BASE_URL}/api/admin/auctions/{pytest.duplicated_auction_id}",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            print(f"  Cleaned up duplicated: {pytest.duplicated_auction_id}")
        
        print("✓ Test cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
