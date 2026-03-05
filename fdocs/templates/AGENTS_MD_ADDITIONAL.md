## Feature Docs (FD) Management
Features are tracked in `docs/fdocs/`. Each FD has a dedicated file (`fdXXX_title.md`) and `docs/fdocs/_INDEX.md` is generated from FD file frontmatter.

### FD Lifecycle
- `closed`: `closed` date is set
- `planned`: `planned` date is set and `closed` is empty
- `open`: `active=true` and `planned`/`closed` are empty
- `backlog`: default when none of the above apply

### fdocs Commands
- `fdocs init`: initialize `docs/fdocs/` scaffolding and seed templates
- `fdocs new`: create a new FD from `_TEMPLATE.md`
- `fdocs status`: regenerate index and show active docs
- `fdocs status --grooming`: move closed docs into `docs/fdocs/archive/`
- `fdocs close`: close and archive a specific FD
- `fdocs explore`: print fdocs status plus recent repo activity

### Conventions
- FD files: `docs/fdocs/fdXXX_title.md` (`XXX` is zero-padded)
- Archive: `docs/fdocs/archive/`
- Source of truth: FD files (index is derived output)
- Date format: `YYYY-MM-DD` for `planned` and `closed`
- Keep project-wide coding rules in `docs/dev_guide/*.md`

### Dev Guide
Keep long-lived engineering rules in `docs/dev_guide/` and keep `AGENTS.md` concise.

#### Conventions
- Source of truth: `docs/dev_guide/*.md` (`README.md` is the index)
- Add one short section per rule with: intent, hard requirement, examples
- Prefer project-specific rules over generic style guidance
- If a rule changes behavior across the codebase, update the relevant FD and mention the rule id/title
