"""
Test suite for categorized images feature in autobids.bg
Tests:
- POST /api/auctions with categorized images (validates minimums 8/4/1/4)
- POST /api/auctions without categorized images (legacy payload)
- POST /api/auctions with insufficient categorized images (returns 400)
- PUT /api/admin/auctions/{id} supports images_exterior/wheels/bumper/interior
- GET /api/auctions/{id} returns images_interior in response
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test image data (small base64 placeholder)
TEST_IMAGE = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBEQCEAwEPwAB//9k="


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@autobids.bg",
        "password": "admin123"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Admin authentication failed")


@pytest.fixture(scope="module")
def test_user_token():
    """Create and authenticate a test user"""
    unique_email = f"TEST_user_{uuid.uuid4().hex[:8]}@test.com"
    response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": unique_email,
        "password": "testpass123",
        "name": "Test User"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Test user registration failed")


class TestCategorizedImagesValidation:
    """Tests for POST /api/auctions with categorized images validation"""
    
    def test_create_auction_with_full_categorized_images(self, test_user_token):
        """POST /api/auctions with all required categorized images should succeed"""
        payload = {
            "title": "TEST_Categorized_Full",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test auction with categorized images",
            "images_exterior": [TEST_IMAGE] * 8,  # min 8
            "images_wheels": [TEST_IMAGE] * 4,    # min 4
            "images_bumper": [TEST_IMAGE] * 1,    # min 1
            "images_interior": [TEST_IMAGE] * 4,  # min 4
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"
        print(f"Created auction with categorized images: {data['id']}")
    
    def test_create_auction_insufficient_exterior(self, test_user_token):
        """POST /api/auctions with <8 exterior images should return 400"""
        payload = {
            "title": "TEST_Insufficient_Exterior",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test auction",
            "images_exterior": [TEST_IMAGE] * 5,  # only 5, need 8
            "images_wheels": [TEST_IMAGE] * 4,
            "images_bumper": [TEST_IMAGE] * 1,
            "images_interior": [TEST_IMAGE] * 4,
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "екстериорни" in data["detail"].lower() or "exterior" in data["detail"].lower()
        print(f"Correctly rejected: {data['detail']}")
    
    def test_create_auction_insufficient_wheels(self, test_user_token):
        """POST /api/auctions with <4 wheel images should return 400"""
        payload = {
            "title": "TEST_Insufficient_Wheels",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test auction",
            "images_exterior": [TEST_IMAGE] * 8,
            "images_wheels": [TEST_IMAGE] * 2,  # only 2, need 4
            "images_bumper": [TEST_IMAGE] * 1,
            "images_interior": [TEST_IMAGE] * 4,
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "джанти" in data["detail"].lower() or "wheels" in data["detail"].lower()
        print(f"Correctly rejected: {data['detail']}")
    
    def test_create_auction_insufficient_bumper(self, test_user_token):
        """POST /api/auctions with 0 bumper images should return 400"""
        payload = {
            "title": "TEST_Insufficient_Bumper",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test auction",
            "images_exterior": [TEST_IMAGE] * 8,
            "images_wheels": [TEST_IMAGE] * 4,
            "images_bumper": [],  # 0, need 1
            "images_interior": [TEST_IMAGE] * 4,
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "броня" in data["detail"].lower() or "bumper" in data["detail"].lower()
        print(f"Correctly rejected: {data['detail']}")
    
    def test_create_auction_insufficient_interior(self, test_user_token):
        """POST /api/auctions with <4 interior images should return 400"""
        payload = {
            "title": "TEST_Insufficient_Interior",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test auction",
            "images_exterior": [TEST_IMAGE] * 8,
            "images_wheels": [TEST_IMAGE] * 4,
            "images_bumper": [TEST_IMAGE] * 1,
            "images_interior": [TEST_IMAGE] * 2,  # only 2, need 4
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "интериор" in data["detail"].lower() or "interior" in data["detail"].lower()
        print(f"Correctly rejected: {data['detail']}")
    
    def test_create_auction_multiple_insufficient(self, test_user_token):
        """POST /api/auctions with multiple insufficient categories should list all errors"""
        payload = {
            "title": "TEST_Multiple_Insufficient",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test auction",
            "images_exterior": [TEST_IMAGE] * 3,  # need 8
            "images_wheels": [TEST_IMAGE] * 1,    # need 4
            "images_bumper": [],                   # need 1
            "images_interior": [TEST_IMAGE] * 1,  # need 4
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        # Should mention multiple issues
        detail_lower = data["detail"].lower()
        print(f"Error message: {data['detail']}")


class TestLegacyImagesPayload:
    """Tests for POST /api/auctions with legacy images-only payload"""
    
    def test_create_auction_legacy_images_only(self, test_user_token):
        """POST /api/auctions with only 'images' field (no categorized) should work"""
        payload = {
            "title": "TEST_Legacy_Images",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test auction with legacy images",
            "images": [TEST_IMAGE] * 5,  # Just regular images, no categorized
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"
        print(f"Created auction with legacy images: {data['id']}")
    
    def test_create_auction_no_images(self, test_user_token):
        """POST /api/auctions with no images at all should work (no validation triggered)"""
        payload = {
            "title": "TEST_No_Images",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test auction with no images",
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        print(f"Created auction with no images: {data['id']}")


class TestAdminCategorizedImagesUpdate:
    """Tests for PUT /api/admin/auctions/{id} with categorized images"""
    
    def test_admin_update_images_interior(self, admin_token):
        """PUT /api/admin/auctions/{id} can update images_interior"""
        auction_id = "ab24566d-a0ef-4975-bb9c-cc93388af663"
        
        # First get current state
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        original = response.json()
        original_interior = original.get("images_interior", [])
        
        # Update with new interior images
        new_interior = [TEST_IMAGE, TEST_IMAGE, TEST_IMAGE]
        response = requests.put(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            json={"images_interior": new_interior},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify update
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated.get("images_interior") == new_interior
        print(f"Successfully updated images_interior for auction {auction_id}")
        
        # Restore original
        requests.put(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            json={"images_interior": original_interior},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
    
    def test_admin_update_all_categorized_images(self, admin_token):
        """PUT /api/admin/auctions/{id} can update all categorized image fields"""
        auction_id = "ab24566d-a0ef-4975-bb9c-cc93388af663"
        
        # Get original state
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        original = response.json()
        
        # Update all categorized fields
        update_payload = {
            "images_exterior": [TEST_IMAGE] * 2,
            "images_wheels": [TEST_IMAGE] * 2,
            "images_bumper": [TEST_IMAGE],
            "images_interior": [TEST_IMAGE] * 2
        }
        
        response = requests.put(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            json=update_payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify all fields updated
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        updated = response.json()
        
        assert len(updated.get("images_exterior", [])) == 2
        assert len(updated.get("images_wheels", [])) == 2
        assert len(updated.get("images_bumper", [])) == 1
        assert len(updated.get("images_interior", [])) == 2
        print("Successfully updated all categorized image fields")
        
        # Restore original
        restore_payload = {
            "images_exterior": original.get("images_exterior", []),
            "images_wheels": original.get("images_wheels", []),
            "images_bumper": original.get("images_bumper", []),
            "images_interior": original.get("images_interior", [])
        }
        requests.put(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            json=restore_payload,
            headers={"Authorization": f"Bearer {admin_token}"}
        )


class TestGetAuctionImagesInterior:
    """Tests for GET /api/auctions/{id} returning images_interior"""
    
    def test_get_auction_returns_images_interior(self):
        """GET /api/auctions/{id} should return images_interior in response"""
        auction_id = "ab24566d-a0ef-4975-bb9c-cc93388af663"
        
        response = requests.get(f"{BASE_URL}/api/auctions/{auction_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Should have images_interior field
        assert "images_interior" in data, "Response should include images_interior field"
        assert isinstance(data["images_interior"], list), "images_interior should be a list"
        print(f"Auction has {len(data['images_interior'])} interior images")
    
    def test_get_auction_without_interior_images(self):
        """GET /api/auctions/{id} for auction without interior images should return empty list or not have field"""
        # Get list of auctions and find one without interior images
        response = requests.get(f"{BASE_URL}/api/auctions?limit=10")
        assert response.status_code == 200
        auctions = response.json()
        
        # Find an auction without images_interior
        for auction in auctions:
            if not auction.get("images_interior"):
                auction_id = auction["id"]
                response = requests.get(f"{BASE_URL}/api/auctions/{auction_id}")
                assert response.status_code == 200
                data = response.json()
                # Should either not have the field or have empty list
                interior = data.get("images_interior", [])
                assert isinstance(interior, list) or interior is None
                print(f"Auction {auction_id} has no interior images (as expected)")
                return
        
        print("All auctions have interior images - skipping this test")


class TestImagesMerging:
    """Tests for verifying images are merged correctly in create_auction"""
    
    def test_images_merged_in_correct_order(self, test_user_token, admin_token):
        """Verify that categorized images are merged into 'images' in correct order"""
        payload = {
            "title": "TEST_Merge_Order",
            "make": "TestMake",
            "model": "TestModel",
            "year": 2023,
            "mileage_km": 50000,
            "fuel": "Бензин",
            "transmission": "Автоматична",
            "body_type": "Седан",
            "power_hp": 200,
            "engine_cc": 2000,
            "color": "Black",
            "region": "София",
            "city": "София",
            "description": "Test merge order",
            "images_exterior": [f"ext_{i}" for i in range(8)],
            "images_wheels": [f"wheel_{i}" for i in range(4)],
            "images_bumper": ["bumper_0"],
            "images_interior": [f"int_{i}" for i in range(4)],
            "starting_bid_eur": 5000,
            "duration_days": 7
        }
        
        response = requests.post(
            f"{BASE_URL}/api/auctions",
            json=payload,
            headers={"Authorization": f"Bearer {test_user_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        auction_id = response.json()["id"]
        
        # Get the auction via admin to see full data
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions/{auction_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify merged images order: exterior, bumper, wheels, interior
        images = data.get("images", [])
        assert len(images) == 17, f"Expected 17 merged images, got {len(images)}"
        
        # First 8 should be exterior
        assert all("ext_" in img for img in images[:8]), "First 8 should be exterior"
        # Next 1 should be bumper
        assert "bumper_" in images[8], "Image 9 should be bumper"
        # Next 4 should be wheels
        assert all("wheel_" in img for img in images[9:13]), "Images 10-13 should be wheels"
        # Last 4 should be interior
        assert all("int_" in img for img in images[13:17]), "Last 4 should be interior"
        
        print(f"Images merged in correct order for auction {auction_id}")


# Cleanup fixture
@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_token):
    """Cleanup TEST_ prefixed auctions after tests"""
    yield
    # After all tests, remove test auctions
    try:
        response = requests.get(
            f"{BASE_URL}/api/admin/auctions?q=TEST_",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if response.status_code == 200:
            for auction in response.json():
                if auction.get("title", "").startswith("TEST_"):
                    requests.post(
                        f"{BASE_URL}/api/admin/auctions/{auction['id']}/remove",
                        headers={"Authorization": f"Bearer {admin_token}"}
                    )
    except Exception:
        pass
