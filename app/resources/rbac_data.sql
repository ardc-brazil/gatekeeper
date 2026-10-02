-- Admin role permissions

INSERT INTO casbin_rule (ptype, v0, v1, v2) VALUES ('g', 'admin', '/api/v1/*', '(GET|POST|PUT|DELETE)');

INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/datasets/?$', 'GET', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/datasets/[0-9a-f-]{36}(/.*)?$', '(GET|POST|PUT|DELETE)', 'allow', NULL, NULL);
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_shared', '/api/v1/tus', 'POST', 'allow', NULL, NULL);
