from tests.integration.utils.assertions import (
    assert_status_code,
    assert_response_matches_dict,
    assert_json_response,
)


class TestInfrastructureHealthCheck:
    """Integration tests for Infrastructure health check endpoint."""

    def test_health_check_success(self, http_client, no_auth_headers):
        """Test health check endpoint returns 200 with online status."""
        # Act
        response = http_client.get("/health-check/", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 200)
        assert_response_matches_dict(response, {"status": "online"})

    def test_health_check_no_auth_required(self, http_client):
        """Test health check endpoint works without authentication headers."""
        # Act - Make request without any headers
        response = http_client.get("/health-check/")

        # Assert
        assert_status_code(response, 200)
        assert_response_matches_dict(response, {"status": "online"})

    def test_health_check_with_auth_headers(self, http_client, valid_headers):
        """Test health check endpoint works with authentication headers."""
        # Act
        response = http_client.get("/health-check/", headers=valid_headers)

        # Assert
        assert_status_code(response, 200)
        assert_response_matches_dict(response, {"status": "online"})

    def test_health_check_with_invalid_auth(self, http_client, invalid_headers):
        """Test health check endpoint works even with invalid auth headers."""
        # Act
        response = http_client.get("/health-check/", headers=invalid_headers)

        # Assert
        assert_status_code(response, 200)
        assert_response_matches_dict(response, {"status": "online"})

    def test_health_check_response_format(self, http_client, no_auth_headers):
        """Test health check response has correct JSON structure."""
        # Act
        response = http_client.get("/health-check/", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 200)
        data = assert_json_response(response)

        # Verify response structure
        assert isinstance(data, dict)
        assert "status" in data
        assert data["status"] == "online"

        # Verify no extra fields
        assert len(data.keys()) == 1

    def test_health_check_multiple_requests(self, http_client, no_auth_headers):
        """Test health check endpoint is consistent across multiple requests."""
        # Act - Make multiple requests
        responses = []
        for _ in range(3):
            response = http_client.get("/health-check/", headers=no_auth_headers)
            responses.append(response)

        # Assert - All responses should be identical
        for response in responses:
            assert_status_code(response, 200)
            assert_response_matches_dict(response, {"status": "online"})

    def test_health_check_different_http_methods(self, http_client, no_auth_headers):
        """Test health check endpoint only responds to GET requests."""
        # Act & Assert - POST should return 405 Method Not Allowed
        post_response = http_client.post("/health-check/", headers=no_auth_headers)
        assert_status_code(post_response, 405)

        # Act & Assert - PUT should return 405 Method Not Allowed
        put_response = http_client.put("/health-check/", headers=no_auth_headers)
        assert_status_code(put_response, 405)

        # Act & Assert - DELETE should return 405 Method Not Allowed
        delete_response = http_client.delete("/health-check/", headers=no_auth_headers)
        assert_status_code(delete_response, 405)

        # Act & Assert - GET should work
        get_response = http_client.get("/health-check/", headers=no_auth_headers)
        assert_status_code(get_response, 200)
        assert_response_matches_dict(get_response, {"status": "online"})

    def test_health_check_path_variations(self, http_client, no_auth_headers):
        """Test health check endpoint path variations."""
        # Act & Assert - Correct path should work
        response = http_client.get("/health-check/", headers=no_auth_headers)
        assert_status_code(response, 200)
        assert_response_matches_dict(response, {"status": "online"})

        # Act & Assert - Path without trailing slash should work (FastAPI redirects)
        response_no_slash = http_client.get("/health-check", headers=no_auth_headers)
        assert_status_code(response_no_slash, 200)
        assert_response_matches_dict(response_no_slash, {"status": "online"})

        # Act & Assert - Wrong path should return 404
        response_wrong = http_client.get("/health-check/wrong", headers=no_auth_headers)
        assert_status_code(response_wrong, 404)

    def test_health_check_content_type(self, http_client, no_auth_headers):
        """Test health check endpoint returns correct content type."""
        # Act
        response = http_client.get("/health-check/", headers=no_auth_headers)

        # Assert
        assert_status_code(response, 200)
        assert "application/json" in response.headers.get("content-type", "")
        assert_response_matches_dict(response, {"status": "online"})
