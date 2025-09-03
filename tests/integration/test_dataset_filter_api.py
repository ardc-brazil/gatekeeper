"""
Integration tests for Dataset Filter API endpoints.
"""

from tests.integration.utils.assertions import (
    assert_status_code,
    assert_json_response,
    assert_response_matches_dict,
)


class TestDatasetFilterEndpoints:
    """Integration tests for Dataset Filter API endpoints."""

    def test_get_filters_success_200(self, http_client, valid_headers):
        """Test getting available filters successfully returns 200."""
        # Act
        response = http_client.get("/datasets/filters", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)
        assert isinstance(data, list)
        assert len(data) > 0

        # Check structure of first filter
        first_filter = data[0]
        assert "id" in first_filter
        assert "title" in first_filter
        assert "selection" in first_filter
        assert "options" in first_filter
        assert isinstance(first_filter["options"], list)

    def test_get_filters_unauthorized_401(self, http_client, no_auth_headers):
        """Test getting filters without authentication returns 401."""
        # Act
        response = http_client.get("/datasets/filters", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 401)
        assert_response_matches_dict(response, {"detail": "Unauthorized"})

    def test_get_filters_invalid_auth_500(self, http_client, invalid_headers):
        """Test getting filters with invalid authentication returns 500 (SQL error)."""
        # Act
        response = http_client.get("/datasets/filters", headers=invalid_headers)

        # Assert
        assert_status_code(response, 500)
        data = assert_json_response(response)
        assert "invalid input syntax for type uuid" in data["detail"]

    def test_get_filters_response_structure(self, http_client, valid_headers):
        """Test that filters response has correct structure."""
        # Act
        response = http_client.get("/datasets/filters", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)

        # Verify it's an array
        assert isinstance(data, list)

        # Check that we have expected filter types
        filter_ids = [filter_item["id"] for filter_item in data]
        expected_filters = [
            "date_range",
            "categories",
            "level",
            "data_type",
            "design_state",
        ]

        for expected_filter in expected_filters:
            assert (
                expected_filter in filter_ids
            ), f"Expected filter '{expected_filter}' not found in response"

    def test_get_filters_date_range_structure(self, http_client, valid_headers):
        """Test that date_range filter has correct structure."""
        # Act
        response = http_client.get("/datasets/filters", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)

        # Find date_range filter
        date_range_filter = next((f for f in data if f["id"] == "date_range"), None)
        assert date_range_filter is not None, "date_range filter not found"

        # Check structure
        assert date_range_filter["title"] == "Date range"
        assert date_range_filter["selection"] == "date-range"
        assert isinstance(date_range_filter["options"], list)
        assert len(date_range_filter["options"]) == 2

        # Check options structure
        options = date_range_filter["options"]
        assert options[0]["id"] == "date_from"
        assert options[0]["label"] == "From"
        assert options[0]["type"] == "date"

        assert options[1]["id"] == "date_to"
        assert options[1]["label"] == "To"
        assert options[1]["type"] == "date"

    def test_get_filters_categories_structure(self, http_client, valid_headers):
        """Test that categories filter has correct structure."""
        # Act
        response = http_client.get("/datasets/filters", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)

        # Find categories filter
        categories_filter = next((f for f in data if f["id"] == "categories"), None)
        assert categories_filter is not None, "categories filter not found"

        # Check structure
        assert categories_filter["title"] == "Category"
        assert categories_filter["selection"] == "multiple"
        assert isinstance(categories_filter["options"], list)
        assert len(categories_filter["options"]) > 0

        # Check first option structure
        first_option = categories_filter["options"][0]
        assert "id" in first_option
        assert "value" in first_option
        assert "label" in first_option

    def test_get_filters_level_structure(self, http_client, valid_headers):
        """Test that level filter has correct structure."""
        # Act
        response = http_client.get("/datasets/filters", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)

        # Find level filter
        level_filter = next((f for f in data if f["id"] == "level"), None)
        assert level_filter is not None, "level filter not found"

        # Check structure
        assert level_filter["title"] == "Level"
        assert level_filter["selection"] == "one"
        assert isinstance(level_filter["options"], list)
        assert len(level_filter["options"]) == 3

        # Check options
        options = level_filter["options"]
        level_values = [opt["value"] for opt in options]
        assert "L1" in level_values
        assert "L2" in level_values
        assert "L3" in level_values

    def test_get_filters_data_type_structure(self, http_client, valid_headers):
        """Test that data_type filter has correct structure."""
        # Act
        response = http_client.get("/datasets/filters", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)

        # Find data_type filter
        data_type_filter = next((f for f in data if f["id"] == "data_type"), None)
        assert data_type_filter is not None, "data_type filter not found"

        # Check structure
        assert data_type_filter["title"] == "Data Type"
        assert data_type_filter["selection"] == "multiple"
        assert isinstance(data_type_filter["options"], list)
        assert len(data_type_filter["options"]) == 2

        # Check options
        options = data_type_filter["options"]
        data_type_values = [opt["value"] for opt in options]
        assert "ROUTINE" in data_type_values
        assert "EXPORADIC" in data_type_values

    def test_get_filters_design_state_structure(self, http_client, valid_headers):
        """Test that design_state filter has correct structure."""
        # Act
        response = http_client.get("/datasets/filters", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)

        # Find design_state filter
        design_state_filter = next((f for f in data if f["id"] == "design_state"), None)
        assert design_state_filter is not None, "design_state filter not found"

        # Check structure
        assert design_state_filter["title"] == "Status"
        assert design_state_filter["selection"] == "one"
        assert isinstance(design_state_filter["options"], list)
        assert len(design_state_filter["options"]) == 2

        # Check options
        options = design_state_filter["options"]
        design_state_values = [opt["value"] for opt in options]
        assert "DRAFT" in design_state_values
        assert "PUBLISHED" in design_state_values

    def test_get_filters_multiple_requests(self, http_client, valid_headers):
        """Test that multiple requests return consistent results."""
        # Act - Make multiple requests
        responses = []
        for _ in range(3):
            response = http_client.get(
                "/datasets/filters", headers=valid_headers
            )
            responses.append(response)

        # Assert - All should be successful and identical
        for response in responses:
            assert_status_code(response, 200)
            data = assert_json_response(response)
            assert isinstance(data, list)
            assert len(data) > 0

        # Check that all responses are identical
        first_data = responses[0].json()
        for response in responses[1:]:
            assert response.json() == first_data

    def test_get_filters_path_variations(self, http_client, valid_headers):
        """Test different path variations."""
        # Act & Assert - With trailing slash
        response = http_client.get("/datasets/filters/", headers=valid_headers)
        assert_status_code(response, 200)

        # Act & Assert - With extra path segments
        response = http_client.get(
            "/datasets/filters/extra", headers=valid_headers
        )
        assert_status_code(response, 404)

    def test_get_filters_content_type(self, http_client, valid_headers):
        """Test that response has correct content type."""
        # Act
        response = http_client.get("/datasets/filters", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        assert response.headers["content-type"] == "application/json"
