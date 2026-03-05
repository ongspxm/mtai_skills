# Reuse Existing Patterns
## Intent
Reduce inconsistency and duplicated implementation styles.

## Rule
- Before introducing a new approach, check whether the repo already has a working pattern.
- If deviating from an established pattern, document why in the related FD.

## Examples
- Good: reuse existing request validation flow for a new endpoint.
- Bad: add a second validation style in one service without rationale.
