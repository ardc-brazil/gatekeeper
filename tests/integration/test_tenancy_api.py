import uuid
from tests.integration.utils.assertions import (
    assert_status_code,
    assert_response_matches_dict,
    assert_json_response,
    assert_response_contains_fields,
)


class TestTenancyGetEndpoints:
    """Integration tests for Tenancy GET endpoints."""

    def test_get_all_tenancies_success(self, http_client, valid_headers):
        """Test getting all tenancies successfully."""
        # Act
        response = http_client.get("/tenancies/", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert isinstance(data, list)
        # Should have seeded tenancies from seed_clients.sql
        assert len(data) > 0

        # Check structure of first tenancy
        if data:
            tenancy = data[0]
            assert "name" in tenancy
            assert "is_enabled" in tenancy
            assert isinstance(tenancy["name"], str)
            assert isinstance(tenancy["is_enabled"], bool)

    def test_get_all_tenancies_unauthorized_401(self, http_client, no_auth_headers):
        """Test getting all tenancies without authentication returns 401."""
        # Act
        response = http_client.get("/tenancies/", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 401)
        assert_response_matches_dict(response, {"detail": "Unauthorized"})

    def test_get_tenancy_by_name_success(self, http_client, valid_headers):
        """Test getting a specific tenancy by name."""
        # Act - Use a seeded tenancy name
        response = http_client.get(
            "/tenancies/datamap/production/data-amazon", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 200)
        assert_response_contains_fields(
            response, {"name": "datamap/production/data-amazon", "is_enabled": True}
        )

    def test_get_tenancy_by_name_with_slash_path(self, http_client, valid_headers):
        """Test getting tenancy with path containing slashes."""
        # Act - Test with root path
        response = http_client.get("/tenancies/", headers=valid_headers)

        # Assert - Should return all tenancies (not a specific one)
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert isinstance(data, list)

    def test_get_tenancy_by_name_not_found_404(self, http_client, valid_headers):
        """Test getting a non-existent tenancy returns 404."""
        # Act
        response = http_client.get(
            "/tenancies/nonexistent/tenancy", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 404)
        # Note: The controller returns a Response object with status_code set, not a dict
        # So we just check the status code

    def test_get_tenancy_by_name_unauthorized_401(self, http_client, no_auth_headers):
        """Test getting tenancy by name without authentication returns 401."""
        # Act
        response = http_client.get(
            "/tenancies/datamap/production/data-amazon", headers=no_auth_headers
        )

        # Assert
        assert_status_code(response, 401)
        assert_response_matches_dict(response, {"detail": "Unauthorized"})

    def test_get_tenancy_with_is_enabled_param(self, http_client, valid_headers):
        """Test getting tenancy with is_enabled query parameter."""
        # Act
        response = http_client.get(
            "/tenancies/datamap/production/data-amazon?is_enabled=true",
            headers=valid_headers,
        )

        # Assert
        assert_status_code(response, 200)
        assert_response_contains_fields(
            response, {"name": "datamap/production/data-amazon", "is_enabled": True}
        )


class TestTenancyCRUDOperations:
    """Integration tests for Tenancy CRUD operations."""

    def test_create_tenancy_success_201(self, http_client, valid_headers):
        """Test creating a new tenancy successfully."""
        # Arrange - Use unique name to avoid conflicts
        unique_name = f"test/tenancy/creation/{str(uuid.uuid4())[:8]}"
        tenancy_data = {"name": unique_name, "is_enabled": True}

        # Act
        response = http_client.post(
            "/tenancies/", json=tenancy_data, headers=valid_headers
        )

        # Assert
        assert_status_code(response, 201)
        # POST returns empty response body

    def test_create_tenancy_invalid_data_422(self, http_client, valid_headers):
        """Test creating tenancy with invalid data returns 422."""
        # Arrange
        invalid_data = {
            "name": "",  # Empty name should be invalid
            "is_enabled": "not_a_boolean",  # Wrong type
        }

        # Act
        response = http_client.post(
            "/tenancies/", json=invalid_data, headers=valid_headers
        )

        # Assert
        assert_status_code(response, 422)
        data = assert_json_response(response)
        assert "detail" in data

    def test_create_tenancy_unauthorized_401(self, http_client, no_auth_headers):
        """Test creating tenancy without authentication returns 401."""
        # Arrange
        tenancy_data = {"name": "test/unauthorized/creation", "is_enabled": True}

        # Act
        response = http_client.post(
            "/tenancies/", json=tenancy_data, headers=no_auth_headers
        )

        # Assert
        assert_status_code(response, 401)
        assert_response_matches_dict(response, {"detail": "Unauthorized"})

    def test_update_tenancy_success(self, http_client, valid_headers):
        """Test updating an existing tenancy successfully."""
        # Arrange - First create a tenancy with unique name
        unique_name = f"test/tenancy/update/{str(uuid.uuid4())[:8]}"
        create_data = {"name": unique_name, "is_enabled": True}
        create_response = http_client.post(
            "/tenancies/", json=create_data, headers=valid_headers
        )
        assert_status_code(create_response, 201)

        # Arrange - Update data
        update_data = {"name": f"{unique_name}_updated", "is_enabled": False}

        # Act
        response = http_client.put(
            f"/tenancies/{unique_name}", json=update_data, headers=valid_headers
        )

        # Assert
        assert_status_code(response, 200)
        # PUT returns empty response body

    def test_update_tenancy_not_found_404(self, http_client, valid_headers):
        """Test updating a non-existent tenancy returns 404."""
        # Arrange
        update_data = {"name": "test/tenancy/notfound", "is_enabled": False}

        # Act
        response = http_client.put(
            "/tenancies/nonexistent/tenancy", json=update_data, headers=valid_headers
        )

        # Assert
        assert_status_code(response, 404)
        # Note: Service throws NotFoundException, but controller doesn't handle it properly
        # This might return 500 instead of 404 - we'll see what happens

    def test_update_tenancy_unauthorized_401(self, http_client, no_auth_headers):
        """Test updating tenancy without authentication returns 401."""
        # Arrange
        update_data = {"name": "test/tenancy/unauthorized", "is_enabled": False}

        # Act
        response = http_client.put(
            "/tenancies/datamap/production/data-amazon",
            json=update_data,
            headers=no_auth_headers,
        )

        # Assert
        assert_status_code(response, 401)
        assert_response_matches_dict(response, {"detail": "Unauthorized"})

    def test_delete_tenancy_success_204(self, http_client, valid_headers):
        """Test deleting (disabling) a tenancy successfully."""
        # Arrange - First create a tenancy with unique name
        unique_name = f"test/tenancy/delete/{str(uuid.uuid4())[:8]}"
        create_data = {"name": unique_name, "is_enabled": True}
        create_response = http_client.post(
            "/tenancies/", json=create_data, headers=valid_headers
        )
        assert_status_code(create_response, 201)

        # Act
        response = http_client.delete(
            f"/tenancies/{unique_name}", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 204)
        # DELETE returns empty response body

    def test_delete_tenancy_not_found_404(self, http_client, valid_headers):
        """Test deleting a non-existent tenancy returns 404."""
        # Act
        response = http_client.delete(
            "/tenancies/nonexistent/tenancy", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 404)
        # Note: Service throws NotFoundException, but controller doesn't handle it properly
        # This might return 500 instead of 404 - we'll see what happens

    def test_delete_tenancy_unauthorized_401(self, http_client, no_auth_headers):
        """Test deleting tenancy without authentication returns 401."""
        # Act
        response = http_client.delete(
            "/tenancies/datamap/production/data-amazon", headers=no_auth_headers
        )

        # Assert
        assert_status_code(response, 401)
        assert_response_matches_dict(response, {"detail": "Unauthorized"})

    def test_enable_tenancy_success(self, http_client, valid_headers):
        """Test enabling a disabled tenancy successfully."""
        # Arrange - First create and then disable a tenancy with unique name
        unique_name = f"test/tenancy/enable/{str(uuid.uuid4())[:8]}"
        create_data = {"name": unique_name, "is_enabled": True}
        create_response = http_client.post(
            "/tenancies/", json=create_data, headers=valid_headers
        )
        assert_status_code(create_response, 201)

        # Disable it
        delete_response = http_client.delete(
            f"/tenancies/{unique_name}", headers=valid_headers
        )
        assert_status_code(delete_response, 204)

        # Act - Enable it
        response = http_client.post(
            f"/tenancies/{unique_name}/enable", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 200)
        # POST returns empty response body

    def test_enable_tenancy_not_found_404(self, http_client, valid_headers):
        """Test enabling a non-existent tenancy returns 404."""
        # Act
        response = http_client.post(
            "/tenancies/nonexistent/tenancy/enable", headers=valid_headers
        )

        # Assert
        assert_status_code(response, 404)
        # Note: Service throws NotFoundException, but controller doesn't handle it properly
        # This might return 500 instead of 404 - we'll see what happens

    def test_enable_tenancy_unauthorized_401(self, http_client, no_auth_headers):
        """Test enabling tenancy without authentication returns 401."""
        # Act
        response = http_client.post(
            "/tenancies/datamap/production/data-amazon/enable", headers=no_auth_headers
        )

        # Assert
        assert_status_code(response, 401)
        assert_response_matches_dict(response, {"detail": "Unauthorized"})


class TestTenancyPathHandling:
    """Integration tests for Tenancy path handling with slashes."""

    def test_tenancy_path_with_multiple_slashes(self, http_client, valid_headers):
        """Test tenancy paths with multiple slashes."""
        # Arrange - Use unique name to avoid conflicts
        unique_name = f"test/multiple/slashes/in/path/{str(uuid.uuid4())[:8]}"
        tenancy_data = {"name": unique_name, "is_enabled": True}

        # Act - Create
        create_response = http_client.post(
            "/tenancies/", json=tenancy_data, headers=valid_headers
        )
        assert_status_code(create_response, 201)

        # Act - Get
        response = http_client.get(f"/tenancies/{unique_name}", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        assert_response_contains_fields(
            response, {"name": unique_name, "is_enabled": True}
        )

    def test_tenancy_path_with_special_characters(self, http_client, valid_headers):
        """Test tenancy paths with special characters."""
        # Arrange - Use unique name to avoid conflicts
        unique_name = f"test/special-chars_123/{str(uuid.uuid4())[:8]}"
        tenancy_data = {"name": unique_name, "is_enabled": True}

        # Act - Create
        create_response = http_client.post(
            "/tenancies/", json=tenancy_data, headers=valid_headers
        )
        assert_status_code(create_response, 201)

        # Act - Get
        response = http_client.get(f"/tenancies/{unique_name}", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        assert_response_contains_fields(
            response, {"name": unique_name, "is_enabled": True}
        )

    def test_tenancy_path_root_slash(self, http_client, valid_headers):
        """Test tenancy path with just root slash."""
        # Act - This should return all tenancies, not a specific one
        response = http_client.get("/tenancies/", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert isinstance(data, list)
        # Should have seeded tenancies
        assert len(data) > 0


class TestTenancyWorkflow:
    """Integration tests for complete Tenancy workflows."""

    def test_tenancy_full_lifecycle(self, http_client, valid_headers):
        """Test complete tenancy lifecycle: create -> get -> update -> disable -> enable -> get."""
        # Use unique name to avoid conflicts
        unique_suffix = str(uuid.uuid4())[:8]
        tenancy_name = f"test/lifecycle/tenancy/{unique_suffix}"

        # 1. Create tenancy
        create_data = {"name": tenancy_name, "is_enabled": True}
        create_response = http_client.post(
            "/tenancies/", json=create_data, headers=valid_headers
        )
        assert_status_code(create_response, 201)

        # 2. Get tenancy (should be enabled)
        get_response = http_client.get(
            f"/tenancies/{tenancy_name}", headers=valid_headers
        )
        assert_status_code(get_response, 200)
        assert_response_contains_fields(
            get_response, {"name": tenancy_name, "is_enabled": True}
        )

        # 3. Update tenancy
        updated_name = f"{tenancy_name}_updated"
        update_data = {"name": updated_name, "is_enabled": True}
        update_response = http_client.put(
            f"/tenancies/{tenancy_name}", json=update_data, headers=valid_headers
        )
        assert_status_code(update_response, 200)

        # 4. Get updated tenancy
        get_updated_response = http_client.get(
            f"/tenancies/{updated_name}", headers=valid_headers
        )
        assert_status_code(get_updated_response, 200)
        assert_response_contains_fields(
            get_updated_response, {"name": updated_name, "is_enabled": True}
        )

        # 5. Disable tenancy
        disable_response = http_client.delete(
            f"/tenancies/{updated_name}", headers=valid_headers
        )
        assert_status_code(disable_response, 204)

        # 6. Try to get disabled tenancy (should not find it with default is_enabled=true)
        get_disabled_response = http_client.get(
            f"/tenancies/{updated_name}", headers=valid_headers
        )
        assert_status_code(get_disabled_response, 404)

        # 7. Enable tenancy
        enable_response = http_client.post(
            f"/tenancies/{updated_name}/enable", headers=valid_headers
        )
        assert_status_code(enable_response, 200)

        # 8. Get re-enabled tenancy
        get_reenabled_response = http_client.get(
            f"/tenancies/{updated_name}", headers=valid_headers
        )
        assert_status_code(get_reenabled_response, 200)
        assert_response_contains_fields(
            get_reenabled_response, {"name": updated_name, "is_enabled": True}
        )
