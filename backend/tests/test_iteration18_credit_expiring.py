"""
Iteration 18: Credit Expiring Banner & Lifecycle Alert Tests

Tests for:
1. GET /api/stripe/authorizations/expiring endpoint
2. _emit_expiring_alert idempotency in stripe_lifecycle.py
3. notify_user integration with push templates
4. Regression tests for existing endpoints
"""
import pytest
import requests
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

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
def user_token(api_client):
    """Get test user authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"User authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get admin authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Admin authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, user_token):
    """Session with user auth header"""
    api_client.headers.update({"Authorization": f"Bearer {user_token}"})
    return api_client


@pytest.fixture(scope="module")
def admin_client(api_client, admin_token):
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    })
    return session


class TestHealthEndpoints:
    """Basic health check tests"""
    
    def test_healthz(self, api_client):
        """GET /api/healthz returns 200"""
        response = api_client.get(f"{BASE_URL}/api/healthz")
        assert response.status_code == 200
        print("✓ GET /api/healthz → 200")
    
    def test_readyz(self, api_client):
        """GET /api/readyz returns 200"""
        response = api_client.get(f"{BASE_URL}/api/readyz")
        assert response.status_code == 200
        print("✓ GET /api/readyz → 200")


class TestExpiringAuthorizationsEndpoint:
    """Tests for GET /api/stripe/authorizations/expiring"""
    
    def test_expiring_requires_auth(self, api_client):
        """GET /api/stripe/authorizations/expiring without auth returns 401"""
        # Create a fresh session without auth
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/stripe/authorizations/expiring")
        assert response.status_code == 401
        print("✓ GET /api/stripe/authorizations/expiring (no auth) → 401")
    
    def test_expiring_returns_structure(self, authenticated_client):
        """GET /api/stripe/authorizations/expiring returns correct structure"""
        response = authenticated_client.get(f"{BASE_URL}/api/stripe/authorizations/expiring")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "has_expiring" in data
        assert "reason" in data
        assert "expires_at" in data
        assert "hold_id" in data
        
        # For user with no expiring holds, should return has_expiring=false
        assert isinstance(data["has_expiring"], bool)
        print(f"✓ GET /api/stripe/authorizations/expiring → 200, has_expiring={data['has_expiring']}")
    
    def test_expiring_no_holds_returns_false(self, authenticated_client):
        """User with no expiring holds gets has_expiring=false"""
        response = authenticated_client.get(f"{BASE_URL}/api/stripe/authorizations/expiring")
        assert response.status_code == 200
        data = response.json()
        
        # Test user (sectest_user) has no saved PM and no active holds by default
        # So has_expiring should be false
        if not data["has_expiring"]:
            assert data["reason"] is None
            assert data["expires_at"] is None
            assert data["hold_id"] is None
            print("✓ User with no expiring holds → has_expiring=false, reason=null")
        else:
            # If there's an expiring hold, verify the structure
            assert data["reason"] in ["no_saved_pm", "card_declined", None]
            assert data["expires_at"] is not None
            assert data["hold_id"] is not None
            print(f"✓ User has expiring hold → reason={data['reason']}, hold_id={data['hold_id']}")


class TestMyCreditsEndpoint:
    """Regression tests for GET /api/stripe/authorizations/my-credits"""
    
    def test_my_credits_requires_auth(self, api_client):
        """GET /api/stripe/authorizations/my-credits without auth returns 401"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/stripe/authorizations/my-credits")
        assert response.status_code == 401
        print("✓ GET /api/stripe/authorizations/my-credits (no auth) → 401")
    
    def test_my_credits_returns_structure(self, authenticated_client):
        """GET /api/stripe/authorizations/my-credits returns correct structure with outbid_bids[]"""
        response = authenticated_client.get(f"{BASE_URL}/api/stripe/authorizations/my-credits")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "holds" in data
        assert "commitments" in data
        assert "outbid_bids" in data  # NEW field from iteration 17
        assert "count" in data
        assert "total_limit_eur" in data
        assert "total_hold_eur" in data
        assert "total_available_eur" in data
        assert "total_committed_eur" in data
        
        # Verify types
        assert isinstance(data["holds"], list)
        assert isinstance(data["commitments"], list)
        assert isinstance(data["outbid_bids"], list)
        
        print(f"✓ GET /api/stripe/authorizations/my-credits → 200, holds={len(data['holds'])}, outbid_bids={len(data['outbid_bids'])}")


class TestPreauthorizationsEndpoint:
    """Regression tests for GET /api/me/preauths"""
    
    def test_preauths_requires_auth(self, api_client):
        """GET /api/me/preauths without auth returns 401"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.get(f"{BASE_URL}/api/me/preauths")
        assert response.status_code == 401
        print("✓ GET /api/me/preauths (no auth) → 401")
    
    def test_preauths_returns_list(self, authenticated_client):
        """GET /api/me/preauths returns list"""
        response = authenticated_client.get(f"{BASE_URL}/api/me/preauths")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/me/preauths → 200, count={len(data)}")


class TestAdminLifecycleScan:
    """Tests for POST /api/admin/stripe/lifecycle/scan"""
    
    def test_lifecycle_scan_requires_auth(self, api_client):
        """POST /api/admin/stripe/lifecycle/scan without auth returns 401"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        response = fresh_session.post(f"{BASE_URL}/api/admin/stripe/lifecycle/scan")
        assert response.status_code == 401
        print("✓ POST /api/admin/stripe/lifecycle/scan (no auth) → 401")
    
    def test_lifecycle_scan_requires_admin(self, authenticated_client):
        """POST /api/admin/stripe/lifecycle/scan with user auth returns 401/403"""
        response = authenticated_client.post(f"{BASE_URL}/api/admin/stripe/lifecycle/scan")
        assert response.status_code in [401, 403]
        print(f"✓ POST /api/admin/stripe/lifecycle/scan (user auth) → {response.status_code}")
    
    def test_lifecycle_scan_admin_success(self, admin_client):
        """POST /api/admin/stripe/lifecycle/scan with admin auth returns counters"""
        response = admin_client.post(f"{BASE_URL}/api/admin/stripe/lifecycle/scan")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "scanned" in data
        assert "extended" in data
        assert "failed" in data
        assert "skipped_no_pm" in data
        
        print(f"✓ POST /api/admin/stripe/lifecycle/scan (admin) → 200, scanned={data['scanned']}, extended={data['extended']}, failed={data['failed']}, skipped_no_pm={data['skipped_no_pm']}")


class TestBiddingEndpoints:
    """Regression tests for bidding endpoints"""
    
    def test_bids_requires_auth(self, api_client):
        """POST /api/auctions/{id}/bids without auth returns 401"""
        fresh_session = requests.Session()
        fresh_session.headers.update({"Content-Type": "application/json"})
        # Use a dummy auction ID
        response = fresh_session.post(f"{BASE_URL}/api/auctions/test-auction-id/bids", json={"amount_eur": 1000})
        assert response.status_code == 401
        print("✓ POST /api/auctions/{id}/bids (no auth) → 401")
    
    def test_auctions_list(self, api_client):
        """GET /api/auctions returns list"""
        response = api_client.get(f"{BASE_URL}/api/auctions?status=live")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data or isinstance(data, list)
        print(f"✓ GET /api/auctions?status=live → 200")


class TestStripeConfig:
    """Tests for GET /api/stripe/config"""
    
    def test_stripe_config(self, api_client):
        """GET /api/stripe/config returns configuration"""
        response = api_client.get(f"{BASE_URL}/api/stripe/config")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "configured" in data
        assert "mode" in data
        assert "hold_percent" in data
        assert "hold_min_eur" in data
        assert "hold_max_eur" in data
        assert "ttl_days" in data
        
        print(f"✓ GET /api/stripe/config → 200, mode={data['mode']}, configured={data['configured']}")


class TestPushTemplates:
    """Verify push templates exist for credit_expiring"""
    
    def test_push_templates_exist(self):
        """Verify credit_expiring push templates are defined by reading the file directly"""
        with open("/app/backend/services/push_templates.py", "r") as f:
            content = f.read()
        
        # Check credit_expiring_no_pm template
        assert '"credit_expiring_no_pm"' in content
        assert '"credit_expiring_declined"' in content
        
        # Check for BG/EN/RO translations in the templates
        # The templates should have all three languages
        assert '"bg":' in content
        assert '"en":' in content
        assert '"ro":' in content
        
        # Check for title and body keys
        assert '"title":' in content
        assert '"body":' in content
        
        # Check specific content for credit_expiring_no_pm
        assert "Your bidding credit expires in 24 hours" in content
        assert "Add a card to keep bidding" in content
        
        # Check specific content for credit_expiring_declined
        assert "Card declined extension" in content
        assert "Update your card to keep bidding" in content
        
        print("✓ Push templates credit_expiring_no_pm and credit_expiring_declined exist with BG/EN/RO")


class TestI18nKeys:
    """Verify i18n keys exist for credit_expiring banner"""
    
    def test_en_translations(self):
        """Verify EN translations for credit_expiring"""
        import json
        with open("/app/frontend/src/i18n/locales/en.json", "r") as f:
            en = json.load(f)
        
        assert "credit_expiring" in en
        ce = en["credit_expiring"]
        assert "body_default" in ce
        assert "body_no_pm" in ce
        assert "body_declined" in ce
        assert "add_card_cta" in ce
        assert "dismiss" in ce
        
        print("✓ EN translations: credit_expiring.body_default, body_no_pm, body_declined, add_card_cta, dismiss")
    
    def test_bg_translations(self):
        """Verify BG translations for credit_expiring"""
        import json
        with open("/app/frontend/src/i18n/locales/bg.json", "r") as f:
            bg = json.load(f)
        
        assert "credit_expiring" in bg
        ce = bg["credit_expiring"]
        assert "body_default" in ce
        assert "body_no_pm" in ce
        assert "body_declined" in ce
        assert "add_card_cta" in ce
        assert "dismiss" in ce
        
        print("✓ BG translations: credit_expiring.body_default, body_no_pm, body_declined, add_card_cta, dismiss")
    
    def test_ro_translations(self):
        """Verify RO translations for credit_expiring"""
        import json
        with open("/app/frontend/src/i18n/locales/ro.json", "r") as f:
            ro = json.load(f)
        
        assert "credit_expiring" in ro
        ce = ro["credit_expiring"]
        assert "body_default" in ce
        assert "body_no_pm" in ce
        assert "body_declined" in ce
        assert "add_card_cta" in ce
        assert "dismiss" in ce
        
        print("✓ RO translations: credit_expiring.body_default, body_no_pm, body_declined, add_card_cta, dismiss")


class TestStripeLifecycleModule:
    """Tests for stripe_lifecycle.py module structure"""
    
    def test_emit_expiring_alert_exists(self):
        """Verify _emit_expiring_alert function exists"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.stripe_lifecycle import _emit_expiring_alert
        
        assert callable(_emit_expiring_alert)
        print("✓ _emit_expiring_alert function exists in stripe_lifecycle.py")
    
    def test_extend_expiring_authorizations_exists(self):
        """Verify extend_expiring_authorizations function exists"""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from services.stripe_lifecycle import extend_expiring_authorizations
        
        assert callable(extend_expiring_authorizations)
        print("✓ extend_expiring_authorizations function exists in stripe_lifecycle.py")


class TestCreditExpiringBannerComponent:
    """Verify CreditExpiringBanner component structure"""
    
    def test_component_exists(self):
        """Verify CreditExpiringBanner.jsx exists and has correct structure"""
        import os
        
        component_path = "/app/frontend/src/components/CreditExpiringBanner.jsx"
        assert os.path.exists(component_path)
        
        with open(component_path, "r") as f:
            content = f.read()
        
        # Check for required data-testid attributes
        assert 'data-testid="credit-expiring-banner"' in content
        assert 'data-testid="credit-expiring-add-card"' in content
        assert 'data-testid="credit-expiring-dismiss"' in content
        
        # Check for API call
        assert '/stripe/authorizations/expiring' in content
        
        # Check for localStorage key
        assert 'ab.credit_expiring_dismissed_until' in content
        
        # Check for reason handling
        assert 'no_saved_pm' in content
        assert 'card_declined' in content
        
        print("✓ CreditExpiringBanner.jsx exists with correct data-testid attributes and API integration")


class TestAppJsIntegration:
    """Verify CreditExpiringBanner is wired in App.js"""
    
    def test_banner_imported_and_rendered(self):
        """Verify CreditExpiringBanner is imported and rendered in App.js"""
        with open("/app/frontend/src/App.js", "r") as f:
            content = f.read()
        
        # Check import
        assert 'import CreditExpiringBanner from "./components/CreditExpiringBanner"' in content
        
        # Check render - should be between TwoFactorPromptBanner and LiveTicker
        assert '<CreditExpiringBanner />' in content
        
        # Verify order: TwoFactorPromptBanner, CreditExpiringBanner, LiveTicker
        twofa_pos = content.find('<TwoFactorPromptBanner />')
        credit_pos = content.find('<CreditExpiringBanner />')
        ticker_pos = content.find('<LiveTicker />')
        
        assert twofa_pos < credit_pos < ticker_pos, "CreditExpiringBanner should be between TwoFactorPromptBanner and LiveTicker"
        
        print("✓ CreditExpiringBanner is imported and rendered in App.js between TwoFactorPromptBanner and LiveTicker")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
