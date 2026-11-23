# NAS deployment and recovery

This template is prepared only. Building or starting it has not been performed.
Starting `--watch` makes real provider requests and may write to the team API;
obtain the operator's approval before starting it.

1. Stop the old worker. Never run two containers or two hosts against this state.
2. Back up and copy the **entire existing data directory**, including
   `domeggook_open/request_ledger.json`, `domeggook_ops/request_ledger.json`,
   `domeggook_ops/discovery_checkpoint.json`, and the backend delivery outbox.
   Do not initialize empty state to work around a hold or budget. Bind `/state`
   to that directory and make it writable by UID/GID 10001. Use a local NAS
   filesystem with reliable locks and atomic rename; do not share it over SMB/NFS.
3. Copy `.env.example` to `.env` here (never commit it), supply credentials and
   absolute paths. Restrict its permissions and the state/profile directories.
   Tokens come from `DOMEGGOOK_API_KEY` and `KKULPICK_BACKEND_TOKEN`. There is no
   interactive login. Use the collector token issued by the team backend.
4. Reuse the approved backend profile, including `backend_enabled`,
   `backend_owner_approved`, `price_semantics_confirmed`, valid per-field
   storage/reuse grants, and `backend_delivery.mode=live_authorized`.
   Keep the existing outbox run ID. Do not change grants or prices to pass checks.
5. From this directory, after launch approval:
   `docker compose --env-file .env build` then
   `docker compose --env-file .env up -d`.
   Stop with `docker compose stop`. SIGTERM finishes the bounded current request,
   checkpoints it, and exits. A forced kill leaves a reservation for recovery.
6. Read-only inspection without product HTTP or token reads:
   `docker compose run --rm --no-deps domeggook python -m services.collector.domeggook_live --status`
   and the same command with `--verify`. Check provider/recovery holds and the
   backend outbox file's status counts; a running process alone is not health.

## Recovery behavior

Only `uncertain_request_no_auto_resend` and
`interrupted_request_outcome_unknown` are eligible for automatic recovery in
watch mode. Wait at least 7,200 seconds (or a longer configured cycle) from the
failure timestamp (reservation timestamp after a forced kill). Keep its original reservation/status and budget charge;
append a recovery receipt with no success claim. Resume the same queue cursor;
the next public GET is a fresh, budgeted attempt. Queue attempt caps still apply.
A failed `--once` exits safely; a later watch start can perform the recovery.

Auth/redirect/API-schema/circuit holds, or a successful listing response lost
before its ID checkpoint, remain held for review. Never erase a ledger, advance
a cursor manually, or clear these holds to force collection. Once task retries
are exhausted, inspect and resolve that task rather than resetting the state.

Completed collection cycles persist their next deadline, so a container restart
does not start another cycle early. No backlog of missed cycles is replayed.
Backend outbox retries continue during the 2-hour wait with exponential delay,
at most five attempts by default. Replays preserve the run ID, observation key
and exact body, including after a crash in `sending`. Authentication failures and
409 conflicts remain held. Exhausted entries remain for operator review.

The backend must enforce its existing observation-key uniqueness for a replay
after a committed POST whose response was lost. Client-only code cannot guarantee
exactly-once database writes. No server schema or team API files are changed.

The provider limits and policy values in the existing config are retained;
this change does not re-certify or increase those limits. Preserve state across
image upgrades and NAS restarts. Docker availability, Linux locking, image build,
and actual NAS operation need deployment-environment validation.
