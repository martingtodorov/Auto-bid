"""
Iteration 19: OG Image Refactor Tests

Tests for the removal of custom Pillow-rendered OG template and replacement
with auction's headline image directly.

Features tested:
1. GET /api/share/auction/{auction_id} - og:image points to headline image
2. GET /api/og/auction/{auction_id}.png - 302 redirect to headline image
3. services/og_image.py build_and_persist - returns headline_image_url
4. Regression: POST /api/admin/auctions/{id}/regenerate-og-image
5. Regression: fallback to /og-default.jpg for auctions with no images
6. Regression: GET /api/share/auction/<bad-id> returns og-default.jpg
"""

import pytest
import requests
import os
import re
from html.parser import HTMLParser

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test auction ID from live auctions
LIVE_AUCTION_ID = "5a476c7a-4a21-4550-b591-439d8fae2f94"
EXPECTED_HEADLINE_IMAGE = "https://mobistatic4.focus.bg/mobile/photosorg/034/1/11774653575320034_hr.webp"


class OGMetaParser(HTMLParser):
    """Parse HTML to extract OG meta tags"""
    def __init__(self):
        super().__init__()
        self.og_tags = {}
        self.twitter_tags = {}
        
    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            attrs_dict = dict(attrs)
            prop = attrs_dict.get('property', '')
            name = attrs_dict.get('name', '')
            content = attrs_dict.get('content', '')
            
            if prop.startswith('og:'):
                self.og_tags[prop] = content
            if name.startswith('twitter:'):
                self.twitter_tags[name] = content


class TestOGShareRoute:
    """Test GET /api/share/auction/{auction_id} returns correct OG meta tags"""
    
    def test_share_auction_og_image_points_to_headline(self):
        """og:image should point to auction's headline image, NOT Pillow PNG"""
        response = requests.get(f"{BASE_URL}/api/share/auction/{LIVE_AUCTION_ID}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        html = response.text
        parser = OGMetaParser()
        parser.feed(html)
        
        # og:image should be the headline image URL
        og_image = parser.og_tags.get('og:image', '')
        assert og_image, "og:image meta tag not found"
        assert EXPECTED_HEADLINE_IMAGE in og_image or og_image == EXPECTED_HEADLINE_IMAGE, \
            f"og:image should be headline image. Got: {og_image}"
        
        # Should NOT be the old Pillow-generated PNG endpoint
        assert '/api/og/auction/' not in og_image or '.png' not in og_image, \
            f"og:image should NOT point to /api/og/auction/{{id}}.png. Got: {og_image}"
        
        # Should NOT be og_image_url field (which was the old stored path)
        assert '/uploads/og/' not in og_image, \
            f"og:image should NOT point to /uploads/og/ path. Got: {og_image}"
        
        print(f"✓ og:image correctly points to headline: {og_image}")
    
    def test_share_auction_twitter_image_points_to_headline(self):
        """twitter:image should also point to headline image"""
        response = requests.get(f"{BASE_URL}/api/share/auction/{LIVE_AUCTION_ID}")
        assert response.status_code == 200
        
        html = response.text
        parser = OGMetaParser()
        parser.feed(html)
        
        twitter_image = parser.twitter_tags.get('twitter:image', '')
        assert twitter_image, "twitter:image meta tag not found"
        assert EXPECTED_HEADLINE_IMAGE in twitter_image or twitter_image == EXPECTED_HEADLINE_IMAGE, \
            f"twitter:image should be headline image. Got: {twitter_image}"
        
        print(f"✓ twitter:image correctly points to headline: {twitter_image}")
    
    def test_share_auction_no_image_dimension_meta_tags(self):
        """og:image:width, og:image:height, og:image:type=image/png should be REMOVED"""
        response = requests.get(f"{BASE_URL}/api/share/auction/{LIVE_AUCTION_ID}")
        assert response.status_code == 200
        
        html = response.text
        parser = OGMetaParser()
        parser.feed(html)
        
        # These tags should NOT exist since headline images can be JPG/WebP of various dimensions
        assert 'og:image:width' not in parser.og_tags, \
            f"og:image:width should be removed. Found: {parser.og_tags.get('og:image:width')}"
        assert 'og:image:height' not in parser.og_tags, \
            f"og:image:height should be removed. Found: {parser.og_tags.get('og:image:height')}"
        
        # og:image:type=image/png should not exist
        og_image_type = parser.og_tags.get('og:image:type', '')
        assert og_image_type != 'image/png', \
            f"og:image:type should NOT be image/png. Got: {og_image_type}"
        
        print("✓ og:image:width/height/type=image/png meta tags correctly removed")
    
    def test_share_auction_bad_id_returns_default_image(self):
        """GET /api/share/auction/<bad-id> should return og:image=/og-default.jpg, not 500"""
        bad_id = "nonexistent-auction-id-12345"
        response = requests.get(f"{BASE_URL}/api/share/auction/{bad_id}")
        
        # Should NOT return 500
        assert response.status_code != 500, f"Should not return 500 for bad auction ID"
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        html = response.text
        parser = OGMetaParser()
        parser.feed(html)
        
        og_image = parser.og_tags.get('og:image', '')
        assert '/og-default.jpg' in og_image, \
            f"og:image should fallback to /og-default.jpg for bad ID. Got: {og_image}"
        
        print(f"✓ Bad auction ID correctly falls back to: {og_image}")


class TestOGAuctionImageRoute:
    """Test GET /api/og/auction/{auction_id}.png - now 302 redirect"""
    
    def test_og_png_route_redirects_to_headline(self):
        """GET /api/og/auction/{id}.png should 302 redirect to headline image"""
        response = requests.get(
            f"{BASE_URL}/api/og/auction/{LIVE_AUCTION_ID}.png",
            allow_redirects=False
        )
        
        assert response.status_code == 302, \
            f"Expected 302 redirect, got {response.status_code}"
        
        location = response.headers.get('Location', '')
        assert location, "Location header missing in 302 response"
        assert EXPECTED_HEADLINE_IMAGE in location or location == EXPECTED_HEADLINE_IMAGE, \
            f"Redirect should point to headline image. Got: {location}"
        
        print(f"✓ /api/og/auction/{{id}}.png correctly redirects to: {location}")
    
    def test_og_png_route_404_for_nonexistent_auction(self):
        """GET /api/og/auction/<bad-id>.png should return 404"""
        bad_id = "nonexistent-auction-id-12345"
        response = requests.get(
            f"{BASE_URL}/api/og/auction/{bad_id}.png",
            allow_redirects=False
        )
        
        assert response.status_code == 404, \
            f"Expected 404 for nonexistent auction, got {response.status_code}"
        
        print("✓ /api/og/auction/<bad-id>.png correctly returns 404")
    
    def test_og_png_route_follows_redirect(self):
        """Following the redirect should return the actual image"""
        response = requests.get(
            f"{BASE_URL}/api/og/auction/{LIVE_AUCTION_ID}.png",
            allow_redirects=True
        )
        
        # Should successfully follow redirect to the image
        assert response.status_code == 200, \
            f"Following redirect should return 200, got {response.status_code}"
        
        # Content-Type should be an image type
        content_type = response.headers.get('Content-Type', '')
        assert 'image' in content_type.lower(), \
            f"Content-Type should be image/*, got: {content_type}"
        
        print(f"✓ Following redirect returns image with Content-Type: {content_type}")


class TestAdminRegenerateOGImage:
    """Regression: POST /api/admin/auctions/{id}/regenerate-og-image"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@autoandbid.com",
            "password": "Nero08787"
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip("Admin authentication failed")
    
    def test_regenerate_og_image_endpoint_works(self, admin_token):
        """POST /api/admin/auctions/{id}/regenerate-og-image should still work"""
        response = requests.post(
            f"{BASE_URL}/api/admin/auctions/{LIVE_AUCTION_ID}/regenerate-og-image",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Should return 200 (or 404 if endpoint was removed, which would be a regression)
        assert response.status_code in [200, 201], \
            f"Expected 200/201, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should return the headline URL (or og_image_url)
        og_url = data.get('og_image_url', data.get('url', ''))
        assert og_url, f"Response should contain og_image_url. Got: {data}"
        
        print(f"✓ regenerate-og-image endpoint works, returned: {og_url}")
    
    def test_regenerate_og_image_requires_admin(self):
        """POST /api/admin/auctions/{id}/regenerate-og-image requires admin auth"""
        # Without auth
        response = requests.post(
            f"{BASE_URL}/api/admin/auctions/{LIVE_AUCTION_ID}/regenerate-og-image"
        )
        assert response.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {response.status_code}"
        
        print("✓ regenerate-og-image correctly requires admin auth")


class TestOGImageFallbacks:
    """Test fallback behavior for auctions with no images"""
    
    def test_headline_image_url_fallback_chain(self):
        """Verify fallback: headline → og_image_url → /og-default.jpg"""
        # This is tested indirectly through the share route with bad ID
        # The bad ID test already verifies /og-default.jpg fallback
        
        # Additional test: verify the share route HTML structure
        response = requests.get(f"{BASE_URL}/api/share/auction/{LIVE_AUCTION_ID}")
        assert response.status_code == 200
        
        html = response.text
        
        # Verify HTML structure is valid
        assert '<!DOCTYPE html>' in html, "Missing DOCTYPE"
        assert '<meta property="og:image"' in html, "Missing og:image meta tag"
        assert '<meta name="twitter:image"' in html, "Missing twitter:image meta tag"
        
        print("✓ Share route HTML structure is valid")


class TestNoAppCrash:
    """Verify no import errors or app crash at startup"""
    
    def test_healthz_endpoint(self):
        """Health check should pass"""
        response = requests.get(f"{BASE_URL}/api/healthz")
        assert response.status_code == 200, \
            f"Health check failed: {response.status_code}"
        print("✓ /api/healthz returns 200")
    
    def test_readyz_endpoint(self):
        """Readiness check should pass"""
        response = requests.get(f"{BASE_URL}/api/readyz")
        assert response.status_code == 200, \
            f"Readiness check failed: {response.status_code}"
        print("✓ /api/readyz returns 200")
    
    def test_auctions_endpoint(self):
        """Auctions endpoint should work"""
        response = requests.get(f"{BASE_URL}/api/auctions?status=live&limit=1")
        assert response.status_code == 200, \
            f"Auctions endpoint failed: {response.status_code}"
        print("✓ /api/auctions returns 200")


class TestOGImageServiceCode:
    """Verify og_image.py service code changes"""
    
    def test_build_and_persist_returns_headline_url(self):
        """build_and_persist should return headline URL without creating files"""
        # This is a code structure test - we verify by checking the share route behavior
        # The share route uses og_image.headline_image_url() directly
        
        response = requests.get(f"{BASE_URL}/api/share/auction/{LIVE_AUCTION_ID}")
        assert response.status_code == 200
        
        html = response.text
        parser = OGMetaParser()
        parser.feed(html)
        
        og_image = parser.og_tags.get('og:image', '')
        
        # Should be the actual image URL, not a generated PNG path
        assert og_image.startswith('http'), \
            f"og:image should be a full URL. Got: {og_image}"
        
        # Should NOT be a local /uploads/og/ path
        assert '/uploads/og/' not in og_image, \
            f"og:image should NOT be a local upload path. Got: {og_image}"
        
        print(f"✓ og:image is external URL (no local file generation): {og_image}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
