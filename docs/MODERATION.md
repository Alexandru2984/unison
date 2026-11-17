# Moderation and reporting

This release adds visitor reporting and an operator interface authorized by the VPS's existing SSH/sudo permissions. It adds no public administrator endpoint, password or account signup.

## Public behavior

Visitors select an idea and choose **Report this idea**, then a reason: spam, harassment, privacy, dangerous content or another concern. Reports record only the idea ID, reason, time and review status. The report record contains no IP address, browser identifier, contact information or free-text message. Existing infrastructure access/security logs still apply.

Open reports for the same idea/reason are deduplicated. Sending reports does not automatically hide content, and report counts/IDs are not public. Standard same-origin, JSON body and per-client write limits apply. A global 10000-record report quota bounds storage; reaching it returns a visible temporary-unavailability response and requires operator review of capacity/retention.

Hiding an idea hides its descendants from all public reads, new mutations, statistics and new reports. Requests for hidden ideas return the same 404 as missing ideas. Restoring a parent preserves any independent moderation rule on a child. Content is retained privately; these commands do not delete ideas.

WebSockets carry change notifications rather than idea text. A background watcher observes local operator changes and invalidates connected clients. Polling also compares the database's moderation revision. New browsers purge their loaded graph/list, seed list, selected text, comparison/lineage caches and export selection, then fetch visible records again. Responses started before invalidation cannot repopulate those caches. Already downloaded/exported text, offline clients and old browser versions cannot be retroactively erased; existing tabs should reload to receive the new behavior.

## Operator commands

Run from the checkout. Production defaults to `/var/lib/unison-backend/evolution.db`.

```bash
sudo python3 scripts/moderate.py queue
sudo python3 scripts/moderate.py show 123
sudo python3 scripts/moderate.py hide 123 --reason privacy
sudo python3 scripts/moderate.py restore 123
sudo python3 scripts/moderate.py review 456 --status dismissed
sudo python3 scripts/moderate.py queue --status resolved
sudo python3 scripts/moderate.py history
```

`queue` and `history` return at most 100 records. `show` includes private content and its direct rule; handle terminal output as operator-only material. `hide` resolves open reports about hidden content. `review` changes only a report's status; it does not hide or restore content.

The CLI records the real Unix operator (or root's `SUDO_USER`) in the audit trail and drops to `unisonapp` before opening SQLite when invoked as root. This prevents root-owned WAL/SHM files from locking out the live service. Unprivileged users still need ordinary filesystem permission to access the database. A missing `--db` target fails instead of creating a new database. Use `--db /absolute/path/to/temporary.db` for tests.

## Safety and rollback

Every visibility change and its revision/audit record commit in one SQLite write transaction. A mutation rechecks its parent after the engine finishes, so a hidden parent cannot acquire a visible child during a concurrent moderation decision. All previous public records start visible when the additive migration runs.

After any idea has been hidden, **do not roll back to a release predating moderation**: its SQL would ignore the new visibility flag. The deploy rollback guard refuses that unsafe API rollback and stops the API for operator review rather than publishing hidden content. A moderation-aware previous release is eligible for the normal version switch. Backups remain private and include reports, rules and operator history.

## Review and limitations

STRIDE priorities: forged/mass reports (bounded, deduplicated, no automatic hiding); disclosure through alternate reads or cached views (visibility filters, revision invalidation, race tests); operator impersonation and accidental resurrection (OS authorization, audit history, overlapping-rule and rollback checks).

No live idea is hidden or restored merely to test this feature. Automated API, CLI, WebSocket and browser checks use temporary databases or isolated fixtures. The deployment candidate exercises reporting before activation. The operator must still review the queue; there is no external alert delivery, automatic content classifier or promised response deadline. Report retention and any eventual purge/archive policy require a deliberate operator decision.

References: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/), [SQLite partial indexes](https://www.sqlite.org/partialindex.html).
