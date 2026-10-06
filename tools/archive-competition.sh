#!/usr/bin/env bash
# Run on the provisioned VPS from the repository root after disabling submissions.
set -euo pipefail
umask 077
version="closeout-$(date -u +%Y%m%dT%H%M%SZ)"
archive="private/archives/$version"
mkdir -p "$archive"
chmod 700 "$archive"
# A single consistent PostgreSQL snapshot, including private simulation and audit.
sudo -n docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$archive/database.dump"
sudo -n docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --schema-only' > "$archive/schema.sql"
sudo -n docker compose --profile ops run --rm -T --no-deps scenario-admin python -m app.archive_report > "$archive/results.json"
for table in observations forecast_cycles cycle_targets submissions predictions cycle_entries; do
  sudo -n docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"' sh "COPY (SELECT * FROM competition.$table) TO STDOUT WITH CSV HEADER" > "$archive/$table.csv"
done
# Preserve source and generator bundles without copying credentials or this archive.
git bundle create "$archive/source.bundle" HEAD
tar --exclude='./archives' -czf "$archive/private-bundles.tar.gz" -C private .
tar -czf "$archive/starter.tar.gz" data/starter
python3 - "$archive" "$(git rev-parse HEAD)" <<'PY'
import csv, hashlib, json, pathlib, sys
from datetime import datetime, timezone
root=pathlib.Path(sys.argv[1])
report=json.loads((root/'results.json').read_text())
phase=report['final_phase']
assert phase['window']['clock_state']=='completed'
assert phase['cycles']['open']==0 and phase['cycles']['awaiting_resolution']==0
files={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()} for p in sorted(root.iterdir()) if p.is_file()}
rows={p.name:sum(1 for _ in csv.reader(p.open()))-1 for p in root.glob('*.csv')}
manifest={'version':root.name,'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_commit':sys.argv[2],'submissions_enabled':False,'closure_at':phase['window']['ends_at_wall'],'final_phase_cycles':phase['cycles'],'academic_cutoff_cycles':report['academic_cutoff']['resolved_cycles'],'csv_rows':rows,'files':files,'privacy':'Private instructor archive. Never publish in GitHub or student downloads. Restore into an isolated database using provisioned roles and secrets.'}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(root/'SHA256SUMS').write_text(''.join(f"{v['sha256']}  {k}\n" for k,v in files.items())+f"{hashlib.file_digest((root/'manifest.json').open('rb'),'sha256').hexdigest()}  manifest.json\n")
print(json.dumps({'version':root.name,'csv_rows':rows,'resolved_phase_cycles':phase['cycles']['resolved'],'academic_cutoff_cycles':report['academic_cutoff']['resolved_cycles']}))
PY
printf '%s\n' "$archive"
