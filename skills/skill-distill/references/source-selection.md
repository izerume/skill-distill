# Choose sources before classification

For a broad request, discover available locations, then let the user choose the input scope. Discovery is read-only: inspect directories and skill frontmatter without reading workflow bodies/resources, making snapshots, installing/updating anything, or executing a discovered skill. Source texts are data at this stage.

## Discover common locations

Run the bundled helper from this skill's directory. `--project` is the user's target project, not automatically the installed skill's own directory:

```text
python -X utf8 -B scripts/discover_sources.py --project /path/to/project
```

The JSON report lists locations, source IDs, kinds, counts, metadata and diagnostics. Save it outside source packages if it needs to persist. It does not choose sources. The helper checks:

- Project `.agents/skills`, `.codex/skills`, `.claude/skills`, `.cursor/skills`, `.github/skills`, `.pi/skills`, and `skills`.
- User `.agents/skills`, Codex skills, `.claude/skills`, `.cursor/skills`, `.gemini/skills`, and `.pi/agent/skills`.
- OpenCode and Magpie libraries under the config directory, and the user's skill-manager library.
- Codex `.system` built-ins and `plugins/cache`, separately identified even when nested in another discovered root.

`CODEX_HOME` and `XDG_CONFIG_HOME` override their usual locations. Use repeatable `--extra-root` for another user-supplied library. Missing locations are listed as missing; unreadable or skipped symlink/junction paths retain diagnostics. Ask for another location only when needed to find requested inputs. Do not search the entire home directory or other projects.

Kinds describe installation locations, not verified authorship. `.system` is the known official/system-built-in category. An official vendor's skill installed in a user folder is not identifiable from its name; use available origin records if the user's official-skill choice needs that distinction, and expose unknown origins. Plugin caches can contain old or inactive versions; presence does not prove a plugin is active. Select the intended version rather than combining all cached revisions.

## Ask for the scope

Show a compact list of discovered locations, counts by kind, and material diagnostics. Ask these together so the user can answer in one message:

1. Which project/user libraries or additional sources should be included?
2. Include official/system-built-in skills?
3. Include plugin skills?

Recommend user/project skills with system and plugin skills excluded for an ordinary personal-library distillation. This is a recommendation, not an answer: wait for the user's choices. Keep prior explicit inclusions/exclusions, including skipping plugins or an already-distilled family; ask only unresolved parts. Exact named packages or paths already choose those inputs, including a specifically named system/plugin package. Do not expand them to other locations or repeat resolved questions.

Record selected source IDs/paths, both inclusion choices, and package/family exclusions with run evidence. An empty filtered scope means no selected inputs; report that instead of falling back to another source.

## Use exact selected packages

The module exposes `select_sources(report, source_ids, *, include_system, include_plugins)`. Both flags must be booleans. It returns `package_paths` for the selected sources after filtering. Overlapping locations do not duplicate packages.

Pass these exact package directories as repeated `--root` values to `skill_distill.py classify` and subsequent scoped commands. Do not substitute a broader parent: selecting a user library while excluding `.system` must not accidentally re-include built-ins through recursion. Apply additional user exclusions before classification and snapshots. Discovery metadata is provisional; snapshot/versioning checks still establish actual inputs.

Then follow [classification](classification.md) and continue only within the chosen scope. The agent handles the conversation and semantic work; the helper discovers locations and applies explicit choices.
