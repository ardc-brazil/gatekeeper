-- Admin role permissions

INSERT INTO casbin_rule (ptype, v0, v1, v2) VALUES ('g', 'admin', '/api/v1/*', '(GET|POST|PUT|DELETE)');
