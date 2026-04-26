"""
Backend tests for Admin Auction Management (autoandbid.com)
Tests new admin endpoints: GET/PUT /admin/auctions/{id}, POST /admin/auctions/{id}/remove, POST /admin/auctions/{id}/restore
Also tests regression for existing endpoints.
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "contact@autoandbid.com"
ADMIN_PASSWORD = "admin123"
TEST_USER_EMAIL = f"testuser_{uuid.uuid4().hex[:8]}@test.com"
TEST_USER_PASSWORD = "testpass123"
TEST_USER_NAME = "Test User"


class TestAuthRegression:
    """Regression tests for auth endpoints"""
    
    def test_login_admin_success(self):
        """Admin login should work with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "admin"
        print(f"✓ Admin login successful, role={data['user']['role']}")
    
    def test_login_invalid_credentials(self):
        """Login with wrong password should return 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Invalid credentials correctly rejected")
    
    def test_register_new_user(self):
        """Register a new user"""
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD,
            "name": TEST_USER_NAME
        })
        assert response.status_code == 200, f"Registration failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["role"] == "user"
        print(f"✓ User registration successful: {TEST_USER_EMAIL}")


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Admin login failed")
    return response.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    """Get regular user auth token"""
    email = f"testuser_{uuid.uuid4().hex[:8]}@test.com"
    response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email,
        "password": "testpass123",
        "name": "Regular User"
    })
    if response.status_code != 200:
        pytest.skip("User registration failed")
    return response.json()["token"]


@pytest.fixture(scope="module")
def test_auction_id(admin_token):
    """Get an existing auction ID for testing"""
    response = requests.get(f"{BASE_URL}/api/admin/auctions", 
                           headers={"Authorization": f"Bearer {admin_token}"})
    if response.status_code != 200 or not response.json():
        pytest.skip("No auctions available for testing")
    return response.json()[0]["id"]


class TestAdminGetAuction:
    """Tests for GET /api/admin/auctions/{id}"""
    
    def test_admin_get_auction_success(self, admin_token, test_auction_id):
        """Admin should get full auction document"""
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        # Verify full document fields
        assert "id" in data
        assert "title" in data
        assert "status" in data
        assert "ends_at" in data
        assert "current_bid_eur" in data
        print(f"✓ Admin GET auction successful: {data['title'][:50]}...")
    
    def test_admin_get_auction_not_found(self, admin_token):
        """Should return 404 for non-existent auction"""
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions/nonexistent-id-12345",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 404
        print("✓ 404 returned for non-existent auction")
    
    def test_non_admin_get_auction_forbidden(self, user_token, test_auction_id):
        """Non-admin should get 403"""
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403
        print("✓ 403 returned for non-admin user")
    
    def test_unauthenticated_get_auction_forbidden(self, test_auction_id):
        """Unauthenticated request should get 401"""
        response = requests.get(f"{BASE_URL}/api/admin/auctions/{test_auction_id}")
        assert response.status_code == 401
        print("✓ 401 returned for unauthenticated request")


class TestAdminUpdateAuction:
    """Tests for PUT /api/admin/auctions/{id}"""
    
    def test_admin_update_title(self, admin_token, test_auction_id):
        """Admin can update title"""
        # Get original
        orig = requests.get(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        
        new_title = f"TEST_Updated_{uuid.uuid4().hex[:6]}"
        response = requests.put(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"title": new_title}
        )
        assert response.status_code == 200, f"Update failed: {response.text}"
        
        # Verify change persisted
        updated = requests.get(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        assert updated["title"] == new_title
        
        # Restore original
        requests.put(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"title": orig["title"]}
        )
        print(f"✓ Admin updated title successfully")
    
    def test_admin_update_current_bid(self, admin_token, test_auction_id):
        """Admin can update current_bid_eur (active bidding)"""
        response = requests.put(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"current_bid_eur": 99999.0}
        )
        assert response.status_code == 200
        
        # Verify
        updated = requests.get(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        assert updated["current_bid_eur"] == 99999.0
        print("✓ Admin updated current_bid_eur successfully")
    
    def test_admin_update_ends_at(self, admin_token, test_auction_id):
        """Admin can update ends_at"""
        new_ends_at = "2026-12-31T23:59:59+00:00"
        response = requests.put(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"ends_at": new_ends_at}
        )
        assert response.status_code == 200
        print("✓ Admin updated ends_at successfully")
    
    def test_admin_update_status_valid(self, admin_token, test_auction_id):
        """Admin can change status to valid values"""
        for status in ["live", "ended", "pending"]:
            response = requests.put(
                f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"status": status}
            )
            assert response.status_code == 200, f"Failed to set status={status}: {response.text}"
        
        # Restore to live
        requests.put(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "live"}
        )
        print("✓ Admin updated status to valid values")
    
    def test_admin_update_status_invalid(self, admin_token, test_auction_id):
        """Admin cannot set invalid status"""
        response = requests.put(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "invalid_status_xyz"}
        )
        assert response.status_code == 400
        print("✓ Invalid status correctly rejected with 400")
    
    def test_admin_update_all_fields(self, admin_token, test_auction_id):
        """Admin can update all editable fields"""
        payload = {
            "title": "TEST_Full_Update",
            "description": "Test description update",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2025,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 300,
            "engine_cc": 3000,
            "color": "TestColor",
            "region": "TestRegion",
            "city": "TestCity",
            "vin": "TESTVIN12345678X",
            "starting_bid_eur": 10000.0,
            "reserve_eur": 15000.0,
            "current_bid_eur": 12000.0,
            "featured": True,
            "seller_name": "Test Seller"
        }
        response = requests.put(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=payload
        )
        assert response.status_code == 200, f"Full update failed: {response.text}"
        
        # Verify some fields
        updated = requests.get(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        assert updated["make"] == "TestMake"
        assert updated["model"] == "TestModel"
        assert updated["vin"] == "TESTVIN12345678X"
        print("✓ Admin full update successful")
    
    def test_non_admin_update_forbidden(self, user_token, test_auction_id):
        """Non-admin should get 403"""
        response = requests.put(
            f"{BASE_URL}/api/admin/auctions/{test_auction_id}",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"title": "Hacked Title"}
        )
        assert response.status_code == 403
        print("✓ 403 returned for non-admin update attempt")


class TestAdminRemoveAuction:
    """Tests for POST /api/admin/auctions/{id}/remove"""
    
    @pytest.fixture
    def removable_auction_id(self, admin_token):
        """Get a live auction to test remove/restore"""
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"status": "live"}
        )
        if response.status_code != 200 or not response.json():
            pytest.skip("No live auctions for remove test")
        return response.json()[0]["id"]
    
    def test_admin_remove_auction(self, admin_token, removable_auction_id):
        """Admin can remove (soft delete) an auction"""
        response = requests.post(
            f"{BASE_URL}/api/admin/auctions/{removable_auction_id}/remove",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Remove failed: {response.text}"
        
        # Verify status changed to 'removed'
        auction = requests.get(
            f"{BASE_URL}/api/admin/auctions/{removable_auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        assert auction["status"] == "removed"
        print("✓ Admin removed auction successfully")
    
    def test_removed_auction_hidden_from_public(self, admin_token, removable_auction_id):
        """Removed auction should not appear in public listings"""
        # First ensure it's removed
        requests.post(
            f"{BASE_URL}/api/admin/auctions/{removable_auction_id}/remove",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Check public listing (no auth)
        public_response = requests.get(f"{BASE_URL}/api/auctions")
        assert public_response.status_code == 200
        public_ids = [a["id"] for a in public_response.json()]
        assert removable_auction_id not in public_ids, "Removed auction should not be in public listings"
        print("✓ Removed auction hidden from public listings")
    
    def test_non_admin_remove_forbidden(self, user_token, removable_auction_id):
        """Non-admin should get 403"""
        response = requests.post(
            f"{BASE_URL}/api/admin/auctions/{removable_auction_id}/remove",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403
        print("✓ 403 returned for non-admin remove attempt")


class TestAdminRestoreAuction:
    """Tests for POST /api/admin/auctions/{id}/restore"""
    
    @pytest.fixture
    def removed_auction_id(self, admin_token):
        """Get or create a removed auction"""
        # First try to find an existing removed auction
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"status": "removed"}
        )
        if response.status_code == 200 and response.json():
            return response.json()[0]["id"]
        
        # Otherwise, remove a live one
        live_response = requests.get(
            f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"status": "live"}
        )
        if live_response.status_code != 200 or not live_response.json():
            pytest.skip("No auctions available for restore test")
        
        auction_id = live_response.json()[0]["id"]
        requests.post(
            f"{BASE_URL}/api/admin/auctions/{auction_id}/remove",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        return auction_id
    
    def test_admin_restore_auction(self, admin_token, removed_auction_id):
        """Admin can restore a removed auction"""
        response = requests.post(
            f"{BASE_URL}/api/admin/auctions/{removed_auction_id}/restore",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Restore failed: {response.text}"
        data = response.json()
        assert data["status"] in ["live", "ended"]
        print(f"✓ Admin restored auction, new status: {data['status']}")
    
    def test_non_admin_restore_forbidden(self, user_token, removed_auction_id):
        """Non-admin should get 403"""
        response = requests.post(
            f"{BASE_URL}/api/admin/auctions/{removed_auction_id}/restore",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403
        print("✓ 403 returned for non-admin restore attempt")


class TestAdminListAllAuctions:
    """Tests for GET /api/admin/auctions with search and filter"""
    
    def test_admin_list_all(self, admin_token):
        """Admin can list all auctions"""
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Admin listed {len(data)} auctions")
    
    def test_admin_list_filter_by_status(self, admin_token):
        """Admin can filter by status"""
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"status": "live"}
        )
        assert response.status_code == 200
        data = response.json()
        for a in data:
            assert a["status"] == "live"
        print(f"✓ Admin filtered by status=live, got {len(data)} auctions")
    
    def test_admin_list_search_query(self, admin_token):
        """Admin can search by query"""
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"q": "BMW"}
        )
        assert response.status_code == 200
        print(f"✓ Admin search by query returned {len(response.json())} results")
    
    def test_non_admin_list_forbidden(self, user_token):
        """Non-admin should get 403"""
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403
        print("✓ 403 returned for non-admin list attempt")


class TestPublicAuctionsRegression:
    """Regression tests for public auction endpoints"""
    
    def test_public_list_auctions(self):
        """Public can list auctions"""
        response = requests.get(f"{BASE_URL}/api/auctions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Verify no removed/pending/rejected in public
        for a in data:
            assert a["status"] in ("live", "ended", "sold", "reserve_not_met"), f"Unexpected status: {a['status']}"
        print(f"✓ Public listing returned {len(data)} auctions with valid statuses")
    
    def test_public_get_auction(self):
        """Public can get single auction"""
        # Get first auction from list
        list_response = requests.get(f"{BASE_URL}/api/auctions")
        if not list_response.json():
            pytest.skip("No auctions available")
        auction_id = list_response.json()[0]["id"]
        
        response = requests.get(f"{BASE_URL}/api/auctions/{auction_id}")
        assert response.status_code == 200
        data = response.json()
        assert "title" in data
        assert "status" in data
        print(f"✓ Public GET auction successful: {data['title'][:40]}...")
    
    def test_public_facets(self):
        """Public can get facets"""
        response = requests.get(f"{BASE_URL}/api/auctions/facets")
        assert response.status_code == 200
        data = response.json()
        assert "makes" in data
        assert "fuels" in data
        print("✓ Public facets endpoint working")
    
    def test_public_featured(self):
        """Public can get featured auctions"""
        response = requests.get(f"{BASE_URL}/api/auctions/featured")
        assert response.status_code == 200
        print(f"✓ Featured auctions returned {len(response.json())} items")
    
    def test_public_sold(self):
        """Public can get sold auctions"""
        response = requests.get(f"{BASE_URL}/api/auctions/sold")
        assert response.status_code == 200
        print(f"✓ Sold auctions returned {len(response.json())} items")
    
    def test_ended_auctions_publicly_accessible(self):
        """Ended auctions should be publicly accessible"""
        response = requests.get(f"{BASE_URL}/api/auctions", params={"status": "ended"})
        assert response.status_code == 200
        # All returned should be ended
        for a in response.json():
            assert a["status"] == "ended"
        print(f"✓ Ended auctions publicly accessible: {len(response.json())} items")


class TestExistingAdminEndpointsRegression:
    """Regression tests for existing admin endpoints"""
    
    def test_admin_pending(self, admin_token):
        """Admin can get pending auctions"""
        response = requests.get(
            f"{BASE_URL}/api/admin/pending",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        print(f"✓ Admin pending returned {len(response.json())} items")
    
    def test_admin_sold(self, admin_token):
        """Admin can get sold auctions"""
        response = requests.get(
            f"{BASE_URL}/api/admin/sold",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        print(f"✓ Admin sold returned {len(response.json())} items")


class TestBidsCommentsRegression:
    """Regression tests for bids and comments"""
    
    def test_list_bids(self):
        """Can list bids for an auction"""
        # Get an auction
        auctions = requests.get(f"{BASE_URL}/api/auctions").json()
        if not auctions:
            pytest.skip("No auctions")
        auction_id = auctions[0]["id"]
        
        response = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/bids")
        assert response.status_code == 200
        print("✓ Bids listing working")
    
    def test_list_comments(self):
        """Can list comments for an auction"""
        auctions = requests.get(f"{BASE_URL}/api/auctions").json()
        if not auctions:
            pytest.skip("No auctions")
        auction_id = auctions[0]["id"]
        
        response = requests.get(f"{BASE_URL}/api/auctions/{auction_id}/comments")
        assert response.status_code == 200
        print("✓ Comments listing working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
