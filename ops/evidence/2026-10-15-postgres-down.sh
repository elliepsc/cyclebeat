#!/usr/bin/env bash
# Incident reproduction: Postgres stopped under a healthy API. Compose project cyclebeat-it ONLY.
# Run from the repo root. Every command is echoed with a UTC timestamp, then its output.
set -u
export CYCLEBEAT_API_PORT=18000 CYCLEBEAT_WEB_PORT=14173
C="docker compose -p cyclebeat-it"
API="http://localhost:${CYCLEBEAT_API_PORT}"
BODY='{"source":{"type":"demo","value":""},"level":"intermediate","goal":"endurance","duration_min":45}'

step() { echo; echo "### $(date -u +%H:%M:%S.%3N) \$ $*"; "$@" 2>&1; echo "### exit=$?"; }
psql_q() { $C exec -T postgres psql -U cyclebeat -d cyclebeat -tA -c "$1"; }
gen() { curl -s -o /dev/stdout -w '\nHTTP %{http_code} in %{time_total}s\n' -X POST "$API/v1/sessions/generate" -H 'Content-Type: application/json' -d "$BODY" | tail -c 400; }
health() { curl -s -w '\nHTTP %{http_code}\n' "$API/health"; }

echo "## 0. Stack up (project cyclebeat-it, default profile)"
step $C up --build --wait --wait-timeout 300 -d
step $C ps

echo "## 1. Baseline"
step health
step gen
step psql_q "select count(*) as sessions, count(*) filter (where plan_json is null or n_segments is null) as incomplete from sessions"

echo "## 2. Incident: stop postgres"
step $C stop postgres
step sleep 6
step $C ps
step health
step gen
step gen
step $C logs --no-color --since 30s api

echo "## 3. Recovery: start postgres"
step $C start postgres
T0=$(date +%s.%N)
for i in $(seq 1 60); do
  s=$($C ps --format '{{.Service}} {{.Health}}' | awk '$1=="postgres"{print $2}')
  [ "$s" = "healthy" ] && break
  sleep 1
done
T1=$(date +%s.%N)
echo "### postgres healthy after $(echo "$T1 - $T0" | bc) s (poll every 1 s)"
step $C ps
echo "### first generate after recovery:"
step gen
step gen
step psql_q "select count(*) as sessions, count(*) filter (where plan_json is null or n_segments is null) as incomplete from sessions"
step psql_q "select session_id, n_segments, json_array_length((plan_json::json)->'segments') as segments_in_json, created_at from sessions order by created_at"

echo "## 4. Teardown"
step $C down -v
step $C ps -a
