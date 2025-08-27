# Development Guidelines

## Development Loop & Validation

### 1. Feature Development Workflow

#### Before Starting
1. **Check if you aren't already in a different branch than main**
2. **Pull latest changes**: `git pull origin main`
3. **Create feature branch**: `git checkout -b feature/your-feature-name`
4. **Verify environment**: Ensure database and dependencies are up to date

#### During Development
1. **Write code** following the architecture patterns
2. **Run tests frequently** to catch issues early
3. **Check linting** before committing
4. **Document complex logic** with clear comments

#### Before Committing
1. **Run full test suite**: `pytest`
2. **Check linting**: `ruff check`
3. **Auto-fix linting issues**: `ruff check --fix`
4. **Format code**: `ruff format`
5. **Verify tests still pass**: `pytest` (after fixes)

### 2. Testing Strategy

#### Test Execution Commands
```bash
# Run all tests
pytest

# Run tests for specific module
pytest app/service/doi_test.py

# Run specific test function
pytest app/service/doi_test.py::test_create_manual_mode_success

# Run tests with coverage
pytest --cov=app

# Run tests in parallel (faster)
pytest -n auto

# Run tests and stop on first failure
pytest -x

# Run tests with verbose output
pytest -v
```

#### Test Organization
- **Contiguous files**: Keep test files next to source files
- **Naming convention**: `module_test.py` for test files
- **Test structure**: Arrange-Act-Assert pattern
- **Mocking**: Use `unittest.mock` for external dependencies

#### Test Coverage Requirements
- **Minimum coverage**: 80% for new features
- **Critical paths**: 100% coverage for authentication/authorization
- **Business logic**: 100% coverage for service layer
- **API endpoints**: Test all success and error scenarios

### 3. Code Quality Validation

#### Linting & Formatting
```bash
# Check for linting issues
ruff check

# Auto-fix linting issues
ruff check --fix

# Format code
ruff format

# Check for type issues (if mypy is configured)
mypy app/
```

#### Pre-commit Checklist
- [ ] All tests pass: `pytest`
- [ ] No linting errors: `ruff check`
- [ ] Code is formatted: `ruff format`
- [ ] Type hints are correct
- [ ] Documentation is updated
- [ ] No debug/print statements left

### 4. Database Development

#### Migration Workflow
```bash
# Create new migration
make MESSAGE="Add new column to datasets" db-create-migration

# Apply migrations
make db-upgrade

# Rollback last migration
make db-downgrade

# Check migration status
alembic current
alembic history
```

#### Database Testing
- **Test migrations**: Verify up/down migrations work
- **Test data integrity**: Ensure constraints are enforced
- **Test rollbacks**: Verify rollback scenarios work correctly
- **Performance**: Check query performance with indexes

### 5. API Development

#### Endpoint Testing
```bash
# Start application
make python-run

# Test endpoints manually
curl -X GET "http://localhost:9092/api/health"
curl -X POST "http://localhost:9092/api/datasets" \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "data": {}}'
```

#### API Validation
- **Request validation**: Test with invalid data
- **Response validation**: Verify response schemas
- **Authentication**: Test with/without valid tokens
- **Authorization**: Test with different user roles
- **Error handling**: Verify proper error responses

### 6. External Service Integration

#### DOI Service Testing
- **Mock responses**: Use unittest.mock for external calls
- **Error scenarios**: Test network failures, timeouts
- **State transitions**: Verify DOI state changes
- **Validation**: Test manual vs auto DOI modes

#### MinIO Integration Testing
- **File uploads**: Test various file types and sizes
- **Storage paths**: Verify correct bucket organization
- **Permissions**: Test access control
- **Cleanup**: Ensure temporary files are removed

### 7. Security Validation

#### Authentication Testing
- **Valid tokens**: Test with proper authentication
- **Invalid tokens**: Test with expired/malformed tokens
- **Missing tokens**: Test without authentication headers
- **Token refresh**: Test token renewal flows

#### Authorization Testing
- **Role-based access**: Test different user roles
- **Resource ownership**: Test user can only access own resources
- **Tenancy isolation**: Test multi-tenant data separation
- **Permission escalation**: Test privilege boundary checks

### 8. Performance Validation

#### Database Performance
- **Query optimization**: Use EXPLAIN ANALYZE
- **Index usage**: Verify indexes are being used
- **Connection pooling**: Monitor connection usage
- **Transaction management**: Check for long-running transactions

#### API Performance
- **Response times**: Monitor endpoint performance
- **Memory usage**: Check for memory leaks
- **Concurrent requests**: Test under load
- **Resource cleanup**: Verify proper cleanup

### 9. Deployment Validation

#### Local Environment
```bash
# Start full stack
make docker-deployment

# Start database only
make docker-run-db

# Run application locally
make python-run

# Check service health
docker ps
docker logs <container_name>
```

#### Production Readiness
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] Health checks passing
- [ ] Logging configured
- [ ] Monitoring enabled
- [ ] Backup strategy in place

### 10. Code Review Checklist

#### Before Submitting PR
- [ ] Feature branch is up to date with main
- [ ] All tests pass locally
- [ ] No linting errors
- [ ] Code follows architecture patterns
- [ ] Error handling is comprehensive
- [ ] Security considerations addressed
- [ ] Documentation is updated
- [ ] No hardcoded values
- [ ] Proper logging implemented

#### During Code Review
- [ ] Architecture compliance
- [ ] Security best practices
- [ ] Error handling adequacy
- [ ] Test coverage completeness
- [ ] Performance implications
- [ ] Maintainability concerns
- [ ] Documentation clarity

### 11. Troubleshooting Common Issues

#### Test Failures
```bash
# Debug test failures
pytest -v -s --tb=short

# Run specific failing test
pytest -xvs app/service/doi_test.py::test_failing_function

# Check test coverage for specific file
pytest --cov=app.service.doi app/service/doi_test.py
```

#### Database Issues
```bash
# Check database connection
make docker-run-db

# Reset database (development only)
docker-compose -f docker-compose-database.yaml down -v
make docker-run-db
make db-upgrade
```

#### Linting Issues
```bash
# See detailed linting errors
ruff check --output-format=text

# Auto-fix what can be fixed
ruff check --fix

# Check specific file
ruff check app/service/doi.py
```

### 12. Development Environment Setup

#### Initial Setup
```bash
# Clone repository
git clone <repository-url>
cd gatekeeper

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
make python-pip-install

# Start database
make docker-run-db

# Apply migrations
make db-upgrade

# Run application
make python-run
```

#### Daily Development
```bash
# Start work
git pull origin main
make docker-run-db

# During development
make python-run  # In one terminal
# Make changes and test

# Before committing
pytest
ruff check --fix
ruff format
git add .
git commit -m "feat: add new feature"
```

### 13. Monitoring & Debugging

#### Application Logs
```bash
# View application logs
docker logs <container_name> -f

# Check specific log levels
docker logs <container_name> | grep ERROR
docker logs <container_name> | grep WARNING
```

#### Database Monitoring
```bash
# Check database status
docker exec -it <db_container> psql -U <user> -d <database>

# Monitor slow queries
# Add to postgresql.conf: log_statement = 'all'
# Check logs for slow queries
```

#### Performance Monitoring
- **Response times**: Monitor API endpoint performance
- **Memory usage**: Check for memory leaks
- **Database connections**: Monitor connection pool usage
- **External service calls**: Track DOI service response times

### 14. Emergency Procedures

#### Hot Fixes
1. **Create hotfix branch**: `git checkout -b hotfix/critical-issue`
2. **Make minimal changes**: Fix only the critical issue
3. **Test thoroughly**: Run full test suite
4. **Deploy immediately**: Skip normal review process
5. **Document issue**: Create proper issue ticket
6. **Follow up**: Proper fix in next release

#### Rollback Procedures
1. **Identify issue**: Determine what went wrong
2. **Stop deployment**: Halt current deployment
3. **Rollback code**: Revert to last known good version
4. **Rollback database**: If schema changes were made
5. **Verify functionality**: Ensure system is working
6. **Investigate root cause**: Understand what happened

This development workflow ensures code quality, maintains system stability, and provides a clear path for feature development and validation.
