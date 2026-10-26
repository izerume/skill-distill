# Classify before detailed selection

Start a library-wide request with the tasks users want done. Read only names and descriptions for this first pass. Group related capabilities broadly enough to reveal potential shared cores, workflow stages and platform branches. Choose categories that fit this library; a previous library's category names or final entrypoint count are not constraints.

Give each skill one primary task category. Add related categories for cross-domain capabilities and free-form tags for platform, output or stage. Roles describe how the skill helps:

- `workflow`: ordered task execution or a decision loop.
- `guidance`: methods, standards or decision criteria.
- `tool`: operating a particular tool, service or environment.
- `reference`: knowledge consulted as needed.
- `router`: dispatching to other capabilities.

A skill can have multiple roles. Motion construction, audit, review and terminology may belong to one task family while keeping their different roles. Classification is a coarse judgment from metadata; defer ambiguous skills instead of reading their full packages just to complete the first pass.

## Metadata inventory and assignments

Run from this skill directory, keeping outputs outside source packages:

```text
python -X utf8 -B scripts/skill_distill.py classify --root /path/to/skills --out inventory.json
```

Repeat `--root` for multiple libraries or named packages. The scanner stops at each installed package boundary and reads only `SKILL.md` frontmatter. It does not inspect bodies, resources, invocation policy or package hashes. Diagnostics retain unreadable/skipped paths. Inventory IDs distinguish same-name packages.

The calling agent uses this inventory to write assignments. The Python CLI validates and groups them; it does not invoke a model. Reuse the inventory report and add `categories` and `assignments`, or supply an object containing these two fields:

```json
{
  "categories": [
    {"id": "motion", "name": "Animation and motion"},
    {"id": "frontend", "name": "Frontend design"}
  ],
  "assignments": [
    {
      "skill": "/absolute/path/to/animate",
      "category": "motion",
      "related_categories": ["frontend"],
      "roles": ["workflow"],
      "tags": ["web", "build"],
      "reason": "Its description offers implementation of web animations."
    },
    {
      "skill": "/absolute/path/to/review-animations",
      "category": "motion",
      "roles": ["guidance"],
      "tags": ["review"],
      "reason": "Its description offers review of existing motion."
    }
  ]
}
```

Use inventory IDs or absolute paths, not display names. `category`, nonempty `roles` and `reason` are required; `related_categories` and `tags` are optional. No source quotes, similarity threshold or economic forecast is needed at this stage. Partial coverage remains explicit in `coverage.unclassified`; it is not a keep decision.

```text
python -X utf8 -B scripts/skill_distill.py classify --root /path/to/skills --assignments assignments.json --out classification.json
```

`candidate_groups` preserves every category with at least two primary/related members as a complete group. These groups have status `classification_only`; they are not limited by pairwise retrieval's `max_candidates`, and do not assert overlap, merge eligibility or lossless behavior. Singleton categories remain visible. A metadata fingerprint checks that a reused report still describes the supplied roots; it is not a source snapshot or an update/version-control system.

## Shortlist, then expand one scope

Show the category map and a few useful candidate families. Prefer families with the same user goal, a shared output across stages, or a common method across platforms. The agent can choose the next useful scope from the user's goal without requesting routine approval. A quick-look request ends with this shortlist. An authorized continuation proceeds to detailed source selection for the chosen categories:

```text
python -X utf8 -B scripts/skill_distill.py select --root /path/to/skills --classification classification.json --category motion --out motion-inventory.json
```

With a classification report, `select` requires at least one category; repeat `--category` for related groups. It reads full packages only in that scope. Other skills remain in `classification.deferred`, with unclassified skills separately visible in the retained coverage. They are not assessed keep outcomes. Review the complete selected family alongside lexical suggestions, then follow [target selection](target-selection.md) to write source-backed assessments and run the same scoped command with `--assessments`.

Class membership is a reason to inspect sources together. Actual construction chooses a shared core with mode-specific branches, shared references, compression or independent packages based on those sources. Workflow consolidation must preserve independent routes, dependencies, outputs and authorization boundaries. Quality and cost claims come from later execution evidence.
