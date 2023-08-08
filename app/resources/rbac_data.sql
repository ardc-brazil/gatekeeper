-- Admin role permissions

INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4) VALUES ('g', 'admin', '/api/v1/*', 'GET', '*', 'allow');
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4) VALUES ('g', 'admin', '/api/v1/*', 'POST', '*', 'allow');
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4) VALUES ('g', 'admin', '/api/v1/*', 'PUT', '*', 'allow');
INSERT INTO casbin_rule (ptype, v0, v1, v2, v3, v4) VALUES ('g', 'admin', '/api/v1/*', 'DELETE', '*', 'allow');
