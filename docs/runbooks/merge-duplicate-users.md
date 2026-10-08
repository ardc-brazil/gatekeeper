# Merging two accounts of the same person

A person can end up with two rows in `users`: one created by signing in with
ORCID, another created with an email address. Everything they own is then split
between two ids. This moves it all onto the account that stays and deletes the
other, in one transaction.

Decide first which account stays. The ORCID account is the usual choice, because
the ORCID is the identity that the `user_provider` row links to. The account that
goes loses its email, password and verification: the person sets and verifies the
email again on the account that stays.

## 1. Look before touching

```sql
SELECT id, name, email, email_verified_at, password_hash IS NOT NULL AS has_pw,
       is_enabled, created_at
FROM users WHERE id IN ('<keep>', '<drop>');

SELECT * FROM user_provider   WHERE user_id IN ('<keep>', '<drop>');
SELECT * FROM users_tenancies WHERE user_id IN ('<keep>', '<drop>');
SELECT * FROM casbin_rule     WHERE v0      IN ('<keep>', '<drop>');
SELECT count(*) FROM datasets WHERE owner_id = '<drop>';
```

Take a dump first (`docs/runbooks/database-backup.md`).

## 2. Check that the list below is still complete

A table added after this was written will block the final `DELETE`. List every
foreign key that points at `users`:

```sql
SELECT conrelid::regclass AS table_name, a.attname AS column_name
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
WHERE c.contype = 'f' AND c.confrelid = 'users'::regclass
ORDER BY 1, 2;
```

Anything not handled in step 3 needs its own `UPDATE ... SET col = :'keep' WHERE
col = :'drop'` before the `DELETE FROM users`. If you forget one, the `DELETE`
fails and names the table; nothing is lost because the transaction aborts.

## 3. Merge

Save as `merge.sql` and run with the two ids as variables:

```bash
psql "$DATABASE_URL" -v keep=252e740f-... -v drop=64cd8613-... -f merge.sql
```

```sql
BEGIN;

INSERT INTO user_provider (user_id, provider_id)
  SELECT :'keep'::uuid, provider_id FROM user_provider
  WHERE user_id = :'drop'::uuid ON CONFLICT DO NOTHING;
DELETE FROM user_provider WHERE user_id = :'drop'::uuid;

INSERT INTO users_tenancies (user_id, tenancy)
  SELECT :'keep'::uuid, tenancy FROM users_tenancies
  WHERE user_id = :'drop'::uuid ON CONFLICT DO NOTHING;
DELETE FROM users_tenancies WHERE user_id = :'drop'::uuid;

INSERT INTO dataset_permissions (dataset_id, user_id, level, granted_by, created_at)
  SELECT dataset_id, :'keep'::uuid, level, granted_by, created_at
  FROM dataset_permissions WHERE user_id = :'drop'::uuid ON CONFLICT DO NOTHING;
DELETE FROM dataset_permissions WHERE user_id = :'drop'::uuid;

UPDATE casbin_rule c SET v0 = :'keep'
WHERE c.ptype = 'g' AND c.v0 = :'drop'
  AND NOT EXISTS (SELECT 1 FROM casbin_rule d
                  WHERE d.ptype = 'g' AND d.v0 = :'keep' AND d.v1 = c.v1);
DELETE FROM casbin_rule WHERE v0 = :'drop';

UPDATE datasets                SET owner_id     = :'keep'::uuid WHERE owner_id     = :'drop'::uuid;
UPDATE dataset_permissions     SET granted_by   = :'keep'::uuid WHERE granted_by   = :'drop'::uuid;
UPDATE dataset_access_events   SET changed_by   = :'keep'::uuid WHERE changed_by   = :'drop'::uuid;
UPDATE email_messages          SET triggered_by = :'keep'::uuid WHERE triggered_by = :'drop'::uuid;
UPDATE dataset_invitations     SET invited_by   = :'keep'::uuid WHERE invited_by   = :'drop'::uuid;
UPDATE dataset_invitations     SET accepted_by  = :'keep'::uuid WHERE accepted_by  = :'drop'::uuid;
UPDATE dataset_anonymous_links SET created_by   = :'keep'::uuid WHERE created_by   = :'drop'::uuid;
UPDATE dataset_versions        SET created_by   = :'keep'::uuid WHERE created_by   = :'drop'::uuid;
UPDATE data_files              SET created_by   = :'keep'::uuid WHERE created_by   = :'drop'::uuid;
UPDATE dois                    SET created_by   = :'keep'::uuid WHERE created_by   = :'drop'::uuid;

DELETE FROM auth_challenges WHERE user_id = :'drop'::uuid;
DELETE FROM users WHERE id = :'drop'::uuid;

SELECT id, name, email, email_verified_at FROM users
WHERE id IN (:'keep'::uuid, :'drop'::uuid);
```

The script ends without `COMMIT`. The last query must return one row, the account
that stays. Then type `COMMIT;`, or `ROLLBACK;` if anything looks wrong.

## What to know

- Where both accounts had a permission on the same dataset, the one that stays
  wins (`ON CONFLICT DO NOTHING`), even if the other had a higher level.
- The email of the account that goes is deleted with it. If the person should
  keep logging in by email, they verify it again on the account that stays.
- Casbin reloads its policy every 5 seconds, so roles move over within that time.
- Run the script once on a restored dump before running it in production if
  there is any doubt about the table list.
