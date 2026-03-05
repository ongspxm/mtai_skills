# No Dead Code By Default
## Intent
Keep the codebase lean and reduce long-term maintenance drag.

## Rule
- Remove obsolete paths as part of the change.
- Keep backward-compatibility shims only when explicitly required.

## Examples
- Good: delete deprecated helper after migrating call sites.
- Bad: keep unused fallback branches "just in case".
