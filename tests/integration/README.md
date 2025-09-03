# Integration Tests Setup

## Overview

This integration test suite provides end-to-end testing for the Gatekeeper API by making real HTTP requests to a running service instance. The DOI service is mocked using WireMock to avoid dependencies on external services during testing.

## Architecture

- **Target Service**: Real Gatekeeper instance running on `http://localhost:9092`
- **DOI Mocking**: WireMock server running on `http://localhost:8083`
- **Database**: Real PostgreSQL instance (same as local development)
- **Storage**: Real MinIO instance (same as local development)
- **Authentication**: Uses configured API keys from `integration-test.env`

## Quick Start

### 1. Choose Your Testing Approach

**Quick Testing (WireMock only)**: 
- Fastest option
- Requires manual service setup
- Good for rapid iteration during development

**Full Infrastructure Testing (Docker containers)**:
- Uses existing containers with same ports
- May conflict with running development services
- Good for testing against exact development setup

**Isolated Container Testing**:
- Completely separate containers with `_test_integration` suffix
- Different ports to avoid conflicts
- No interference with development or manual testing
- **Recommended for CI/CD and conflict-free testing**

#### Port Mappings for Isolated Container Testing

| Service | Development Port | Integration Test Port |
|---------|------------------|----------------------|
| Gatekeeper API | 9092 | 9093 |
| MinIO API | 9000 | 9002 |
| MinIO Console | 9001 | 9003 |
| PostgreSQL | 5432 | 5433 |
| PGAdmin | 5050 | 5051 |
| TUSd | 1080 | 1081 |
| WireMock | - | 8083 |

### 2. Prerequisites (Quick Testing Only)

If using quick testing approach, ensure you have the following services running:
```bash
# Start database and MinIO
make ENV_FILE_PATH=local.env docker-run-db

# Start Gatekeeper application
make ENV_FILE_PATH=integration-test.env python-run
```

For full infrastructure testing, no manual setup required!

### 3. Run Integration Tests

**Using Makefile Commands (Recommended)**

*Complete Workflow (Recommended):*
```bash
# Complete isolated environment + tests + cleanup
make ENV_FILE_PATH=integration-test.env integration-test-full
```

*Manual Container Management:*
```bash
# Build containers
make ENV_FILE_PATH=integration-test.env integration-test-build

# Start isolated containers
make ENV_FILE_PATH=integration-test.env integration-test-up

# Run tests
make ENV_FILE_PATH=integration-test.env integration-test-run

# Stop containers
make integration-test-down

# Additional commands:
make integration-test-restart           # Restart containers
make integration-test-logs              # View container logs
make integration-test-clean             # Remove containers + volumes
```

*Run Specific Tests:*
```bash
# Run specific test file
make ENV_FILE_PATH=integration-test.env TEST_PATH=tests/integration/test_dataset_snapshot.py integration-test-run-specific

# Run specific test function (using pytest directly)
ENV_FILE_PATH=integration-test.env pytest tests/integration/test_dataset_snapshot.py::TestDatasetSnapshotEndpoints::test_get_latest_snapshot_with_nonexistent_dataset -v
```

**Direct pytest (Advanced):**
```bash
# Make sure containers are running first
make ENV_FILE_PATH=integration-test.env integration-test-up

# Run tests directly with pytest
ENV_FILE_PATH=integration-test.env pytest tests/integration/ -v

# Clean up after
make integration-test-down
```

## Configuration

### Environment Variables

The integration tests use `integration-test.env` which is based on `local.env` but with these key differences:

```bash
# DOI Service (WireMock instead of real DataCite)
DOI_BASE_URL=http://localhost:8083
DOI_LOGIN=MOCK_USER
DOI_PASSWORD=MOCK_PASS

# Integration Test Specific
INTEGRATION_BASE_URL=http://localhost:9092
INTEGRATION_API_KEY=5060b1a2-9aaf-48db-871a-0839007fd478
INTEGRATION_API_SECRET=g*aZkbWom3deiAX-vtoT
INTEGRATION_USER_ID=cbb0a683-630f-4b86-8b45-91b90a6fce1c
INTEGRATION_TENANCY=datamap/production/data-amazon
```

### WireMock Configuration

WireMock mappings are located in:
- **Mappings**: `tests/integration/wiremock/mappings/` - API endpoint configurations
- **Responses**: `tests/integration/wiremock/__files/` - Response body templates

### Supported DOI API Endpoints

The WireMock setup covers all DOI operations used by your application:
- `POST /dois` - Create DOI (returns 201 with generated DOI)
- `GET /dois/{repository}/{identifier}` - Get DOI (returns 200 or 404)
- `PUT /dois/{identifier}` - Update DOI (returns 200)
- `DELETE /dois/{repository}/{identifier}` - Delete DOI (returns 204)

## Test Coverage

### Dataset Snapshot Endpoints

✅ **Implemented Tests:**
- `GET /datasets/{id}/snapshot` - Latest snapshot endpoint
- `GET /datasets/{id}/versions/{version}/snapshot` - Version-specific snapshot endpoint

**Error Scenarios Covered:**
- ✅ 404 - Non-existent dataset ID
- ✅ 404 - Non-existent version name
- ✅ 422 - Invalid UUID format
- ✅ Public endpoint verification (no auth required)
- ✅ Special characters in version names
- ✅ Edge cases (long version names, empty names)

**Happy Path Tests:**
- ⏳ 200 - Successful snapshot retrieval (requires published dataset setup)
- ⏳ Schema validation for response structure
- ⏳ Content validation (DOI info, files summary, etc.)

> **Note**: Happy path tests are currently skipped because they require a complete DOI workflow with published datasets and snapshot files in MinIO. These can be enabled once the dataset publishing and snapshot generation workflow is fully implemented.

## Debugging

### View WireMock Logs
```bash
make integration-test-logs

# Or directly:
docker logs gatekeeper-wiremock
```

### Check WireMock Admin Interface
```bash
# List all mappings
curl http://localhost:8083/__admin/mappings | jq

# Health check
curl http://localhost:8083/__admin/health

# View requests received
curl http://localhost:8083/__admin/requests | jq
```

### Test Individual Endpoints
```bash
# Test the snapshot endpoint directly
curl "http://localhost:9092/api/v1/datasets/123e4567-e89b-12d3-a456-426614174000/snapshot"

# Test WireMock directly
curl "http://localhost:8083/dois" \
  -H "Content-Type: application/vnd.api+json" \
  -H "Authorization: Basic $(echo -n 'MOCK_USER:MOCK_PASS' | base64)"
```

### Common Issues

1. **WireMock not starting**: 
   - Check port 8083 is available: `lsof -i :8083`
   - Check Docker is running: `docker ps`

2. **Tests failing with connection errors**:
   - Ensure Gatekeeper is running on port 9092: `curl http://localhost:9092/api/health`
   - Check `integration-test.env` configuration

3. **Database connection errors**:
   - Verify PostgreSQL is running: `make ENV_FILE_PATH=local.env docker-run-db`
   - Check database migrations: `make ENV_FILE_PATH=integration-test.env db-upgrade`

4. **DOI mock issues**:
   - Check WireMock mappings: `curl http://localhost:8083/__admin/mappings`
   - View WireMock logs: `make integration-test-logs`

### Reset Environment

```bash
# Full reset
make integration-test-teardown
make ENV_FILE_PATH=local.env docker-stop
make ENV_FILE_PATH=local.env docker-run-db
make integration-test-setup

# Quick reset (keep services running)
make integration-test-teardown
make integration-test-setup
```

## Directory Structure

```
tests/integration/
├── README.md                     # This file
├── conftest.py                   # pytest configuration & fixtures
├── config.py                     # test environment configuration
├── fixtures/
│   ├── __init__.py
│   ├── auth.py                   # authentication fixtures
│   └── dataset.py                # dataset test data fixtures
├── utils/
│   ├── __init__.py
│   ├── http_client.py            # HTTP client wrapper
│   └── assertions.py             # common assertion helpers
├── test_dataset_snapshot.py      # snapshot endpoint tests
└── wiremock/
    ├── mappings/                 # WireMock API mappings
    │   ├── doi-post-create.json
    │   ├── doi-get-success.json
    │   ├── doi-get-not-found.json
    │   ├── doi-put-update.json
    │   └── doi-delete.json
    └── __files/                  # WireMock response templates
        ├── doi-created-response.json
        ├── doi-get-response.json
        └── doi-updated-response.json
```

## Writing New Tests

### 1. Create Test File

Follow the naming convention: `test_{feature}.py`

```python
"""Integration tests for {feature} endpoints."""
import pytest
from tests.integration.utils.assertions import assert_status_code, assert_json_response

class TestMyFeature:
    def test_my_endpoint_success(self, http_client, auth_headers):
        # Arrange
        test_data = {...}
        
        # Act
        response = http_client.post("/my-endpoint", json=test_data, headers=auth_headers)
        
        # Assert
        assert_status_code(response, 201)
        data = assert_json_response(response)
        assert data["id"] is not None
```

### 2. Add Test Data Fixtures

Add fixtures to `fixtures/` directory:

```python
class MyFeatureFixture:
    @staticmethod
    def get_test_data():
        return {...}
    
    def create_test_resource(self):
        # Use HTTP client to create via API
        pass
```

### 3. Use Provided Utilities

- **HTTP Client**: `http_client` fixture for making requests
- **Auth Headers**: `auth_headers`, `no_auth_headers`, `invalid_auth_headers` fixtures
- **Assertions**: Import from `tests.integration.utils.assertions`
- **Config**: Import from `tests.integration.config`

### 4. Test Both Happy and Error Paths

Always test:
- ✅ Success scenarios (200, 201, etc.)
- ✅ Not found scenarios (404)
- ✅ Validation errors (422)
- ✅ Authentication/authorization (401, 403) if applicable
- ✅ Edge cases (empty values, special characters)

## CI/CD Integration

The integration test suite is designed to be CI/CD friendly:

```yaml
# Example GitHub Actions workflow
- name: Run Integration Tests
  run: |
    # Start services
    make ENV_FILE_PATH=integration-test.env docker-run-db
    make ENV_FILE_PATH=integration-test.env python-run &
    
    # Wait for services to be ready
    sleep 10
    
    # Run tests
    make ENV_FILE_PATH=integration-test.env integration-test-full
```

## Next Steps

1. **Enable Happy Path Tests**: Once DOI workflow and snapshot generation is complete, remove `@pytest.mark.skip` from happy path tests
2. **Add More Endpoints**: Create integration tests for other API endpoints following the same pattern
3. **Test Data Management**: Implement proper test data cleanup if needed
4. **Performance Tests**: Add performance benchmarks to the integration test suite
5. **Contract Testing**: Consider adding API contract tests using the WireMock recordings
