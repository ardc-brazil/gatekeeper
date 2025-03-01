INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'admin', '/*', '.*', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_read', '/api/v1/users', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_write', '/api/v1/users', '(GET|POST|PUT)', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_write', '/api/v1/users/.*/enable', 'PUT', 'deny', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_write', '/api/v1/users/.*/roles', '(PUT|DELETE)', 'deny', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_admin', '/api/v1/users', '(POST|PUT|GET|DELETE)', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'users_admin', '/api/v1/users/.*/roles', '(PUT|DELETE)', 'deny', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_read', '/api/v1/datasets', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_write', '/api/v1/datasets', '(GET|POST|PUT)', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_write', '/api/v1/tus', 'POST', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_admin', '/api/v1/datasets', '(GET|POST|PUT|DELETE)', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_write', '/api/v1/datasets/.*/enable', 'PUT', 'deny', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'tenancies_read', '/api/v1/tenancies', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'tenancies_write', '/api/v1/tenancies', '(GET|POST|PUT)', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'tenancies_write', '/api/v1/tenancies/.*/enable', 'PUT', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'tenancies_admin', '/api/v1/tenancies', '(POST|PUT|GET|DELETE)', 'allow', NULL, NULL);
