"""
Phase 6 Testing: Registration T&C, Hero CMS, Seller Requests, Admin Notifications/Templates
Tests for autoandbid.com session 6 features.
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "contact@autoandbid.com"
ADMIN_PASSWORD = "admin123"
MODERATOR_EMAIL = "moderator@test.bg"
MODERATOR_PASSWORD = "mod12345"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def moderator_token():
    """Get moderator authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": MODERATOR_EMAIL,
        "password": MODERATOR_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Moderator login failed: {response.status_code} - {response.text}")


class TestRegistrationWithTerms:
    """Test registration flow with T&C acceptance"""
    
    def test_register_without_terms_returns_400(self):
        """Registration without terms_accepted should fail with 400"""
        unique_email = f"test_no_terms_{uuid.uuid4().hex[:8]}@test.bg"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Test User",
            "terms_accepted": False
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "detail" in data
        # Bulgarian error message for terms not accepted
        assert "Общите условия" in data["detail"] or "terms" in data["detail"].lower()
    
    def test_register_with_terms_succeeds(self):
        """Registration with terms_accepted=true should succeed"""
        unique_email = f"test_with_terms_{uuid.uuid4().hex[:8]}@test.bg"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Test User With Terms",
            "terms_accepted": True,
            "terms_version": "v1"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == unique_email.lower()
    
    def test_register_captures_ip_ua_timestamp(self, admin_token):
        """Verify that registration captures IP, user-agent, and timestamp in user doc"""
        unique_email = f"test_audit_{uuid.uuid4().hex[:8]}@test.bg"
        
        # Register with custom user-agent
        headers = {"User-Agent": "TestBot/1.0 (Phase6 Testing)"}
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Audit Test User",
            "terms_accepted": True,
            "terms_version": "v1"
        }, headers=headers)
        assert response.status_code == 200
        
        # Check audit log for terms acceptance
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        audit_response = requests.get(f"{BASE_URL}/api/admin/audit-log", 
                                      params={"action": "user.terms_accepted", "limit": 10},
                                      headers=admin_headers)
        assert audit_response.status_code == 200
        audit_data = audit_response.json()
        
        # Find the audit entry for our test user
        found = False
        for entry in audit_data.get("items", []):
            if entry.get("actor_email") == unique_email.lower():
                found = True
                assert "ip" in entry
                assert "user_agent" in entry
                assert "at" in entry
                assert entry.get("action") == "user.terms_accepted"
                break
        
        assert found, f"Audit log entry not found for {unique_email}"


class TestHeroCMS:
    """Test Hero CMS settings for multi-language support"""
    
    def test_public_settings_returns_hero_keys(self):
        """GET /api/settings should return hero_headline_* and hero_subtitle_* keys"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        data = response.json()
        
        # Check all 6 hero keys exist (can be empty strings)
        expected_keys = [
            "hero_headline_bg", "hero_subtitle_bg",
            "hero_headline_ro", "hero_subtitle_ro",
            "hero_headline_en", "hero_subtitle_en"
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"
    
    def test_admin_can_update_hero_settings(self, admin_token):
        """Admin can PUT hero text settings"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # Update hero settings
        test_headline_bg = f"Тест заглавие {uuid.uuid4().hex[:6]}"
        test_subtitle_bg = "Тест подзаглавие"
        
        response = requests.put(f"{BASE_URL}/api/admin/settings", json={
            "hero_headline_bg": test_headline_bg,
            "hero_subtitle_bg": test_subtitle_bg,
            "hero_headline_ro": "Test RO headline",
            "hero_subtitle_ro": "Test RO subtitle",
            "hero_headline_en": "Test EN headline",
            "hero_subtitle_en": "Test EN subtitle"
        }, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify via public settings endpoint
        verify_response = requests.get(f"{BASE_URL}/api/settings")
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data.get("hero_headline_bg") == test_headline_bg
        assert verify_data.get("hero_subtitle_bg") == test_subtitle_bg
    
    def test_hero_settings_persist_after_reload(self, admin_token):
        """Hero settings should persist across requests"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        unique_text = f"Persist test {uuid.uuid4().hex[:6]}"
        requests.put(f"{BASE_URL}/api/admin/settings", json={
            "hero_headline_en": unique_text
        }, headers=headers)
        
        # Multiple reads should return same value
        for _ in range(3):
            response = requests.get(f"{BASE_URL}/api/settings")
            assert response.status_code == 200
            assert response.json().get("hero_headline_en") == unique_text


class TestAdminNotifications:
    """Test Admin Notifications tab endpoints"""
    
    def test_get_notifications_requires_auth(self):
        """GET /api/admin/notifications requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/notifications")
        assert response.status_code == 401
    
    def test_admin_can_get_notifications(self, admin_token):
        """Admin can GET /api/admin/notifications"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/notifications", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
    
    def test_notifications_status_filter(self, admin_token):
        """Notifications can be filtered by status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        for status in ["sent", "failed", "queued"]:
            response = requests.get(f"{BASE_URL}/api/admin/notifications", 
                                   params={"status": status}, headers=headers)
            assert response.status_code == 200


class TestAdminEmailTemplates:
    """Test Admin Email Templates endpoints"""
    
    def test_get_templates_requires_auth(self):
        """GET /api/admin/email-templates requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/email-templates")
        assert response.status_code == 401
    
    def test_admin_can_get_templates(self, admin_token):
        """Admin can GET /api/admin/email-templates"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/email-templates", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    def test_admin_can_save_templates(self, admin_token):
        """Admin can PUT /api/admin/email-templates"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        test_slug = f"test_template_{uuid.uuid4().hex[:6]}"
        templates = {
            test_slug: {
                "subject": "Test Subject",
                "body": "Test body content"
            }
        }
        
        response = requests.put(f"{BASE_URL}/api/admin/email-templates", 
                               json=templates, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert test_slug in data["templates"]
    
    def test_send_test_email_endpoint(self, admin_token):
        """POST /api/admin/send-email endpoint exists"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        # This will likely fail without Resend API key, but endpoint should exist
        response = requests.post(f"{BASE_URL}/api/admin/send-email", json={
            "to": "test@example.com",
            "subject": "Test",
            "body": "Test body"
        }, headers=headers)
        # Accept 200 (success) or 500 (Resend not configured) - endpoint exists
        assert response.status_code in [200, 500], f"Unexpected status: {response.status_code}"


class TestTransactionsExport:
    """Test CSV transactions export"""
    
    def test_csv_export_requires_auth(self):
        """CSV export requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/transactions/export.csv")
        assert response.status_code == 401
    
    def test_admin_can_export_csv(self, admin_token):
        """Admin can download CSV export"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/transactions/export.csv", headers=headers)
        assert response.status_code == 200
        # Check content type is CSV
        content_type = response.headers.get("content-type", "")
        assert "text/csv" in content_type or "application/octet-stream" in content_type


class TestSellerRequestsEndpoints:
    """Test seller request endpoints"""
    
    def test_admin_seller_requests_requires_auth(self):
        """GET /api/admin/seller-requests requires authentication"""
        response = requests.get(f"{BASE_URL}/api/admin/seller-requests")
        assert response.status_code == 401
    
    def test_admin_can_list_seller_requests(self, admin_token):
        """Admin can GET /api/admin/seller-requests"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/seller-requests", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_seller_requests_status_filter(self, admin_token):
        """Seller requests can be filtered by status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        for status in ["pending", "approved", "rejected"]:
            response = requests.get(f"{BASE_URL}/api/admin/seller-requests", 
                                   params={"status": status}, headers=headers)
            assert response.status_code == 200
    
    def test_seller_requests_type_filter(self, admin_token):
        """Seller requests can be filtered by type"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        for req_type in ["promotion", "text_change"]:
            response = requests.get(f"{BASE_URL}/api/admin/seller-requests", 
                                   params={"type": req_type}, headers=headers)
            assert response.status_code == 200
    
    def test_my_seller_requests_requires_auth(self):
        """GET /api/me/seller-requests requires authentication"""
        response = requests.get(f"{BASE_URL}/api/me/seller-requests")
        assert response.status_code == 401


class TestSellerAuctionRequests:
    """Test seller auction request endpoints (promotion, text change, reorder)"""
    
    @pytest.fixture
    def seller_with_auction(self, admin_token):
        """Create a test seller with an auction for testing"""
        # Register a new seller
        unique_email = f"test_seller_{uuid.uuid4().hex[:8]}@test.bg"
        reg_response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Test Seller",
            "terms_accepted": True
        })
        if reg_response.status_code != 200:
            pytest.skip(f"Could not create test seller: {reg_response.text}")
        
        seller_token = reg_response.json()["token"]
        seller_headers = {"Authorization": f"Bearer {seller_token}"}
        
        # Create an auction
        auction_response = requests.post(f"{BASE_URL}/api/auctions", json={
            "title": f"Test Car {uuid.uuid4().hex[:6]}",
            "make": "BMW",
            "model": "M3",
            "year": 2020,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматик",
            "body_type": "Седан",
            "power_hp": 450,
            "engine_cc": 3000,
            "color": "Черен",
            "region": "София",
            "city": "София",
            "description": "Test auction for seller requests",
            "images": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"],
            "starting_bid_eur": 30000,
            "duration_days": 10,
            "contact_email": unique_email,
            "contact_phone": "+359888123456"
        }, headers=seller_headers)
        
        if auction_response.status_code != 201:
            pytest.skip(f"Could not create test auction: {auction_response.text}")
        
        auction_id = auction_response.json()["id"]
        
        # Approve the auction as admin
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        requests.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/approve", headers=admin_headers)
        
        return {
            "token": seller_token,
            "headers": seller_headers,
            "auction_id": auction_id,
            "email": unique_email
        }
    
    def test_request_promotion_requires_auth(self):
        """POST /api/auctions/{id}/request-promotion requires auth"""
        response = requests.post(f"{BASE_URL}/api/auctions/fake-id/request-promotion", json={})
        assert response.status_code == 401
    
    def test_request_text_change_requires_title_or_description(self, seller_with_auction):
        """Text change request requires at least title or description"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/{seller_with_auction['auction_id']}/request-text-change",
            json={"note": "Just a note"},
            headers=seller_with_auction["headers"]
        )
        assert response.status_code == 400
    
    def test_reorder_images_rejects_invalid_list(self, seller_with_auction):
        """Reorder images rejects list that adds/removes images"""
        response = requests.patch(
            f"{BASE_URL}/api/auctions/{seller_with_auction['auction_id']}/reorder-images",
            json={"images": ["https://example.com/new-image.jpg"]},
            headers=seller_with_auction["headers"]
        )
        assert response.status_code == 400


class TestI18nLocales:
    """Test that i18n locale files are valid"""
    
    def test_bg_json_is_valid(self):
        """bg.json should be valid JSON"""
        import json
        with open("/app/frontend/src/i18n/locales/bg.json", "r") as f:
            data = json.load(f)
        assert "nav" in data
        assert "hero" in data
        assert "auth" in data
    
    def test_ro_json_is_valid(self):
        """ro.json should be valid JSON"""
        import json
        with open("/app/frontend/src/i18n/locales/ro.json", "r") as f:
            data = json.load(f)
        assert "nav" in data
        assert "hero" in data
        assert "auth" in data
    
    def test_en_json_is_valid(self):
        """en.json should be valid JSON"""
        import json
        with open("/app/frontend/src/i18n/locales/en.json", "r") as f:
            data = json.load(f)
        assert "nav" in data
        assert "hero" in data
        assert "auth" in data


class TestRegressionBasics:
    """Basic regression tests for existing functionality"""
    
    def test_health_check(self):
        """API health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
    
    def test_public_auctions_list(self):
        """Public auctions list works"""
        response = requests.get(f"{BASE_URL}/api/auctions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_public_settings(self):
        """Public settings endpoint works"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
    
    def test_admin_login(self):
        """Admin can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data or "requires_2fa" in data
    
    def test_moderator_login(self):
        """Moderator can login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": MODERATOR_EMAIL,
            "password": MODERATOR_PASSWORD
        })
        assert response.status_code == 200
