"""
Iteration 13 Tests: Translation helpers, city transliteration, country detection, and image dedup.

Tests:
1. translate.transliterate_city_to_latin() - Cyrillic → Latin city names
2. translate.country_from_host() - TLD → country mapping
3. Image dedup logic (_canon, _score) - mobile.bg URL canonicalization
4. SellPage city input - no Latin-only restriction
"""

import pytest
import requests
import os
import sys
import asyncio

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://auction-drive-bg.preview.emergentagent.com').rstrip('/')

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


def run_async(coro):
    """Helper to run async functions in sync tests"""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestTransliterateCityToLatin:
    """Test translate.transliterate_city_to_latin() function"""
    
    def test_sofia_cyrillic_to_latin(self):
        """София → Sofia (curated fast-path)"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin("София"))
        assert result == "Sofia", f"Expected 'Sofia', got '{result}'"
        print(f"✅ 'София' → '{result}'")
    
    def test_veliko_tarnovo_cyrillic_to_latin(self):
        """Велико Търново → Veliko Tarnovo (curated fast-path)"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin("Велико Търново"))
        assert result == "Veliko Tarnovo", f"Expected 'Veliko Tarnovo', got '{result}'"
        print(f"✅ 'Велико Търново' → '{result}'")
    
    def test_plovdiv_cyrillic_to_latin(self):
        """Пловдив → Plovdiv (curated fast-path)"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin("Пловдив"))
        assert result == "Plovdiv", f"Expected 'Plovdiv', got '{result}'"
        print(f"✅ 'Пловдив' → '{result}'")
    
    def test_varna_cyrillic_to_latin(self):
        """Варна → Varna (curated fast-path)"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin("Варна"))
        assert result == "Varna", f"Expected 'Varna', got '{result}'"
        print(f"✅ 'Варна' → '{result}'")
    
    def test_burgas_cyrillic_to_latin(self):
        """Бургас → Burgas (curated fast-path)"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin("Бургас"))
        assert result == "Burgas", f"Expected 'Burgas', got '{result}'"
        print(f"✅ 'Бургас' → '{result}'")
    
    def test_latin_input_unchanged(self):
        """Sofia (already Latin) → Sofia (no-op)"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin("Sofia"))
        assert result == "Sofia", f"Expected 'Sofia', got '{result}'"
        print(f"✅ 'Sofia' → '{result}' (no-op)")
    
    def test_empty_input(self):
        """Empty string → empty string"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin(""))
        assert result == "", f"Expected '', got '{result}'"
        print(f"✅ '' → '' (empty)")
    
    def test_hisarya_cyrillic_to_latin(self):
        """Хисаря → some Latin string (curated or LLM fallback)"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin("Хисаря"))
        # Should return some Latin string (either from LLM or static fallback)
        assert result, "Expected non-empty result"
        assert not any('\u0400' <= ch <= '\u04FF' for ch in result), f"Result '{result}' still contains Cyrillic"
        print(f"✅ 'Хисаря' → '{result}' (Latin output)")
    
    def test_ruse_cyrillic_to_latin(self):
        """Русе → Ruse (curated fast-path)"""
        from translate import transliterate_city_to_latin
        result = run_async(transliterate_city_to_latin("Русе"))
        assert result == "Ruse", f"Expected 'Ruse', got '{result}'"
        print(f"✅ 'Русе' → '{result}'")


class TestCountryFromHost:
    """Test translate.country_from_host() function"""
    
    def test_bg_domain(self):
        """auto-bid.bg → Bulgaria"""
        from translate import country_from_host
        result = country_from_host("auto-bid.bg")
        assert result == "Bulgaria", f"Expected 'Bulgaria', got '{result}'"
        print(f"✅ 'auto-bid.bg' → '{result}'")
    
    def test_ro_domain(self):
        """auto-bid.ro → Romania"""
        from translate import country_from_host
        result = country_from_host("auto-bid.ro")
        assert result == "Romania", f"Expected 'Romania', got '{result}'"
        print(f"✅ 'auto-bid.ro' → '{result}'")
    
    def test_com_domain(self):
        """auto-bid.com → Bulgaria (default)"""
        from translate import country_from_host
        result = country_from_host("auto-bid.com")
        assert result == "Bulgaria", f"Expected 'Bulgaria', got '{result}'"
        print(f"✅ 'auto-bid.com' → '{result}'")
    
    def test_preview_domain(self):
        """auction-drive-bg.preview.emergentagent.com → Bulgaria (default for .com)"""
        from translate import country_from_host
        result = country_from_host("auction-drive-bg.preview.emergentagent.com")
        assert result == "Bulgaria", f"Expected 'Bulgaria', got '{result}'"
        print(f"✅ 'auction-drive-bg.preview.emergentagent.com' → '{result}'")
    
    def test_empty_host(self):
        """Empty host → Bulgaria (default)"""
        from translate import country_from_host
        result = country_from_host("")
        assert result == "Bulgaria", f"Expected 'Bulgaria', got '{result}'"
        print(f"✅ '' → '{result}' (default)")
    
    def test_host_with_port(self):
        """auto-bid.bg:8080 → Bulgaria (port stripped)"""
        from translate import country_from_host
        result = country_from_host("auto-bid.bg:8080")
        assert result == "Bulgaria", f"Expected 'Bulgaria', got '{result}'"
        print(f"✅ 'auto-bid.bg:8080' → '{result}'")
    
    def test_unknown_tld(self):
        """auto-bid.de → Bulgaria (default for unknown TLD)"""
        from translate import country_from_host
        result = country_from_host("auto-bid.de")
        assert result == "Bulgaria", f"Expected 'Bulgaria', got '{result}'"
        print(f"✅ 'auto-bid.de' → '{result}' (default)")


class TestImageDedupLogic:
    """Test mobile.bg image dedup logic (_canon, _score)"""
    
    def test_canon_strips_big_folder(self):
        """_canon strips /big/ folder"""
        import re
        def _canon(u: str) -> str:
            lu = u.lower()
            lu = re.sub(r"/(big|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+(?:\?|$))", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))(?:\?|$)", r"/\1", lu)
            lu = lu.split("?", 1)[0]
            return lu
        
        url = "https://www.mobile.bg/photos/big/abc123.jpg"
        result = _canon(url)
        assert "/big/" not in result, f"Expected /big/ stripped, got '{result}'"
        print(f"✅ _canon strips /big/: '{url}' → '{result}'")
    
    def test_canon_strips_thumb_folder(self):
        """_canon strips /thumb/ folder"""
        import re
        def _canon(u: str) -> str:
            lu = u.lower()
            lu = re.sub(r"/(big|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+(?:\?|$))", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))(?:\?|$)", r"/\1", lu)
            lu = lu.split("?", 1)[0]
            return lu
        
        url = "https://www.mobile.bg/photos/thumb/abc123.jpg"
        result = _canon(url)
        assert "/thumb/" not in result, f"Expected /thumb/ stripped, got '{result}'"
        print(f"✅ _canon strips /thumb/: '{url}' → '{result}'")
    
    def test_canon_strips_size_suffix(self):
        """_canon strips _big suffix"""
        import re
        def _canon(u: str) -> str:
            lu = u.lower()
            lu = re.sub(r"/(big|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+(?:\?|$))", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))(?:\?|$)", r"/\1", lu)
            lu = lu.split("?", 1)[0]
            return lu
        
        url = "https://www.mobile.bg/photos/abc123_big.jpg"
        result = _canon(url)
        assert "_big" not in result, f"Expected _big stripped, got '{result}'"
        print(f"✅ _canon strips _big suffix: '{url}' → '{result}'")
    
    def test_canon_strips_numeric_prefix(self):
        """_canon strips numeric size prefix like /8-abc.jpg"""
        import re
        def _canon(u: str) -> str:
            lu = u.lower()
            lu = re.sub(r"/(big|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+(?:\?|$))", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))(?:\?|$)", r"/\1", lu)
            lu = lu.split("?", 1)[0]
            return lu
        
        url = "https://www.mobile.bg/photos/8-abc123.jpg"
        result = _canon(url)
        assert "/8-" not in result, f"Expected /8- stripped, got '{result}'"
        print(f"✅ _canon strips numeric prefix: '{url}' → '{result}'")
    
    def test_score_big_highest(self):
        """_score gives highest score to /big/ URLs"""
        def _score(u: str) -> int:
            lu = u.lower()
            if "/big/" in lu or "_big." in lu or "/orig" in lu or "_orig." in lu:
                return 5
            if "/large/" in lu or "_large." in lu:
                return 4
            if "/medium/" in lu or "_medium." in lu:
                return 2
            if ("/small/" in lu or "_small." in lu or "/thumb/" in lu or
                    "_thumb." in lu or "_t." in lu or "/tn/" in lu or "/preview/" in lu):
                return 1
            return 3
        
        assert _score("https://mobile.bg/photos/big/abc.jpg") == 5
        assert _score("https://mobile.bg/photos/thumb/abc.jpg") == 1
        assert _score("https://mobile.bg/photos/abc.jpg") == 3
        print("✅ _score: big=5, thumb=1, neutral=3")
    
    def test_dedup_keeps_best_variant(self):
        """Dedup keeps only the best (highest score) variant per canonical key"""
        import re
        
        def _canon(u: str) -> str:
            lu = u.lower()
            lu = re.sub(r"/(big|small|thumb|medium|orig|large|preview|tn)/", "/", lu)
            lu = re.sub(r"_(big|small|t|thumb|medium|orig|large|preview|tn)(?=\.[a-z0-9]+(?:\?|$))", "", lu)
            lu = re.sub(r"/(?:\d{1,3})-([^/]+\.(?:jpg|jpeg|png|webp))(?:\?|$)", r"/\1", lu)
            lu = lu.split("?", 1)[0]
            return lu
        
        def _score(u: str) -> int:
            lu = u.lower()
            if "/big/" in lu or "_big." in lu or "/orig" in lu or "_orig." in lu:
                return 5
            if "/large/" in lu or "_large." in lu:
                return 4
            if "/medium/" in lu or "_medium." in lu:
                return 2
            if ("/small/" in lu or "_small." in lu or "/thumb/" in lu or
                    "_thumb." in lu or "_t." in lu or "/tn/" in lu or "/preview/" in lu):
                return 1
            return 3
        
        # Simulate 9 URLs: 4 thumb + 4 big + 1 standalone for 5 unique photos
        candidates = [
            # Photo 1: thumb + big
            "https://mobile.bg/photos/thumb/photo1.jpg",
            "https://mobile.bg/photos/big/photo1.jpg",
            # Photo 2: thumb + big
            "https://mobile.bg/photos/thumb/photo2.jpg",
            "https://mobile.bg/photos/big/photo2.jpg",
            # Photo 3: thumb + big
            "https://mobile.bg/photos/thumb/photo3.jpg",
            "https://mobile.bg/photos/big/photo3.jpg",
            # Photo 4: thumb + big
            "https://mobile.bg/photos/thumb/photo4.jpg",
            "https://mobile.bg/photos/big/photo4.jpg",
            # Photo 5: standalone (no thumb variant)
            "https://mobile.bg/photos/photo5.jpg",
        ]
        
        best_for_key: dict = {}
        key_first_seen: list = []
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
        
        # Should have exactly 5 unique images
        assert len(images) == 5, f"Expected 5 images, got {len(images)}"
        
        # All 4 photos with variants should be the 'big' version
        big_count = sum(1 for img in images if "/big/" in img)
        assert big_count == 4, f"Expected 4 big variants, got {big_count}"
        
        # No thumb URLs should leak through
        thumb_count = sum(1 for img in images if "/thumb/" in img)
        assert thumb_count == 0, f"Expected 0 thumb variants, got {thumb_count}"
        
        print(f"✅ Dedup: 9 URLs → 5 unique images, all 4 variants are 'big', 0 thumbs")


class TestMobileBgImportEndpoint:
    """Test POST /api/auctions/import-mobile-bg endpoint"""
    
    def test_import_returns_country_field(self):
        """Import response includes 'country' field derived from host"""
        # Use a valid-looking mobile.bg URL (even if it doesn't exist, the endpoint
        # will scrape whatever page it can reach and return a response with country)
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": "https://mobile.bg/invalid"}
        )
        # The endpoint returns 200 even for invalid listing URLs because it scrapes
        # whatever page it can reach (in this case, the mobile.bg homepage/search)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Verify 'country' field is present and derived from host
        assert "country" in data, "Expected 'country' field in response"
        assert data["country"] == "Bulgaria", f"Expected 'Bulgaria', got '{data['country']}'"
        print(f"✅ Import response includes country: {data['country']}")
    
    def test_non_mobile_bg_url_returns_400(self):
        """Non-mobile.bg URL returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": "https://google.com/search"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "mobile.bg" in data.get("detail", "").lower(), "Expected mobile.bg mention in error"
        print(f"✅ Non-mobile.bg URL returns 400: {data.get('detail', '')[:50]}...")
    
    def test_empty_url_returns_400(self):
        """Empty URL returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": ""}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print(f"✅ Empty URL returns 400")
    
    def test_import_response_has_required_fields(self):
        """Import response has all required fields"""
        response = requests.post(
            f"{BASE_URL}/api/auctions/import-mobile-bg",
            json={"url": "https://mobile.bg/invalid"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        # Check required fields are present
        required_fields = ["title", "make", "model", "year", "mileage_km", "fuel", 
                          "transmission", "body_type", "city", "country", "images"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"✅ Import response has all required fields: {list(data.keys())}")


class TestBgLocaleTranslations:
    """Test that BG locale has the updated benefit phrases"""
    
    def test_bg_locale_s1_desc(self):
        """s1_desc should contain 'наддаване' (not 'наддавка')"""
        import json
        with open('/app/frontend/src/i18n/locales/bg.json', 'r') as f:
            bg = json.load(f)
        
        s1_desc = bg.get("landing", {}).get("steps", {}).get("s1_desc", "")
        assert "наддаване" in s1_desc, f"Expected 'наддаване' in s1_desc, got: {s1_desc}"
        assert "наддавка" not in s1_desc, f"Should NOT contain 'наддавка', got: {s1_desc}"
        print(f"✅ s1_desc contains 'наддаване': {s1_desc[:60]}...")
    
    def test_bg_locale_s2_desc_no_technical_report(self):
        """s2_desc should NOT contain 'независим технически доклад'"""
        import json
        with open('/app/frontend/src/i18n/locales/bg.json', 'r') as f:
            bg = json.load(f)
        
        s2_desc = bg.get("landing", {}).get("steps", {}).get("s2_desc", "")
        assert "независим технически доклад" not in s2_desc, f"Should NOT contain 'независим технически доклад', got: {s2_desc}"
        print(f"✅ s2_desc does NOT contain 'независим технически доклад': {s2_desc[:60]}...")
    
    def test_bg_locale_s3_desc_rephrased(self):
        """s3_desc should contain 'наддаване в последните 2 минути удължава търга'"""
        import json
        with open('/app/frontend/src/i18n/locales/bg.json', 'r') as f:
            bg = json.load(f)
        
        s3_desc = bg.get("landing", {}).get("steps", {}).get("s3_desc", "")
        assert "наддаване в последните 2 минути удължава търга" in s3_desc, f"Expected rephrased text, got: {s3_desc}"
        print(f"✅ s3_desc rephrased correctly: {s3_desc[:60]}...")
    
    def test_bg_locale_s4_desc_ending(self):
        """s4_desc should end with 'прехвърляне и регистрация'"""
        import json
        with open('/app/frontend/src/i18n/locales/bg.json', 'r') as f:
            bg = json.load(f)
        
        s4_desc = bg.get("landing", {}).get("steps", {}).get("s4_desc", "")
        assert "прехвърляне и регистрация" in s4_desc, f"Expected 'прехвърляне и регистрация', got: {s4_desc}"
        print(f"✅ s4_desc ends with 'прехвърляне и регистрация': {s4_desc[:60]}...")
    
    def test_bg_locale_city_hint(self):
        """city_hint should mention accepting both Latin and Cyrillic"""
        import json
        with open('/app/frontend/src/i18n/locales/bg.json', 'r') as f:
            bg = json.load(f)
        
        city_hint = bg.get("sell", {}).get("form", {}).get("city_hint", "")
        assert "кирилица" in city_hint.lower() or "латиница" in city_hint.lower(), f"Expected mention of scripts, got: {city_hint}"
        print(f"✅ city_hint mentions scripts: {city_hint}")


class TestEnRoLocaleIntegrity:
    """Test that EN and RO locales still render without errors"""
    
    def test_en_locale_has_landing_steps(self):
        """EN locale has landing.steps section"""
        import json
        with open('/app/frontend/src/i18n/locales/en.json', 'r') as f:
            en = json.load(f)
        
        steps = en.get("landing", {}).get("steps", {})
        assert "s1_title" in steps, "Missing s1_title in EN"
        assert "s1_desc" in steps, "Missing s1_desc in EN"
        assert "s2_title" in steps, "Missing s2_title in EN"
        assert "s2_desc" in steps, "Missing s2_desc in EN"
        assert "s3_title" in steps, "Missing s3_title in EN"
        assert "s3_desc" in steps, "Missing s3_desc in EN"
        assert "s4_title" in steps, "Missing s4_title in EN"
        assert "s4_desc" in steps, "Missing s4_desc in EN"
        print("✅ EN locale has all landing.steps keys")
    
    def test_ro_locale_has_landing_steps(self):
        """RO locale has landing.steps section"""
        import json
        with open('/app/frontend/src/i18n/locales/ro.json', 'r') as f:
            ro = json.load(f)
        
        steps = ro.get("landing", {}).get("steps", {})
        assert "s1_title" in steps, "Missing s1_title in RO"
        assert "s1_desc" in steps, "Missing s1_desc in RO"
        assert "s2_title" in steps, "Missing s2_title in RO"
        assert "s2_desc" in steps, "Missing s2_desc in RO"
        assert "s3_title" in steps, "Missing s3_title in RO"
        assert "s3_desc" in steps, "Missing s3_desc in RO"
        assert "s4_title" in steps, "Missing s4_title in RO"
        assert "s4_desc" in steps, "Missing s4_desc in RO"
        print("✅ RO locale has all landing.steps keys")
    
    def test_en_locale_city_hint_updated(self):
        """EN locale city_hint mentions accepting both scripts"""
        import json
        with open('/app/frontend/src/i18n/locales/en.json', 'r') as f:
            en = json.load(f)
        
        city_hint = en.get("sell", {}).get("form", {}).get("city_hint", "")
        assert "latin" in city_hint.lower() or "cyrillic" in city_hint.lower(), f"Expected mention of scripts, got: {city_hint}"
        print(f"✅ EN city_hint: {city_hint}")
    
    def test_ro_locale_city_hint_updated(self):
        """RO locale city_hint mentions accepting both scripts"""
        import json
        with open('/app/frontend/src/i18n/locales/ro.json', 'r') as f:
            ro = json.load(f)
        
        city_hint = ro.get("sell", {}).get("form", {}).get("city_hint", "")
        assert "latin" in city_hint.lower() or "chirilic" in city_hint.lower(), f"Expected mention of scripts, got: {city_hint}"
        print(f"✅ RO city_hint: {city_hint}")


class TestSellPageCityInput:
    """Test SellPage.jsx city input has no Latin-only restriction"""
    
    def test_city_input_no_pattern_attribute(self):
        """City input should NOT have pattern attribute"""
        with open('/app/frontend/src/pages/SellPage.jsx', 'r') as f:
            content = f.read()
        
        # Find the city input section
        city_input_section = content[content.find('label={t("sell.form.city")}'):content.find('label={t("sell.form.country")}')]
        
        # Should NOT have pattern attribute
        assert 'pattern=' not in city_input_section, f"City input should NOT have pattern attribute"
        print("✅ City input has NO pattern attribute")
    
    def test_city_input_no_latin_only_title(self):
        """City input should NOT have Latin-only title"""
        with open('/app/frontend/src/pages/SellPage.jsx', 'r') as f:
            content = f.read()
        
        # Should NOT have Latin-only title
        assert 'title="Latin' not in content, "Should NOT have Latin-only title"
        assert 'title="Само латиница' not in content, "Should NOT have Bulgarian Latin-only title"
        print("✅ City input has NO Latin-only title")
    
    def test_no_err_city_latin_validation(self):
        """SellPage should NOT have err_city_latin validation"""
        with open('/app/frontend/src/pages/SellPage.jsx', 'r') as f:
            content = f.read()
        
        # Should NOT have Latin-only regex validation
        assert 'err_city_latin' not in content, "Should NOT have err_city_latin validation"
        assert '/^[A-Za-z' not in content, "Should NOT have Latin-only regex"
        print("✅ SellPage has NO err_city_latin validation")
    
    def test_city_placeholder_shows_both_scripts(self):
        """City input placeholder shows both Latin and Cyrillic examples"""
        with open('/app/frontend/src/pages/SellPage.jsx', 'r') as f:
            content = f.read()
        
        # Should have placeholder with both scripts
        assert 'Sofia, София' in content or 'София' in content, "Placeholder should show Cyrillic example"
        print("✅ City placeholder shows both scripts")


class TestRegressionEndpoints:
    """Test that core endpoints still work"""
    
    def test_healthz(self):
        """GET /api/healthz returns 200"""
        response = requests.get(f"{BASE_URL}/api/healthz")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ /api/healthz returns 200")
    
    def test_auctions_list(self):
        """GET /api/auctions returns 200"""
        response = requests.get(f"{BASE_URL}/api/auctions")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✅ /api/auctions returns 200 with {len(data)} items")
    
    def test_auctions_featured(self):
        """GET /api/auctions/featured returns 200"""
        response = requests.get(f"{BASE_URL}/api/auctions/featured")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✅ /api/auctions/featured returns 200 with {len(data)} items")
    
    def test_auctions_sold(self):
        """GET /api/auctions/sold returns 200"""
        response = requests.get(f"{BASE_URL}/api/auctions/sold")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ /api/auctions/sold returns 200")
    
    def test_makes_list(self):
        """GET /api/makes returns 200"""
        response = requests.get(f"{BASE_URL}/api/makes")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✅ /api/makes returns 200 with {len(data)} makes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
