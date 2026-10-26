# Maintain distilled versions

The agent follows this procedure; `scripts/versioning.py` supplies deterministic file operations. Use the user's project and target. Sources remain managed by the prerequisite `npx skills`; these helpers never install, fetch or update sources and never call a model. A request to inspect does not authorize an update. A request to update a distilled target authorizes its preparation, checks and clean-path switch without asking again for each file.

Commands below run from this skill directory. All output is JSON; errors return status 2. Python's `-B` keeps source packages free of import caches. The helper also suppresses its own import cache when invoked without `-B`.

## Check without changing anything

```text
python -X utf8 -B scripts/versioning.py --project /path/to/project inspect writing-workbench
```

This reads existing records and compares only actual local dependencies. It returns `unmanaged` without creating a directory when the target has no record. Managed output distinguishes source changes, local output edits, method changes, candidates and pending operations. `upstream: not_queried` means no upstream availability check was made; unchanged local bytes do not establish that the source is globally latest.

Do not use `npx skills check` as a read-only probe: in the reviewed `skills@1.7.4` it dispatches to the update flow. If the user separately requests upstream investigation, inspect the source read-only. Only an explicit source-update request authorizes invoking that prerequisite's update action.

## Adopt an existing artifact or record a first delivery

```text
python -X utf8 -B scripts/versioning.py --project /path/to/project register writing-workbench --active distilled/writing-workbench --source /installed/writing-fragments --source /installed/writing-shape --source /installed/writing-beats --baseline-run /path/to/original-run
```

Use the original `snapshot` run when available; its `sources.json` and fixed files are verified. Inputs map by original path. If the source moved, pass `--sources bindings.json` instead of `--source`, with a list such as:

```json
[
  {"path": "/installed/alpha", "snapshot_key": "A"},
  {"path": "/installed/beta", "snapshot_key": "B"}
]
```

Each historical input must map exactly once. Available npx project/global locks supply origin metadata for their canonical installation directories. Host symlink entrypoints resolve to the canonical source directory. A custom binding can supply `origin` with `source_type`, normalized `source`, and skill-directory `skill_path`; the name alone is not identity. A missing origin becomes a persistent local identity. Git source IDs exclude branch/ref, installation path and timestamps.

Historical identity and the current binding are separate. Imported snapshot records retain their own recorded `origin`; snapshots lacking that information use `origin: null`, `source_id: null` and `origin_provenance: unknown`. Their `binding_id` refers only to the selected current installation. Do not fill historical identity from today's npx lock. An independently verified original origin may be provided as `historical_origin` in a source mapping; it must not contradict origin metadata already in the snapshot.

`register` snapshots the existing output without rewriting it. With `--baseline-run`, comparison uses those historical input bytes, even when the installed sources have since advanced. Without it, source snapshots are labelled `observed_at_adoption`, not represented as proved generation inputs. Explain that distinction; the original method remains unknown unless its actual record is supplied.

If no sources survive, pass `--sources` a JSON file containing `[]`: the actual output is still archived and restorable, with `source_history: unknown`; rebuilding is blocked until verified inputs are supplied. A known but missing/unreadable source may also be retained with unknown snapshot content. If that bound source later becomes readable, its state is `unknown` until an explicitly requested rebuild captures real inputs. Never invent provenance to make adoption succeed.

Optional `--method method.json` accepts a method record captured at generation, with `package: {algorithm, value}`, `generation_settings` and `author_executor`; do not substitute today's method for an unknown old method. Optional `--evidence /path/to/evidence` preserves prior observed checks in the format below. An adopted artifact is not automatically marked tested. For a fresh delivery, keep the original source run, method fingerprint/settings and observed evidence so these can be attached during registration.

## Explicit update

1. Inspect the named target. Keep its source membership fixed unless the user also requests regrouping. Source identity changes require an explicit corrected binding, not matching by name. Resolve missing sources before rebuilding.
2. If there are pending operations, recover the recorded operation before starting another switch. Preserve local edits; show the actual changed files and ask how to carry them forward or whether to overwrite. Do not discard them as a routine update.
3. Prepare the update:

```text
python -X utf8 -B scripts/versioning.py --project /path/to/project prepare writing-workbench
```

The returned `run_id` and absolute `path` locate the work folder. `up_to_date` ends an ordinary update without model calls. `--regenerate` is for an expressly requested rebuild; `--method method-settings.json` records actual `generation_settings` and `author_executor`. The helper computes the method package fingerprint itself. Unknown old methods permit an initial rebuild rather than a false claim of equivalence.

If historical origin cannot be verified, `inspect` reports `source_history: partial` and the ordinary prepare route stops. Use `--accept-current-sources` only when the user has explicitly selected the configured current sources as rebuild inputs, including when that selection is already clear in the request; do not request the same authorization again. This preserves unknown old provenance and records the choice on the new release. It does not silently refresh a binding to an unexpected repository: frozen-input checks still enforce the configured current origin.

4. Read the returned work folder's `run/sources.json` and source snapshots. Distill only those frozen inputs using [contracts](contracts.md) and the existing build procedure. Write a candidate directory and a separate evidence directory inside this work folder. The candidate frontmatter must match the final active directory's name.
5. Run structure checks and a few representative cases, normally 3–5, covering the changed routes and one important boundary. Follow [quick smoke checks](evaluation.md#quick-smoke-checks); stop when the requested scope passes. Fix concrete failures and replay affected cases. No blanket full benchmark is required for an ordinary update.
6. Fingerprint the final candidate and write observed evidence, then seal it:

```text
python -X utf8 -B scripts/versioning.py --project /path/to/project fingerprint --path /work/candidate
python -X utf8 -B scripts/versioning.py --project /path/to/project seal writing-workbench run-RETURNED_ID --candidate /work/candidate --evidence /work/evidence
```

`seal` validates structure, source snapshots, candidate bytes and evidence. It saves `r000002` (or the next unused number) without switching the active directory. Failures retain their work record and leave the current package intact.

7. Select the returned release:

```text
python -X utf8 -B scripts/versioning.py --project /path/to/project promote writing-workbench r000002
```

Promotion checks the captured base revision, current directory, saved package/evidence, method and current source contents again. Another session's new selection, local edits or sources advancing during staging stop the switch. `--expected-revision N` additionally binds an explicit inspected revision and never overrides the captured base revision. If checks pass, the helper saves an operation record, backs up the current directory, installs the complete new package, updates the state and removes only the redundant temporary backup. Historical releases remain.

## Observed evidence

The evidence directory contains `report.json` and the actual outputs it refers to. Populate the digest from the fingerprint result and checks from actual observations; the example is a format, not executed evidence:

```json
{
  "schema_version": 1,
  "scope": "smoke",
  "artifact": {
    "algorithm": "snapshot-manifest-sha256-v1",
    "value": "ACTUAL_CANDIDATE_DIGEST"
  },
  "executor": {"model": "ACTUAL_MODEL", "options": {}},
  "outputs": ["case-1/reply.md"],
  "checks": [
    {"id": "case-1-preserve-edits", "passed": true, "evidence": "Observed existing file prefix was retained."}
  ]
}
```

Every output path is relative to the evidence directory and must exist. Every check needs an ID, actual verdict and explanation; failed checks block sealing. The full evidence file manifest is saved and verified again before switching. File verification does not grade semantic correctness: the agent owns that judgment and reports the actual case scope, executor settings and grading dependence.

For a strictly metadata-only adjustment after a smoke run, keep the tested package inside the evidence directory, record its `tested_artifact: {algorithm, value}`, and add `post_test_adjustment` with `kind: metadata_only`, relative `tested_package`, and observed compatibility `checks` (`passed` plus `evidence`). The final `artifact` still names the actual final bytes. The helper requires every auxiliary file and the workflow text after frontmatter to be unchanged; other changes require replaying affected cases. Host selection/permission semantics still need the agent's compatibility check, not merely a string comparison.

## Restore and interrupted operations

```text
python -X utf8 -B scripts/versioning.py --project /path/to/project rollback writing-workbench r000001
python -X utf8 -B scripts/versioning.py --project /path/to/project recover writing-workbench
```

Rollback uses the saved package even if the live sources disappeared. It does not regenerate or fetch anything. Version numbering continues above the historical maximum after a rollback.

Windows directory switching and state-file updates are separate operations. If a process exits between them, `inspect` reports the pending operation without fixing it. When resuming the authorized update or when the user requests recovery, `recover` restores a complete old backup if the active directory is missing, or completes the state if the verified new package is already installed. It preserves unrecognized content. The OS releases the short write lock if a process dies; recovery does not need to delete a guessed stale lock file. Use `--operation op-ID` if selecting a particular recorded operation.

## Records and scope

State lives at `.skill-distill/targets/<target>/state.json`; sealed versions contain `release.json`, `package/`, `run/sources.json`, `run/sources/` and optional `evidence/`. The active path stays at the user's project-local location. Full content fingerprints share the snapshot enumerator, including runtime resources; only `.git`, `__pycache__` and `.pyc` follow the existing snapshot exclusions.

The helper manages one active directory per target. It preserves old releases and does not synchronize copies in other agent/global installations, poll upstreams, schedule work, or clear history. Check and update are distinct routes throughout.
