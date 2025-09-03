-- Integration test seed data
-- This applies all resource seed data and creates test client/user for integration tests

-- Apply all tenancy seed data (from tenancy_seed.sql)
INSERT INTO tenancies (name, is_enabled) VALUES ('datamap/production/amazon-face', TRUE);
INSERT INTO tenancies (name, is_enabled) VALUES ('datamap/staging/amazon-face', TRUE);
INSERT INTO tenancies (name, is_enabled) VALUES ('datamap/production/data-amazon', TRUE);
INSERT INTO tenancies (name, is_enabled) VALUES ('datamap/staging/data-amazon', TRUE);

-- Apply all Casbin policies (from casbin_seed_policies.sql)
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'admin', '/*', '.*', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_read', '/api/v1/users', 'GET', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_write', '/api/v1/users', '(GET|POST|PUT)', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_write', '/api/v1/users/.*/enable', 'PUT', 'deny', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_write', '/api/v1/users/.*/roles', '(PUT|DELETE)', 'deny', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_admin', '/api/v1/users', '(POST|PUT|GET|DELETE)', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_admin', '/api/v1/users/.*/roles', '(PUT|DELETE)', 'deny', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_read', '/api/v1/datasets', 'GET', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_write', '/api/v1/datasets', '(GET|POST|PUT)', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_write', '/api/v1/tus', 'POST', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_admin', '/api/v1/datasets', '(GET|POST|PUT|DELETE)', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_write', '/api/v1/datasets/.*/enable', 'PUT', 'deny', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'tenancies_read', '/api/v1/tenancies', 'GET', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'tenancies_write', '/api/v1/tenancies', '(GET|POST|PUT)', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'tenancies_write', '/api/v1/tenancies/.*/enable', 'PUT', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'tenancies_admin', '/api/v1/tenancies', '(POST|PUT|GET|DELETE)', 'allow', NULL, NULL);

-- Apply RBAC data (from rbac_data.sql) 
INSERT INTO casbin_rule (ptype, v0, v1, v2) VALUES ('g', 'admin', '/api/v1/*', '(GET|POST|PUT|DELETE)');

-- Insert test client
INSERT INTO clients (key, secret, name, is_enabled, created_at, updated_at) 
VALUES (
    '5060b1a2-9aaf-48db-871a-0839007fd478'::uuid,
    '$2b$12$TdLefTKhOuWHbm7D4ZN35eoFg7U9zmQOTKTNTfVbn.TLAFTPsCJ7W', -- hashed 'g*aZkbWom3deiAX-vtoT'
    'Integration Test Client',
    true,
    now(),
    now()
) ON CONFLICT (key) DO UPDATE SET
    secret = EXCLUDED.secret,
    name = EXCLUDED.name,
    is_enabled = EXCLUDED.is_enabled,
    updated_at = now();

-- Insert test user
INSERT INTO users (id, name, email, is_enabled, created_at, updated_at)
VALUES (
    'cbb0a683-630f-4b86-8b45-91b90a6fce1c'::uuid,
    'Integration Test User',
    'integration-test@datamap.example.com',
    true,
    now(),
    now()
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    is_enabled = EXCLUDED.is_enabled,
    updated_at = now();

-- Connect user to tenancy
INSERT INTO users_tenancies (user_id, tenancy)
VALUES (
    'cbb0a683-630f-4b86-8b45-91b90a6fce1c'::uuid,
    'datamap/production/data-amazon'
) ON CONFLICT (user_id, tenancy) DO NOTHING;

-- Assign datasets_write role to the test user  
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('g', 'cbb0a683-630f-4b86-8b45-91b90a6fce1c', 'datasets_write', NULL, NULL, NULL, NULL);