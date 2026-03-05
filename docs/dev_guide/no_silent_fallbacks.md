# No Silent Fallback Values
## Intent
Make misconfiguration obvious and fast to diagnose.

## Rule
- Required configuration must fail loudly with a clear error.
- Do not mask missing required config with implicit defaults.

## Examples
- Good: fail startup when required API key is missing.
- Bad: silently substitute an empty key or test value.
