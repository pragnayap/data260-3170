#!/usr/bin/env bash
# HW10: start / stop / status of the HW8 Planner, Writer and Reviewer as background processes with tracing on.
#   code/hw10/agents.sh start [stub]   stub = instant canned plan/draft (plumbing tests only)
#   code/hw10/agents.sh stop | status
# Fresh consumer groups (s3170_hw10_*) read only new messages, so old HW8 traffic is never replayed.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
RUN="$ROOT/data/hw10/run"
mkdir -p "$RUN" "$ROOT/data/hw10/logs" "$ROOT/data/hw10/spans"

start_one() {  # name script group
  local name="$1" script="$2" group="$3"
  if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then echo "$name already running"; return; fi
  ( cd "$ROOT/code/hw08" && HW10_TRACE=1 GROUP="$group" RESET=latest STATE_DIR="$ROOT/data/hw10/state" \
      nohup "$PY" -u "$script" >"$ROOT/data/hw10/logs/$name.log" 2>&1 & echo $! >"$RUN/$name.pid" )
  echo "started $name (pid $(cat "$RUN/$name.pid"))"
}

case "${1:-status}" in
  start)
    # Refuse to start if ANY agent process is alive (stale ones share the consumer groups and silently steal messages).
    stale=$(pgrep -f "hw08/(planner|writer|reviewer).py|(planner|writer|reviewer).py" | wc -l | tr -d ' ')
    if [ "$stale" != "0" ]; then echo "REFUSING to start: $stale agent process(es) already running - run '$0 stop' first"; exit 1; fi
    if [ "${2:-}" = "stub" ]; then export PLANNER_MODE=stub WRITER_MODE=stub; fi
    start_one planner planner.py s3170_hw10_planner
    start_one writer writer.py s3170_hw10_writer
    start_one reviewer reviewer.py s3170_hw10_reviewer
    ;;
  stop)
    # The pid file holds the launcher; the venv python re-execs into a CHILD, so kill children too, then sweep by name.
    for n in planner writer reviewer; do
      if [ -f "$RUN/$n.pid" ]; then pkill -P "$(cat "$RUN/$n.pid")" 2>/dev/null; kill "$(cat "$RUN/$n.pid")" 2>/dev/null; echo "stopped $n"; rm -f "$RUN/$n.pid"; fi
    done
    pkill -f "(planner|writer|reviewer).py" 2>/dev/null; sleep 1
    left=$(pgrep -f "(planner|writer|reviewer).py" | wc -l | tr -d ' '); echo "agent processes left: $left"
    ;;
  status)
    for n in planner writer reviewer; do
      if [ -f "$RUN/$n.pid" ] && kill -0 "$(cat "$RUN/$n.pid")" 2>/dev/null; then echo "$n running (pid $(cat "$RUN/$n.pid"))"; else echo "$n stopped"; fi
    done
    echo "agent processes alive (should be 3 when running, 0 when stopped): $(pgrep -f "(planner|writer|reviewer).py" | wc -l | tr -d ' ')"
    ;;
esac
