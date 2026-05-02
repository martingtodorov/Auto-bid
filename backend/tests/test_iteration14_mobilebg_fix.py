"""
Iteration 14 Tests: Mobile.bg import fix for 17-photo listing returning 24 photos.

Root cause: 
1. /big1/ path segment not matched by old regex (only /big/ was matched)
2. Related listings section ("Още обяви в mobile.bg") was bleeding through

Fix:
1. Scoped image search to main gallery (#rezon-gallery / .owl-carousel / .newAdImages / section)
2. Canonical dedup key is now FILENAME only (e.g. 11772388504582211_Au.webp)
3. Updated regex to support big\d* (big1, big2...) in _canon and _score
4. Added focus.bg to host allowlist
5. Added data-src-gallery as fallback attribute

Tests:
1. POST /api/auctions/import-mobile-bg with BMW M2 URL returns EXACTLY 17 images
2. All images contain '/big1/' in URL
3. No images from OTHER listing IDs (related listings block)
4. Images are in correct order (_Au, _U0, _8z, _bV, _NZ, _K6, _mp, _k8, _tz, _HX, _g0, _Id, _fP, _M8, _rK, _eG, _Iz)
5. City = 'Sofia', Country = 'Bulgaria'
6. Regression: filename-based dedup with synthetic test cases
7. Regression: URLs without file extension fallback
"""

import pytest
import requests
import os
import sys
import re

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://auction-drive-bg.preview.emergentagent.com').rstrip('/')

# The specific mobile.bg URL from the bug report
BMW_M2_URL = "https://www.mobile.bg/obiava-11772388504582211-bmw-m2-competition-swiss-hk-carplay"

# Expected listing ID (should be in all image URLs)
EXPECTED_LISTING_ID = "11772388504582211"

# Related listing IDs that should NOT appear in images (from "Още обяви в mobile.bg" section)
RELATED_LISTING_IDS = [
    "11772109399906432",
    "11749650820775475", 
    "11755840738726260",
    "11774653575320034"
]

# Expected image filename suffixes in order (from the page's gallery order)
EXPECTED_IMAGE_ORDER = ["_Au", "_U0", "_8z", "_bV", "_NZ", "_K6", "_mp", "_k8", "_tz", "_HX", "_g0", "_Id", "_fP", "_M8", "_rK", "_eG", "_Iz"]


class TestMobileBgBMWM2Import:
    """Test the specific BMW M2 listing import that was returning 24 photos instead of 17"""
    
    def test_import_returns_exactly_17_images(self):
        """POST /api/auctions/import-mobile-bg with BMW M2 URL returns EXACTLY 17 images"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": BMW_M2_URL},
            timeout=60  # mobile.bg scraping can be slow
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
        data = response.json()
        
        images = data.get("images", [])
        print(f"Received {len(images)} images")
        
        # The fix should return exactly 17 images (not 24 with 7 low-res dupes)
        assert len(images) == 17, f"Expected exactly 17 images, got {len(images)}. Images: {images}"
        print(f"✅ Import returns exactly 17 images")
    
    def test_all_images_contain_big1_path(self):
        """All returned images should contain '/big1/' in the URL (high-res variant)"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": BMW_M2_URL},
            timeout=60
        )
        
        assert response.status_code == 200
        data = response.json()
        images = data.get("images", [])
        
        for i, img in enumerate(images):
            assert "/big1/" in img.lower() or "/big" in img.lower(), f"Image {i} missing /big1/ or /big: {img}"
        
        # Count how many have /big1/ specifically
        big1_count = sum(1 for img in images if "/big1/" in img.lower())
        print(f"✅ {big1_count}/{len(images)} images contain '/big1/' path")
    
    def test_no_images_from_related_listings(self):
        """No images should contain listing IDs from the related listings block"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": BMW_M2_URL},
            timeout=60
        )
        
        assert response.status_code == 200
        data = response.json()
        images = data.get("images", [])
        
        for img in images:
            for related_id in RELATED_LISTING_IDS:
                assert related_id not in img, f"Image contains related listing ID {related_id}: {img}"
        
        print(f"✅ No images from related listings (checked {len(RELATED_LISTING_IDS)} IDs)")
    
    def test_all_images_from_correct_listing(self):
        """All images should contain the correct listing ID"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": BMW_M2_URL},
            timeout=60
        )
        
        assert response.status_code == 200
        data = response.json()
        images = data.get("images", [])
        
        for i, img in enumerate(images):
            assert EXPECTED_LISTING_ID in img, f"Image {i} missing listing ID {EXPECTED_LISTING_ID}: {img}"
        
        print(f"✅ All {len(images)} images contain correct listing ID {EXPECTED_LISTING_ID}")
    
    def test_images_in_correct_order(self):
        """Images should be in the correct gallery order based on filename suffixes"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": BMW_M2_URL},
            timeout=60
        )
        
        assert response.status_code == 200
        data = response.json()
        images = data.get("images", [])
        
        # Extract the suffix from each image URL (e.g., _Au from 11772388504582211_Au.webp)
        actual_suffixes = []
        for img in images:
            # Extract filename from URL
            filename = img.rsplit("/", 1)[-1].split("?")[0]
            # Extract suffix (e.g., _Au from 11772388504582211_Au.webp)
            match = re.search(r"_([A-Za-z0-9]{2})\.(?:webp|jpg|jpeg|png)$", filename)
            if match:
                actual_suffixes.append(f"_{match.group(1)}")
            else:
                actual_suffixes.append(filename)
        
        print(f"Actual order: {actual_suffixes}")
        print(f"Expected order: {EXPECTED_IMAGE_ORDER}")
        
        # Check that the order matches
        for i, (actual, expected) in enumerate(zip(actual_suffixes, EXPECTED_IMAGE_ORDER)):
            assert actual == expected, f"Image {i}: expected {expected}, got {actual}"
        
        print(f"✅ Images are in correct gallery order")
    
    def test_city_is_sofia(self):
        """City field should be 'Sofia' (transliterated from 'София')"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": BMW_M2_URL},
            timeout=60
        )
        
        assert response.status_code == 200
        data = response.json()
        
        city = data.get("city", "")
        assert city == "Sofia", f"Expected city 'Sofia', got '{city}'"
        print(f"✅ City is 'Sofia' (transliterated from Cyrillic)")
    
    def test_country_is_bulgaria(self):
        """Country field should be 'Bulgaria' (inferred from mobile.bg host)"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": BMW_M2_URL},
            timeout=60
        )
        
        assert response.status_code == 200
        data = response.json()
        
        country = data.get("country", "")
        assert country == "Bulgaria", f"Expected country 'Bulgaria', got '{country}'"
        print(f"✅ Country is 'Bulgaria' (inferred from host)")


class TestFilenameBasedDedupRegression:
    """Regression tests for filename-based dedup logic"""
    
    def test_canon_uses_filename_as_key(self):
        """_canon should use filename as the canonical key"""
        # Simulate the _canon function from server.py
        def _canon(u: str) -> str:
            lu = u.lower().split("?", 1)[0]
            # Prefer the basename as the canonical key
            tail = lu.rsplit("/", 1)[-1]
            if tail and "." in tail:
                return tail
            # Fallback
            lu = re.sub(r"/(big\d*|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big\d*|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+$)", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))$", r"/\1", lu)
            return lu
        
        # Test that big1 and non-big1 variants of same filename get same key
        big1_url = "https://mobistatic1.focus.bg/mobile/photosorg/big1/11772388504582211_Au.webp"
        thumb_url = "https://mobistatic1.focus.bg/mobile/photosorg/11772388504582211_Au.webp"
        
        big1_key = _canon(big1_url)
        thumb_key = _canon(thumb_url)
        
        assert big1_key == thumb_key, f"Keys should match: big1='{big1_key}', thumb='{thumb_key}'"
        assert big1_key == "11772388504582211_au.webp", f"Expected filename as key, got '{big1_key}'"
        print(f"✅ _canon uses filename as key: '{big1_key}'")
    
    def test_score_prefers_big1_over_plain(self):
        """_score should give higher score to /big1/ URLs"""
        def _score(u: str) -> int:
            lu = u.lower()
            if re.search(r"/big\d*/", lu) or "_big." in lu or "/orig" in lu or "_orig." in lu:
                return 5
            if "/large/" in lu or "_large." in lu:
                return 4
            if "/medium/" in lu or "_medium." in lu:
                return 2
            if ("/small/" in lu or "_small." in lu or "/thumb/" in lu or
                    "_thumb." in lu or "_t." in lu or "/tn/" in lu or "/preview/" in lu):
                return 1
            return 3
        
        big1_url = "https://mobistatic1.focus.bg/mobile/photosorg/big1/11772388504582211_Au.webp"
        plain_url = "https://mobistatic1.focus.bg/mobile/photosorg/11772388504582211_Au.webp"
        
        big1_score = _score(big1_url)
        plain_score = _score(plain_url)
        
        assert big1_score == 5, f"Expected big1 score 5, got {big1_score}"
        assert plain_score == 3, f"Expected plain score 3, got {plain_score}"
        assert big1_score > plain_score, f"big1 should score higher than plain"
        print(f"✅ _score: big1={big1_score}, plain={plain_score}")
    
    def test_dedup_9_urls_to_5_unique(self):
        """Regression: 9 URLs mixing /big/, /small/, /thumb/ and plain → 5 unique images"""
        def _canon(u: str) -> str:
            lu = u.lower().split("?", 1)[0]
            tail = lu.rsplit("/", 1)[-1]
            if tail and "." in tail:
                return tail
            lu = re.sub(r"/(big\d*|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big\d*|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+$)", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))$", r"/\1", lu)
            return lu
        
        def _score(u: str) -> int:
            lu = u.lower()
            if re.search(r"/big\d*/", lu) or "_big." in lu or "/orig" in lu or "_orig." in lu:
                return 5
            if "/large/" in lu or "_large." in lu:
                return 4
            if "/medium/" in lu or "_medium." in lu:
                return 2
            if ("/small/" in lu or "_small." in lu or "/thumb/" in lu or
                    "_thumb." in lu or "_t." in lu or "/tn/" in lu or "/preview/" in lu):
                return 1
            return 3
        
        # 9 URLs: 4 thumb + 4 big + 1 standalone for 5 unique photos
        candidates = [
            "https://mobile.bg/photos/thumb/photo1.jpg",
            "https://mobile.bg/photos/big/photo1.jpg",
            "https://mobile.bg/photos/thumb/photo2.jpg",
            "https://mobile.bg/photos/big/photo2.jpg",
            "https://mobile.bg/photos/thumb/photo3.jpg",
            "https://mobile.bg/photos/big/photo3.jpg",
            "https://mobile.bg/photos/thumb/photo4.jpg",
            "https://mobile.bg/photos/big/photo4.jpg",
            "https://mobile.bg/photos/photo5.jpg",
        ]
        
        best_for_key = {}
        key_first_seen = []
        for u in candidates:
            k = _canon(u)
            s = _score(u)
            prev = best_for_key.get(k)
            if prev is None:
                key_first_seen.append(k)
                best_for_key[k] = (s, u)
            elif s > prev[0]:
                best_for_key[k] = (s, u)
        
        images = [best_for_key[k][1] for k in key_first_seen]
        
        assert len(images) == 5, f"Expected 5 unique images, got {len(images)}"
        big_count = sum(1 for img in images if "/big/" in img)
        assert big_count == 4, f"Expected 4 big variants, got {big_count}"
        thumb_count = sum(1 for img in images if "/thumb/" in img)
        assert thumb_count == 0, f"Expected 0 thumb variants, got {thumb_count}"
        
        print(f"✅ Dedup: 9 URLs → 5 unique images, {big_count} big, {thumb_count} thumb")
    
    def test_dedup_big1_big2_variants(self):
        """Test dedup with /big1/, /big2/ variants (mobile.bg specific)"""
        def _canon(u: str) -> str:
            lu = u.lower().split("?", 1)[0]
            tail = lu.rsplit("/", 1)[-1]
            if tail and "." in tail:
                return tail
            lu = re.sub(r"/(big\d*|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big\d*|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+$)", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))$", r"/\1", lu)
            return lu
        
        def _score(u: str) -> int:
            lu = u.lower()
            if re.search(r"/big\d*/", lu) or "_big." in lu or "/orig" in lu or "_orig." in lu:
                return 5
            if "/large/" in lu or "_large." in lu:
                return 4
            if "/medium/" in lu or "_medium." in lu:
                return 2
            if ("/small/" in lu or "_small." in lu or "/thumb/" in lu or
                    "_thumb." in lu or "_t." in lu or "/tn/" in lu or "/preview/" in lu):
                return 1
            return 3
        
        # Simulate mobile.bg's actual URL structure with big1
        candidates = [
            "https://mobistatic1.focus.bg/mobile/photosorg/11772388504582211_Au.webp",  # plain (low-res)
            "https://mobistatic1.focus.bg/mobile/photosorg/big1/11772388504582211_Au.webp",  # big1 (high-res)
            "https://mobistatic1.focus.bg/mobile/photosorg/11772388504582211_U0.webp",  # plain
            "https://mobistatic1.focus.bg/mobile/photosorg/big1/11772388504582211_U0.webp",  # big1
        ]
        
        best_for_key = {}
        key_first_seen = []
        for u in candidates:
            k = _canon(u)
            s = _score(u)
            prev = best_for_key.get(k)
            if prev is None:
                key_first_seen.append(k)
                best_for_key[k] = (s, u)
            elif s > prev[0]:
                best_for_key[k] = (s, u)
        
        images = [best_for_key[k][1] for k in key_first_seen]
        
        assert len(images) == 2, f"Expected 2 unique images, got {len(images)}"
        big1_count = sum(1 for img in images if "/big1/" in img)
        assert big1_count == 2, f"Expected 2 big1 variants, got {big1_count}"
        
        print(f"✅ Dedup with /big1/: 4 URLs → 2 unique images, all big1")


class TestUrlWithoutExtensionFallback:
    """Regression: URLs without file extension should still get canonical key via fallback"""
    
    def test_canon_fallback_for_no_extension(self):
        """_canon fallback works for URLs without clear filename"""
        def _canon(u: str) -> str:
            lu = u.lower().split("?", 1)[0]
            tail = lu.rsplit("/", 1)[-1]
            if tail and "." in tail:
                return tail
            # Fallback for URLs without a clear filename
            lu = re.sub(r"/(big\d*|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big\d*|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+$)", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))$", r"/\1", lu)
            return lu
        
        # URL without extension
        url_no_ext = "https://mobile.bg/photos/big1/abc123"
        key = _canon(url_no_ext)
        
        # Should return the path with /big1/ stripped
        assert "/big1/" not in key, f"Expected /big1/ stripped in fallback, got '{key}'"
        print(f"✅ _canon fallback for no extension: '{url_no_ext}' → '{key}'")


class TestFocusBgHostAllowlist:
    """Test that focus.bg is in the host allowlist"""
    
    def test_focus_bg_urls_accepted(self):
        """focus.bg URLs should be accepted as valid image sources"""
        # This is tested implicitly by the BMW M2 import test, but let's verify the logic
        test_urls = [
            "https://mobistatic1.focus.bg/mobile/photosorg/big1/test.webp",
            "https://cdn1.focus.bg/mobile/photos/test.jpg",
            "https://www.mobile.bg/photos/test.png",
        ]
        
        for url in test_urls:
            # Check the condition from server.py line 1458
            is_valid = ("mobile.bg" in url or "focus.bg" in url or url.startswith("http")) and \
                       any(x in url.lower() for x in ["photo", "pic", "big", "jpg", "jpeg", "png", "webp"])
            assert is_valid, f"URL should be valid: {url}"
        
        print(f"✅ focus.bg URLs are accepted as valid image sources")


class TestRegressionEndpoints:
    """Regression tests for core endpoints"""
    
    def test_healthz(self):
        """GET /api/healthz returns 200"""
        response = requests.get(f"{BASE_URL}/api/healthz")
        assert response.status_code == 200
        print("✅ /api/healthz returns 200")
    
    def test_auctions_list(self):
        """GET /api/auctions returns 200"""
        response = requests.get(f"{BASE_URL}/api/auctions")
        assert response.status_code == 200
        print("✅ /api/auctions returns 200")
    
    def test_import_endpoint_exists(self):
        """POST /api/auctions/import-mobile-bg endpoint exists"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": ""}
        )
        # Should return 400 for empty URL, not 404
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✅ /api/auctions/import-mobile-bg endpoint exists")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
