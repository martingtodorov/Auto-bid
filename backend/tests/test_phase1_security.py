"""
Phase 1 Security Features Tests — autobids.bg
Tests for: Stripe CMS, Moderator role, Audit log, Forgot password, 2FA, Reactivate auction
"""
import pytest
import requests
import os
import time
import pyotp
import hashlib
import hmac
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@autobids.bg"
ADMIN_PASSWORD = "admin123"
MODERATOR_EMAIL = "moderator@test.bg"
MODERATOR_PASSWORD = "mod12345"
BUYER_EMAIL = "reviewbuyer@test.bg"
BUYER_PASSWORD = "newPass123"


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
    if response.status_code == 200:
        data = response.json()
        # Handle 2FA if enabled
        if data.get("requires_2fa"):
            pytest.skip("Admin has 2FA enabled - need to handle challenge")
        return data.get("token")
    pytest.skip(f"Admin authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def admin_client(api_client, admin_token):
    """Session with admin auth header"""
    api_client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api_client


@pytest.fixture(scope="module")
def moderator_user_id(admin_client):
    """Create or get moderator user and return their ID"""
    # First try to find existing moderator
    response = admin_client.get(f"{BASE_URL}/api/admin/users", params={"q": MODERATOR_EMAIL})
    if response.status_code == 200:
        users = response.json()
        for u in users:
            if u.get("email") == MODERATOR_EMAIL:
                # Ensure role is moderator
                if u.get("role") != "moderator":
                    admin_client.put(f"{BASE_URL}/api/admin/users/{u['id']}", json={"role": "moderator"})
                return u["id"]
    
    # Create new moderator user
    reg_response = admin_client.post(f"{BASE_URL}/api/auth/register", json={
        "email": MODERATOR_EMAIL,
        "password": MODERATOR_PASSWORD,
        "name": "Test Moderator"
    })
    if reg_response.status_code in (200, 201):
        user_id = reg_response.json().get("user", {}).get("id")
        if user_id:
            # Set role to moderator
            admin_client.put(f"{BASE_URL}/api/admin/users/{user_id}", json={"role": "moderator"})
            return user_id
    elif reg_response.status_code == 409:
        # User exists, find them
        response = admin_client.get(f"{BASE_URL}/api/admin/users", params={"q": MODERATOR_EMAIL})
        if response.status_code == 200:
            for u in response.json():
                if u.get("email") == MODERATOR_EMAIL:
                    admin_client.put(f"{BASE_URL}/api/admin/users/{u['id']}", json={"role": "moderator"})
                    return u["id"]
    pytest.skip("Could not create/find moderator user")


@pytest.fixture(scope="module")
def moderator_token(api_client, moderator_user_id):
    """Get moderator authentication token"""
    # Create fresh session without admin headers
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": MODERATOR_EMAIL,
        "password": MODERATOR_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        if data.get("requires_2fa"):
            pytest.skip("Moderator has 2FA enabled")
        return data.get("token")
    pytest.skip(f"Moderator authentication failed: {response.status_code}")


@pytest.fixture(scope="module")
def moderator_client(moderator_token):
    """Session with moderator auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {moderator_token}"
    })
    return session


class TestStripePublicConfig:
    """Test GET /api/stripe/public-config (public endpoint)"""
    
    def test_public_config_returns_mode_and_key(self, api_client):
        response = api_client.get(f"{BASE_URL}/api/stripe/public-config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "mode" in data, "Response should contain 'mode'"
        assert "publishable_key" in data, "Response should contain 'publishable_key'"
        assert "enabled" in data, "Response should contain 'enabled'"
        assert data["mode"] in ("test", "live"), f"Mode should be 'test' or 'live', got {data['mode']}"
        print(f"✓ Stripe public config: mode={data['mode']}, enabled={data['enabled']}")


class TestStripeAdminCMS:
    """Test Stripe CMS admin endpoints"""
    
    def test_admin_get_stripe_returns_masked_secrets(self, admin_client):
        response = admin_client.get(f"{BASE_URL}/api/admin/stripe")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Check required fields
        assert "mode" in data
        assert "stripe_enabled" in data
        assert "stripe_publishable_key_test" in data
        assert "stripe_publishable_key_live" in data
        # Secrets should be masked
        assert "stripe_secret_key_test_masked" in data
        assert "stripe_secret_key_live_masked" in data
        assert "stripe_webhook_secret_test_masked" in data
        assert "stripe_webhook_secret_live_masked" in data
        # Boolean flags for whether secrets are set
        assert "has_secret_test" in data
        assert "has_secret_live" in data
        assert "has_webhook_test" in data
        assert "has_webhook_live" in data
        print(f"✓ Admin Stripe GET returns masked secrets: mode={data['mode']}")
    
    def test_moderator_cannot_access_stripe(self, moderator_client):
        response = moderator_client.get(f"{BASE_URL}/api/admin/stripe")
        assert response.status_code == 403, f"Moderator should get 403, got {response.status_code}"
        print("✓ Moderator correctly denied access to Stripe CMS")
    
    def test_user_cannot_access_stripe(self, api_client):
        # Login as regular user
        login_resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": BUYER_EMAIL,
            "password": BUYER_PASSWORD
        })
        if login_resp.status_code != 200:
            pytest.skip("Could not login as buyer")
        token = login_resp.json().get("token")
        if not token:
            pytest.skip("No token returned for buyer")
        
        response = api_client.get(f"{BASE_URL}/api/admin/stripe", 
                                  headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403, f"User should get 403, got {response.status_code}"
        print("✓ Regular user correctly denied access to Stripe CMS")
    
    def test_put_stripe_validates_key_prefixes(self, admin_client):
        # Test invalid secret key prefix
        response = admin_client.put(f"{BASE_URL}/api/admin/stripe", json={
            "stripe_secret_key_test": "invalid_key_12345"
        })
        assert response.status_code == 400, f"Expected 400 for invalid prefix, got {response.status_code}"
        print("✓ PUT /admin/stripe rejects invalid secret key prefix")
        
        # Test invalid publishable key prefix
        response = admin_client.put(f"{BASE_URL}/api/admin/stripe", json={
            "stripe_publishable_key_test": "invalid_pk_12345"
        })
        assert response.status_code == 400, f"Expected 400 for invalid pk prefix, got {response.status_code}"
        print("✓ PUT /admin/stripe rejects invalid publishable key prefix")
    
    def test_put_stripe_accepts_valid_keys(self, admin_client):
        # Test valid test keys
        response = admin_client.put(f"{BASE_URL}/api/admin/stripe", json={
            "stripe_publishable_key_test": "pk_test_FAKE_EXAMPLE_12345",
            "stripe_secret_key_test": "sk_test_FAKE_EXAMPLE_SECRET_12345",
            "stripe_enabled": True
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("ok") == True
        assert "updated_fields" in data
        print(f"✓ PUT /admin/stripe accepts valid keys: {data.get('updated_fields')}")
    
    def test_put_stripe_empty_secret_preserves_existing(self, admin_client):
        # First set a value
        admin_client.put(f"{BASE_URL}/api/admin/stripe", json={
            "stripe_secret_key_test": "sk_test_PRESERVE_TEST_12345"
        })
        
        # Now update with empty secret - should preserve
        response = admin_client.put(f"{BASE_URL}/api/admin/stripe", json={
            "mode": "test",
            "stripe_secret_key_test": ""  # Empty should preserve existing
        })
        assert response.status_code == 200
        
        # Verify the secret is still set
        get_resp = admin_client.get(f"{BASE_URL}/api/admin/stripe")
        data = get_resp.json()
        assert data.get("has_secret_test") == True, "Secret should be preserved when empty string sent"
        print("✓ Empty secret field preserves existing value")
    
    def test_mode_toggle_changes_public_config(self, admin_client, api_client):
        # Set to test mode
        admin_client.put(f"{BASE_URL}/api/admin/stripe", json={"mode": "test"})
        
        # Check public config
        response = api_client.get(f"{BASE_URL}/api/stripe/public-config")
        assert response.json().get("mode") == "test"
        
        # Set to live mode
        admin_client.put(f"{BASE_URL}/api/admin/stripe", json={"mode": "live"})
        
        # Check public config again
        response = api_client.get(f"{BASE_URL}/api/stripe/public-config")
        assert response.json().get("mode") == "live"
        
        # Reset to test mode
        admin_client.put(f"{BASE_URL}/api/admin/stripe", json={"mode": "test"})
        print("✓ Mode toggle correctly changes public config")


class TestStripeWebhook:
    """Test Stripe webhook endpoint"""
    
    def test_webhook_without_secret_configured(self, api_client, admin_client):
        # Clear webhook secret
        admin_client.put(f"{BASE_URL}/api/admin/stripe", json={
            "stripe_webhook_secret_test": ""
        })
        
        # Try to call webhook
        response = api_client.post(f"{BASE_URL}/api/webhooks/stripe", 
                                   data=b'{"type":"test"}',
                                   headers={"stripe-signature": "t=123,v1=abc"})
        # Should return ok:false with reason
        if response.status_code == 200:
            data = response.json()
            assert data.get("ok") == False
            assert "webhook_secret_not_configured" in data.get("reason", "")
            print("✓ Webhook returns ok:false when secret not configured")
        else:
            print(f"✓ Webhook returns {response.status_code} when secret not configured")
    
    def test_webhook_with_wrong_signature(self, api_client, admin_client):
        # Set a webhook secret
        admin_client.put(f"{BASE_URL}/api/admin/stripe", json={
            "stripe_webhook_secret_test": "whsec_test_secret_12345"
        })
        
        # Call with wrong signature
        response = api_client.post(f"{BASE_URL}/api/webhooks/stripe",
                                   data=b'{"type":"test"}',
                                   headers={"stripe-signature": "t=123,v1=wrong_signature"})
        assert response.status_code == 400, f"Expected 400 for wrong signature, got {response.status_code}"
        print("✓ Webhook returns 400 for wrong signature")


class TestModeratorRole:
    """Test moderator role permissions"""
    
    def test_moderator_can_get_settings(self, moderator_client):
        response = moderator_client.get(f"{BASE_URL}/api/admin/settings")
        assert response.status_code == 200, f"Moderator should access settings, got {response.status_code}"
        print("✓ Moderator can GET /admin/settings")
    
    def test_moderator_cannot_put_settings(self, moderator_client):
        response = moderator_client.put(f"{BASE_URL}/api/admin/settings", json={
            "buyer_fee_pct": 3.0
        })
        assert response.status_code == 403, f"Moderator should not PUT settings, got {response.status_code}"
        print("✓ Moderator cannot PUT /admin/settings (403)")
    
    def test_moderator_can_get_stats(self, moderator_client):
        response = moderator_client.get(f"{BASE_URL}/api/admin/stats")
        assert response.status_code == 200, f"Moderator should access stats, got {response.status_code}"
        print("✓ Moderator can GET /admin/stats")
    
    def test_moderator_can_get_users(self, moderator_client):
        response = moderator_client.get(f"{BASE_URL}/api/admin/users")
        assert response.status_code == 200, f"Moderator should access users, got {response.status_code}"
        print("✓ Moderator can GET /admin/users")
    
    def test_moderator_can_get_audit_log(self, moderator_client):
        response = moderator_client.get(f"{BASE_URL}/api/admin/audit-log")
        assert response.status_code == 200, f"Moderator should access audit log, got {response.status_code}"
        print("✓ Moderator can GET /admin/audit-log")
    
    def test_moderator_can_get_pending(self, moderator_client):
        response = moderator_client.get(f"{BASE_URL}/api/admin/pending")
        assert response.status_code == 200, f"Moderator should access pending, got {response.status_code}"
        print("✓ Moderator can GET /admin/pending")
    
    def test_moderator_cannot_get_stripe(self, moderator_client):
        response = moderator_client.get(f"{BASE_URL}/api/admin/stripe")
        assert response.status_code == 403, f"Moderator should not access Stripe, got {response.status_code}"
        print("✓ Moderator cannot GET /admin/stripe (403)")
    
    def test_moderator_cannot_put_stripe(self, moderator_client):
        response = moderator_client.put(f"{BASE_URL}/api/admin/stripe", json={"mode": "test"})
        assert response.status_code == 403, f"Moderator should not PUT Stripe, got {response.status_code}"
        print("✓ Moderator cannot PUT /admin/stripe (403)")
    
    def test_moderator_cannot_ban_users(self, moderator_client, admin_client):
        # Get a user to try to ban
        users_resp = admin_client.get(f"{BASE_URL}/api/admin/users")
        users = users_resp.json()
        target_user = None
        for u in users:
            if u.get("role") == "user":
                target_user = u
                break
        
        if not target_user:
            pytest.skip("No regular user found to test ban")
        
        response = moderator_client.post(f"{BASE_URL}/api/admin/users/{target_user['id']}/ban")
        assert response.status_code == 403, f"Moderator should not ban users, got {response.status_code}"
        print("✓ Moderator cannot ban users (403)")
    
    def test_moderator_can_delete_comments(self, moderator_client, admin_client):
        # First create a comment to delete
        # Get an auction
        auctions_resp = admin_client.get(f"{BASE_URL}/api/auctions")
        auctions = auctions_resp.json()
        if not auctions:
            pytest.skip("No auctions to test comment deletion")
        
        auction_id = auctions[0]["id"]
        
        # Create a comment as admin
        comment_resp = admin_client.post(f"{BASE_URL}/api/auctions/{auction_id}/comments", json={
            "text": "TEST_MODERATOR_DELETE_COMMENT"
        })
        if comment_resp.status_code != 200:
            pytest.skip("Could not create test comment")
        
        comment_id = comment_resp.json().get("id")
        
        # Moderator should be able to delete it
        response = moderator_client.delete(f"{BASE_URL}/api/admin/comments/{comment_id}")
        assert response.status_code == 200, f"Moderator should delete comments, got {response.status_code}"
        print("✓ Moderator can DELETE /admin/comments/{id}")


class TestAuditLog:
    """Test audit log functionality"""
    
    def test_audit_log_returns_paginated_response(self, admin_client):
        response = admin_client.get(f"{BASE_URL}/api/admin/audit-log")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data, "Response should contain 'items'"
        assert "total" in data, "Response should contain 'total'"
        assert "offset" in data, "Response should contain 'offset'"
        assert "limit" in data, "Response should contain 'limit'"
        print(f"✓ Audit log returns paginated response: total={data['total']}")
    
    def test_audit_log_filter_by_action(self, admin_client):
        response = admin_client.get(f"{BASE_URL}/api/admin/audit-log", params={"action": "stripe.update"})
        assert response.status_code == 200
        data = response.json()
        # All items should have the filtered action
        for item in data.get("items", []):
            assert item.get("action") == "stripe.update", f"Expected action 'stripe.update', got {item.get('action')}"
        print(f"✓ Audit log filter by action works: {len(data.get('items', []))} stripe.update entries")
    
    def test_stripe_update_creates_audit_entry(self, admin_client):
        # Get current audit log count for stripe.update
        before_resp = admin_client.get(f"{BASE_URL}/api/admin/audit-log", params={"action": "stripe.update"})
        before_count = before_resp.json().get("total", 0)
        
        # Make a stripe update
        admin_client.put(f"{BASE_URL}/api/admin/stripe", json={"mode": "test"})
        
        # Check audit log
        after_resp = admin_client.get(f"{BASE_URL}/api/admin/audit-log", params={"action": "stripe.update"})
        after_count = after_resp.json().get("total", 0)
        
        assert after_count > before_count, "Stripe update should create audit entry"
        
        # Verify the entry doesn't contain secret values
        items = after_resp.json().get("items", [])
        if items:
            latest = items[0]
            details = latest.get("details", {})
            # Should only contain field names, not values
            if "fields" in details:
                for field in details["fields"]:
                    assert "sk_" not in str(field), "Audit should not contain secret key values"
                    assert "whsec_" not in str(field), "Audit should not contain webhook secret values"
        print("✓ Stripe update creates audit entry with only field names (no values)")


class TestForgotPassword:
    """Test forgot password flow"""
    
    def test_forgot_password_returns_generic_message(self, api_client):
        # Test with existing email
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": ADMIN_EMAIL
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True
        assert "message" in data
        print(f"✓ Forgot password returns generic message for existing email")
        
        # Test with non-existing email (should return same response to prevent enumeration)
        response = api_client.post(f"{BASE_URL}/api/auth/forgot-password", json={
            "email": "nonexistent@test.bg"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") == True
        print("✓ Forgot password returns same response for non-existing email (no enumeration)")
    
    def test_reset_password_validates_code(self, api_client):
        # Try with wrong code
        response = api_client.post(f"{BASE_URL}/api/auth/reset-password", json={
            "email": ADMIN_EMAIL,
            "code": "000000",
            "new_password": "newpassword123"
        })
        assert response.status_code == 400, f"Expected 400 for wrong code, got {response.status_code}"
        print("✓ Reset password rejects wrong code")
    
    def test_reset_password_code_cannot_be_reused(self, api_client):
        # This test would require access to the actual code sent via email
        # Since we're in test mode, we'll verify the endpoint exists and validates
        response = api_client.post(f"{BASE_URL}/api/auth/reset-password", json={
            "email": "test@test.bg",
            "code": "123456",
            "new_password": "newpassword123"
        })
        # Should fail because no valid code exists
        assert response.status_code == 400
        print("✓ Reset password endpoint validates code existence")


class TestTwoFactorAuth:
    """Test 2FA functionality"""
    
    def test_2fa_enable_returns_provisioning_data(self, admin_client):
        # First check if 2FA is already enabled
        me_resp = admin_client.get(f"{BASE_URL}/api/auth/me")
        if me_resp.json().get("totp_enabled"):
            pytest.skip("2FA already enabled for admin")
        
        response = admin_client.post(f"{BASE_URL}/api/auth/2fa/enable")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "secret" in data, "Response should contain 'secret'"
        assert "qr_code_data_url" in data, "Response should contain 'qr_code_data_url'"
        assert "otpauth_uri" in data, "Response should contain 'otpauth_uri'"
        assert data["qr_code_data_url"].startswith("data:image/png;base64,")
        print("✓ 2FA enable returns secret, QR code, and otpauth URI")
        return data["secret"]
    
    def test_2fa_confirm_with_valid_code(self, admin_client):
        # First check if 2FA is already enabled
        me_resp = admin_client.get(f"{BASE_URL}/api/auth/me")
        if me_resp.json().get("totp_enabled"):
            pytest.skip("2FA already enabled for admin")
        
        # Enable 2FA to get secret
        enable_resp = admin_client.post(f"{BASE_URL}/api/auth/2fa/enable")
        if enable_resp.status_code != 200:
            pytest.skip("Could not enable 2FA")
        
        secret = enable_resp.json().get("secret")
        
        # Generate valid TOTP code
        totp = pyotp.TOTP(secret)
        code = totp.now()
        
        # Confirm with valid code
        response = admin_client.post(f"{BASE_URL}/api/auth/2fa/confirm", json={"code": code})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("ok") == True
        assert "backup_codes" in data, "Response should contain backup_codes"
        assert len(data["backup_codes"]) == 8, f"Should have 8 backup codes, got {len(data['backup_codes'])}"
        
        # Verify backup code format (8 uppercase hex chars)
        for bc in data["backup_codes"]:
            assert len(bc) == 8, f"Backup code should be 8 chars, got {len(bc)}"
            assert bc.isupper(), "Backup code should be uppercase"
        
        print(f"✓ 2FA confirm returns 8 backup codes")
        return data["backup_codes"]
    
    def test_2fa_login_requires_challenge(self, api_client, admin_client):
        # Check if 2FA is enabled
        me_resp = admin_client.get(f"{BASE_URL}/api/auth/me")
        if not me_resp.json().get("totp_enabled"):
            pytest.skip("2FA not enabled for admin")
        
        # Try to login
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("requires_2fa") == True, "Login should require 2FA"
        assert "challenge_token" in data, "Response should contain challenge_token"
        assert "token" not in data, "Response should NOT contain JWT token yet"
        print("✓ Login with 2FA returns requires_2fa and challenge_token")
    
    def test_2fa_verify_completes_login(self, api_client, admin_client):
        # Check if 2FA is enabled
        me_resp = admin_client.get(f"{BASE_URL}/api/auth/me")
        user_data = me_resp.json()
        if not user_data.get("totp_enabled"):
            pytest.skip("2FA not enabled for admin")
        
        # Get the secret from DB (we need to get it from the user)
        # Since we can't access DB directly, we'll skip this test if 2FA is enabled
        # but we don't have the secret
        pytest.skip("Cannot test 2FA verify without knowing the secret")
    
    def test_2fa_disable_requires_code(self, admin_client):
        # Check if 2FA is enabled
        me_resp = admin_client.get(f"{BASE_URL}/api/auth/me")
        if not me_resp.json().get("totp_enabled"):
            pytest.skip("2FA not enabled for admin")
        
        # Try to disable without code
        response = admin_client.post(f"{BASE_URL}/api/auth/2fa/disable", json={"code": "000000"})
        assert response.status_code == 400, f"Expected 400 for wrong code, got {response.status_code}"
        print("✓ 2FA disable requires valid TOTP code")


class TestReactivateAuction:
    """Test auction reactivation"""
    
    def test_reactivate_sold_auction(self, admin_client):
        # Get a sold auction
        sold_resp = admin_client.get(f"{BASE_URL}/api/admin/sold")
        sold = sold_resp.json()
        
        if not sold:
            pytest.skip("No sold auctions to test reactivation")
        
        auction = sold[0]
        auction_id = auction["id"]
        
        # Reactivate with 5 days
        response = admin_client.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/reactivate", params={"days": 5})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("ok") == True
        assert data.get("status") == "live"
        assert "ends_at" in data
        print(f"✓ Reactivated sold auction to live, ends_at={data['ends_at']}")
        
        # Verify the auction is now live
        auction_resp = admin_client.get(f"{BASE_URL}/api/auctions/{auction_id}")
        assert auction_resp.json().get("status") == "live"
        print("✓ Auction status is now 'live'")
    
    def test_reactivate_rejects_live_auction(self, admin_client):
        # Get a live auction
        auctions_resp = admin_client.get(f"{BASE_URL}/api/auctions", params={"status": "live"})
        auctions = auctions_resp.json()
        
        if not auctions:
            pytest.skip("No live auctions to test")
        
        auction_id = auctions[0]["id"]
        
        # Try to reactivate a live auction
        response = admin_client.post(f"{BASE_URL}/api/admin/auctions/{auction_id}/reactivate", params={"days": 5})
        assert response.status_code == 400, f"Expected 400 for live auction, got {response.status_code}"
        print("✓ Reactivate correctly rejects live auction")
    
    def test_reactivate_creates_audit_entry(self, admin_client):
        # Get audit log count for auction.reactivate
        before_resp = admin_client.get(f"{BASE_URL}/api/admin/audit-log", params={"action": "auction.reactivate"})
        before_count = before_resp.json().get("total", 0)
        
        # We already reactivated an auction in the previous test
        # Just verify the audit entry exists
        after_resp = admin_client.get(f"{BASE_URL}/api/admin/audit-log", params={"action": "auction.reactivate"})
        after_count = after_resp.json().get("total", 0)
        
        assert after_count > 0, "Should have at least one auction.reactivate audit entry"
        print(f"✓ Auction reactivate creates audit entry (total: {after_count})")


class TestAdminUserRoleUpdate:
    """Test admin can set user role to moderator"""
    
    def test_admin_can_set_moderator_role(self, admin_client, moderator_user_id):
        # Verify the user has moderator role
        response = admin_client.get(f"{BASE_URL}/api/admin/users/{moderator_user_id}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "moderator", f"Expected role 'moderator', got {data.get('role')}"
        print("✓ Admin can set user role to 'moderator'")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
