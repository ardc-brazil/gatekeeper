--
-- PostgreSQL database dump
--

-- Dumped from database version 15.3 (Debian 15.3-1.pgdg120+1)
-- Dumped by pg_dump version 15.3

-- Started on 2023-08-12 22:33:17 UTC

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 3362 (class 0 OID 16777)
-- Dependencies: 222
-- Data for Name: casbin_rule; Type: TABLE DATA; Schema: public; Owner: gk_admin
--

INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'admin', '/*', '.*', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_read', '/api/v1/datasets/:id', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_write', '/api/v1/datasets/:id', '(POST|PUT)', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_admin', '/api/v1/datasets/:id/(disable|enable)', '(PUT|DELETE)', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_filters', '/api/v1/datasets/filters', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('p', 'datasets_search', '/api/v1/datasets', 'GET', 'allow', NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('g', 'datasets_search', 'datasets_read', NULL, NULL, NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('g', 'datasets_search', 'datasets_filters', NULL, NULL, NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('g', 'datasets_write', 'datasets_search', NULL, NULL, NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('g', 'datasets_admin', 'datasets_write', NULL, NULL, NULL, NULL);
INSERT INTO public.casbin_rule (ptype, v0, v1, v2, v3, v4, v5) VALUES ('g', 'users_write', 'users_search', NULL, NULL, NULL, NULL);

-- Completed on 2023-08-12 22:33:18 UTC

--
-- PostgreSQL database dump complete
--

