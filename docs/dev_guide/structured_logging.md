# Structured Logging
## Intent
Make production debugging and analysis reliable.

## Rule
- Use structured logs at service boundaries and failure paths.
- Include stable keys so logs can be queried consistently.

## Examples
- Good: `event=mail_send_failed user_id=... provider=... error_code=...`
- Bad: free-form text logs with variable wording and missing context.
