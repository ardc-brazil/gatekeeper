# Database backups

Until 2026-09-26 there were none. The two files in `~/db-backups` are dumps
taken by hand around migrations in April and October 2024.

The database is 138 MB and dumps to 25 MB in under two seconds, so the schedule
is not a trade-off against anything: it is daily because there is no reason for
it to be less.

## What runs

A systemd timer at 03:20, `Persistent=true` so a machine that was off at that
hour takes the backup on the next boot instead of skipping the day. It runs
`/home/datamap/bin/backup_database.py`, which the deploy installs: the script
dumps through the database container, verifies what it wrote, and prunes — 30
daily copies and 12 first-of-month ones.

The unit deliberately does not run the copy in the runner's workspace. That
directory belongs to CI and can be cleaned, and a backup that stops running
because of a checkout is worse than no backup, because it still looks installed.
The deploy also runs the installed script with `--help`, so an import it cannot
satisfy fails during the deploy rather than at 03:20 with nobody watching.

Backups land on the NAS, at `/home/datamap/storage/backups/postgres`. The
Postgres data directory is a bind mount on the host's **local** disk, so the NAS
is different physical storage from what it protects — which is the point. It is
one place, though: this does not survive losing the NAS.

## Installing it

The unit files are versioned; installing them is manual, because it needs root.

```bash
sudo cp infrastructure/backup/datamap-pg-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now datamap-pg-backup.timer
systemctl list-timers datamap-pg-backup.timer
```

Run it once by hand before trusting the schedule:

```bash
sudo systemctl start datamap-pg-backup.service
journalctl -u datamap-pg-backup.service -n 20 --no-pager
```

## The restore is the only thing that proves a backup

A dump nobody has restored is a hypothesis. Restore into a scratch database and
compare counts against production:

```bash
DUMP=$(ls -t /home/datamap/storage/backups/postgres/*.dump | head -1)
docker exec datamap_gatekeeper_db createdb -U gk_admin restore_probe
docker exec -i datamap_gatekeeper_db pg_restore -U gk_admin -d restore_probe --no-owner < "$DUMP"

for t in datasets dataset_versions users clients dois tenancies casbin_rule; do
  a=$(docker exec datamap_gatekeeper_db psql -U gk_admin -d gatekeeper_db -tAc "select count(*) from $t")
  b=$(docker exec datamap_gatekeeper_db psql -U gk_admin -d restore_probe  -tAc "select count(*) from $t")
  printf "%-20s %8s %8s %s\n" "$t" "$a" "$b" "$([ "$a" = "$b" ] && echo ok || echo DIFFERENT)"
done

docker exec datamap_gatekeeper_db dropdb -U gk_admin restore_probe
```

Keep `-d` before `-c`: `psql -tAc "query" -d db` hands `-d` to `-c` as the
query and reports nothing useful, which is how the first run of this check
produced seven spurious mismatches.

Verified on 2026-09-26: 450 datasets, 515 versions, 101 users, 10 clients,
185 DOIs, 12 tenancies, 232 Casbin rules, identical on both sides.

## Restoring for real

Into the live database, after establishing that you mean to:

```bash
docker compose -f docker-compose-infrastructure.yaml stop gatekeeper gatekeeper_b
docker exec -i datamap_gatekeeper_db pg_restore -U gk_admin -d gatekeeper_db \
  --clean --if-exists --no-owner < "$DUMP"
docker compose -f docker-compose-infrastructure.yaml start gatekeeper gatekeeper_b
```

Stop the application first. A restore with `--clean` drops and recreates every
object, and an instance holding connections through it produces a partial
restore rather than an error.

## Why it refuses to run sometimes

`/home/datamap/storage` is an autofs NFS mount. When the server is unreachable
the directory still exists and is empty, so a backup would land on the local
disk believing it reached the NAS — and the copy meant to survive that disk
would be on it. The script requires a `.datamap-nas` marker file, which exists
only on the NAS, and exits 2 without writing if it is missing.

That check is worth more than it looks: it is the difference between a failed
backup, which is visible, and a backup in the wrong place, which is not.
