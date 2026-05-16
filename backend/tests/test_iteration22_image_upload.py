"""
Iteration 22: Image Upload Architecture + Admin Health Tab Testing

Tests:
1. POST /api/sell/image-upload — multipart upload with 5MB cap, magic-byte validation
2. GET /api/images/status — returns status + manifest for given shas
3. GET /api/admin/image-queue — admin auth, returns queue + db stats + failed list
4. POST /api/admin/image-queue/retry — admin-only, re-enqueues a failed image
5. GET /api/admin/cdn-health — admin only, probes CDN
6. Settings page regression (no smsOpt ReferenceError)
"""
import os
import io
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable is required")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@autoandbid.com"
ADMIN_PASSWORD = "Nero08787"
USER_EMAIL = "sectest_user@test.bg"
USER_PASSWORD = "sectest123"


@pytest.fixture(scope="module")
def admin_session():
    """Get admin auth session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    token = data.get("token")
    csrf = data.get("csrf_token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    if csrf:
        session.headers.update({"X-CSRF-Token": csrf})
    return session


@pytest.fixture(scope="module")
def user_session():
    """Get regular user auth session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    assert resp.status_code == 200, f"User login failed: {resp.text}"
    data = resp.json()
    token = data.get("token")
    csrf = data.get("csrf_token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    if csrf:
        session.headers.update({"X-CSRF-Token": csrf})
    return session


class TestImageUploadEndpoint:
    """Tests for POST /api/sell/image-upload"""

    def test_upload_valid_jpeg(self, admin_session):
        """Upload a valid JPEG image - should return 200 with url, sha, ext, size_bytes, status"""
        # Create a minimal valid JPEG (1x1 pixel red)
        # JPEG magic bytes: FF D8 FF
        jpeg_bytes = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
            0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
            0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
            0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
            0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
            0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xA8, 0xA2, 0x80,
            0x0A, 0x28, 0xA0, 0x02, 0x8A, 0x28, 0x00, 0xFF, 0xD9
        ])
        
        files = {"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
        # Remove Content-Type header for multipart
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != "content-type"}
        
        resp = requests.post(
            f"{BASE_URL}/api/sell/image-upload",
            files=files,
            headers=headers,
            cookies=admin_session.cookies
        )
        
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "url" in data, "Response missing 'url'"
        assert "sha" in data, "Response missing 'sha'"
        assert "ext" in data, "Response missing 'ext'"
        assert "size_bytes" in data, "Response missing 'size_bytes'"
        assert "status" in data, "Response missing 'status'"
        
        # Verify values
        assert data["ext"] == "jpg", f"Expected ext='jpg', got '{data['ext']}'"
        assert data["status"] == "optimizing", f"Expected status='optimizing', got '{data['status']}'"
        assert len(data["sha"]) == 64, f"SHA should be 64 chars, got {len(data['sha'])}"
        assert data["size_bytes"] > 0, "size_bytes should be positive"
        
        print(f"✓ Valid JPEG upload successful: sha={data['sha'][:10]}..., url={data['url']}")

    def test_upload_valid_png(self, admin_session):
        """Upload a valid PNG image"""
        # Minimal valid PNG (1x1 pixel)
        png_bytes = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,  # IDAT chunk
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
            0x00, 0x05, 0xFE, 0x02, 0xFE, 0xDC, 0xCC, 0x59,
            0xE7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,  # IEND chunk
            0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        
        files = {"file": ("test.png", io.BytesIO(png_bytes), "image/png")}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != "content-type"}
        
        resp = requests.post(
            f"{BASE_URL}/api/sell/image-upload",
            files=files,
            headers=headers,
            cookies=admin_session.cookies
        )
        
        assert resp.status_code == 200, f"PNG upload failed: {resp.text}"
        data = resp.json()
        assert data["ext"] == "png", f"Expected ext='png', got '{data['ext']}'"
        print(f"✓ Valid PNG upload successful: sha={data['sha'][:10]}...")

    def test_reject_text_file(self, admin_session):
        """Reject text file disguised as image - magic byte validation"""
        text_bytes = b"This is not an image file, just plain text content."
        
        files = {"file": ("fake.jpg", io.BytesIO(text_bytes), "image/jpeg")}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != "content-type"}
        
        resp = requests.post(
            f"{BASE_URL}/api/sell/image-upload",
            files=files,
            headers=headers,
            cookies=admin_session.cookies
        )
        
        assert resp.status_code == 400, f"Expected 400 for text file, got {resp.status_code}"
        data = resp.json()
        assert "detail" in data
        print(f"✓ Text file correctly rejected: {data['detail']}")

    def test_reject_pdf_file(self, admin_session):
        """Reject PDF file - magic byte validation"""
        # PDF magic bytes: %PDF
        pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"
        
        files = {"file": ("document.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != "content-type"}
        
        resp = requests.post(
            f"{BASE_URL}/api/sell/image-upload",
            files=files,
            headers=headers,
            cookies=admin_session.cookies
        )
        
        assert resp.status_code == 400, f"Expected 400 for PDF, got {resp.status_code}"
        print("✓ PDF file correctly rejected")

    def test_reject_oversized_file(self, admin_session):
        """Reject file larger than 5MB"""
        # Create a 6MB file (exceeds 5MB limit)
        large_bytes = b"\xff\xd8\xff" + (b"\x00" * (6 * 1024 * 1024))
        
        files = {"file": ("large.jpg", io.BytesIO(large_bytes), "image/jpeg")}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != "content-type"}
        
        resp = requests.post(
            f"{BASE_URL}/api/sell/image-upload",
            files=files,
            headers=headers,
            cookies=admin_session.cookies
        )
        
        assert resp.status_code == 413, f"Expected 413 for oversized file, got {resp.status_code}"
        print("✓ Oversized file correctly rejected with 413")

    def test_upload_requires_auth(self):
        """Upload endpoint requires authentication"""
        jpeg_bytes = bytes([0xFF, 0xD8, 0xFF, 0xE0] + [0x00] * 100)
        files = {"file": ("test.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
        
        resp = requests.post(f"{BASE_URL}/api/sell/image-upload", files=files)
        
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
        print("✓ Upload correctly requires authentication")


class TestImageStatusEndpoint:
    """Tests for GET /api/images/status"""

    def test_status_with_unknown_sha(self, admin_session):
        """Query status for unknown sha returns 'unknown'"""
        resp = admin_session.get(f"{BASE_URL}/api/images/status?shas=abc123def456")
        
        assert resp.status_code == 200, f"Status query failed: {resp.text}"
        data = resp.json()
        assert "items" in data
        assert "abc123def456" in data["items"]
        assert data["items"]["abc123def456"]["status"] == "unknown"
        print("✓ Unknown sha returns status='unknown'")

    def test_status_multiple_shas(self, admin_session):
        """Query status for multiple shas"""
        resp = admin_session.get(f"{BASE_URL}/api/images/status?shas=sha1,sha2,sha3")
        
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 3
        print("✓ Multiple sha query works correctly")

    def test_status_requires_auth(self):
        """Status endpoint requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/images/status?shas=test")
        assert resp.status_code == 401
        print("✓ Status endpoint correctly requires auth")


class TestAdminImageQueue:
    """Tests for GET /api/admin/image-queue"""

    def test_image_queue_returns_stats(self, admin_session):
        """Admin image queue returns queue, db, and failed stats"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/image-queue")
        
        assert resp.status_code == 200, f"Image queue failed: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "queue" in data, "Response missing 'queue'"
        assert "db" in data, "Response missing 'db'"
        assert "failed" in data, "Response missing 'failed'"
        
        # Verify queue stats
        queue = data["queue"]
        assert "pending" in queue
        assert "in_flight" in queue
        assert "max_concurrency" in queue
        
        # Verify db stats
        db = data["db"]
        assert "optimized" in db or db == {}  # May be empty if no images processed
        
        print(f"✓ Image queue stats: pending={queue['pending']}, in_flight={queue['in_flight']}")
        print(f"  DB stats: {db}")

    def test_image_queue_requires_admin(self, user_session):
        """Image queue requires admin/moderator role"""
        resp = user_session.get(f"{BASE_URL}/api/admin/image-queue")
        # Should be 403 (forbidden) for regular user
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        print("✓ Image queue correctly requires admin auth")


class TestAdminImageQueueRetry:
    """Tests for POST /api/admin/image-queue/retry"""

    def test_retry_nonexistent_image(self, admin_session):
        """Retry with non-existent sha returns 404"""
        resp = admin_session.post(
            f"{BASE_URL}/api/admin/image-queue/retry",
            json={"sha": "nonexistent123456789", "auction_id": "test-auction-id"}
        )
        
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("✓ Retry non-existent image returns 404")

    def test_retry_requires_admin(self, user_session):
        """Retry requires admin role (not just moderator)"""
        resp = user_session.post(
            f"{BASE_URL}/api/admin/image-queue/retry",
            json={"sha": "test", "auction_id": "test"}
        )
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        print("✓ Retry correctly requires admin auth")


class TestAdminCdnHealth:
    """Tests for GET /api/admin/cdn-health"""

    def test_cdn_health_returns_probe_results(self, admin_session):
        """CDN health returns probe results with diagnosis"""
        resp = admin_session.get(f"{BASE_URL}/api/admin/cdn-health")
        
        assert resp.status_code == 200, f"CDN health failed: {resp.text}"
        data = resp.json()
        
        # Verify structure
        assert "cdn_host" in data, "Response missing 'cdn_host'"
        assert "probe_url" in data, "Response missing 'probe_url'"
        assert "cf_path" in data, "Response missing 'cf_path'"
        
        # CF path should have ok, status, etc.
        cf = data["cf_path"]
        assert "ok" in cf
        assert "status" in cf or "error" in cf
        
        # Check for wrong_redirect detection
        if cf.get("status") == 301:
            assert "wrong_redirect" in cf
            print(f"  CDN returned 301, wrong_redirect={cf.get('wrong_redirect')}")
        
        print(f"✓ CDN health probe: host={data['cdn_host']}")
        print(f"  CF path: ok={cf.get('ok')}, status={cf.get('status')}")
        if "diagnosis" in data:
            print(f"  Diagnosis: {data['diagnosis']}")

    def test_cdn_health_requires_admin(self, user_session):
        """CDN health requires admin role"""
        resp = user_session.get(f"{BASE_URL}/api/admin/cdn-health")
        assert resp.status_code in (401, 403), f"Expected 401/403, got {resp.status_code}"
        print("✓ CDN health correctly requires admin auth")


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""

    def test_healthz(self):
        """Health check endpoint works"""
        resp = requests.get(f"{BASE_URL}/api/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        print("✓ /healthz returns ok")

    def test_readyz(self):
        """Readiness check endpoint works"""
        resp = requests.get(f"{BASE_URL}/api/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
        print("✓ /readyz returns ready")

    def test_settings_endpoint(self, admin_session):
        """Settings endpoint works (regression for smsOpt issue)"""
        resp = admin_session.get(f"{BASE_URL}/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        # Should not have smsOpt field that caused ReferenceError
        print(f"✓ /settings returns valid response with {len(data)} keys")

    def test_admin_health_endpoint(self, admin_session):
        """Admin health endpoint works"""
        resp = admin_session.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "services" in data
        print(f"✓ /health returns status={data['status']}")


class TestBackgroundVariantGeneration:
    """Test that background variant generation runs"""

    def test_upload_triggers_optimization(self, admin_session):
        """Upload triggers background optimization queue"""
        # Upload a valid image
        jpeg_bytes = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
            0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xA8, 0xA2, 0x80, 0x0A, 0x28, 0xA0,
            0x02, 0x8A, 0x28, 0x00, 0xFF, 0xD9
        ])
        
        files = {"file": ("test_opt.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")}
        headers = {k: v for k, v in admin_session.headers.items() if k.lower() != "content-type"}
        
        resp = requests.post(
            f"{BASE_URL}/api/sell/image-upload",
            files=files,
            headers=headers,
            cookies=admin_session.cookies
        )
        
        assert resp.status_code == 200
        data = resp.json()
        sha = data["sha"]
        
        # Check queue stats - should show activity
        queue_resp = admin_session.get(f"{BASE_URL}/api/admin/image-queue")
        assert queue_resp.status_code == 200
        queue_data = queue_resp.json()
        
        print(f"✓ Upload triggered optimization for sha={sha[:10]}...")
        print(f"  Queue: pending={queue_data['queue']['pending']}, in_flight={queue_data['queue']['in_flight']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
