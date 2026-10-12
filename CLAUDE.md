# Django AWS API Gateway Websockerts

Contact: Steve (steve@mapestech.co.uk).

## 🛑 Hard Restrictions (Do NOT Do)

- **CRITICAL:** Never read `.env` files. (Also enforced by deny rules in `.claude/settings.json`.)
- **CRITICAL:** Never commit secret keys, passwords, or `.env` files. Use `environ` or `decouple`.
- **CRITICAL:** Never use `print()` for debugging in production code. Use the standard `logging` module.
- **CRITICAL:** Never edit `requirements.txt` directly. Add or change dependencies in `requirements/requirements.in`, then run `python requirements/compile.py`.
- **CRITICAL:** Do not use hooks, background agents or tasks, auto-installed MCP servers, web fetch, or any other Claude Code capability not already in use in this project without first asking permission and explaining why. If unsure whether something counts, ask before using it.
- Never edit or delete a migration file that already exists.
- Never commit, push, or merge automatically. Leave changes uncommitted for peer review.
- When moving tests between files, do not replace the existing file; add the new tests in. If a class matches, add the new tests to the existing class.
- Never read, copy, delete, update or edit a .pem file

## Key Decisions

- Security first. Concretely: never disable CSRF or other security middleware; no raw SQL — use the ORM, and where raw SQL is unavoidable it must be parameterised; every new view needs an explicit authentication and permission decision; flag anything touching auth, sessions, file uploads, or external input parsing for human review.

## Code Style & Architecture

- **Version:** Python 3.14+, Django 6.1.
- **Style:** Strict PEP 8, enforced by Ruff and pre-commit. See `.pre-commit-config.yaml` and `pyproject.toml`.
- **Type hints:** Required on all new function signatures, including view returns (`HttpRequest` → `HttpResponse`).
- **Internationalisation:** Wrap all user-facing strings in `gettext`/`gettext_lazy`; use `{% translate %}` in templates.
- **Project layout:** Keep apps modular. Each app contains `models.py`, `views.py`, `urls.py`, `drf_views.py` for API logic, and `websockets.py` for websocket connections.

## Database & Models

- Prefer `select_related`/`prefetch_related` to avoid N+1 queries.
- Use `.only()`/`.defer()`/`.values()` where appropriate.
- Guard hot paths with `assertNumQueries` in tests.

## Testing

- Unit tests: `tests/unittests/`, extend `SimpleTestCase` only, no database access; use `patch` and mocking.
- Integration tests: `tests/integration_tests/`, extend `TestCase` or `TransactionTestCase` only; use fixtures/graph pre-loading where possible.
- Unit tests take priority over integration tests and are written first.
- Use TDD where possible, aiming for high coverage on new code. Don't chase 100% via meaningless tests.

## Code Search

- Before reading a file with `read_file`, use `grep` or `find` to locate the relevant file and line first. Avoid reading whole files speculatively.

## Documentation, Commit Messages, PRs, Change Logs and SOPs

- API reference lives in `docs/`.
- Project documentation in `docs/` is reStructuredText (`.rst`), built with Sphinx. `docs/tasks/` and `docs/sessions/` stay in Markdown.
- Before writing any documentation, commit message, PR description, change log entry, or SOP, read `docs/WRITING.rst` and follow it. Do not draft this material from memory of the rules.
- Commit subject lines use the imperative mood ("Add pagination to invoice list"); change log entries use the past tense ("Added pagination to the invoice list"). Full conventions are in `docs/WRITING.rst`.

## Commands

## Git Conventions

- `main` — production release
- `rc` — QA release of the platform
- `feature/*` — feature branches, where the main development happens; branch from `rc` <!-- TODO Steve: confirm base branch -->
- `hotfix/*` — branched from `main` for emergency hotfix development
- Reference ticket numbers (`SCDEV-123` style) in the commit body, never the subject line.

## Session Handoff Protocol

At the end of each session, create `docs/sessions/<username>-YYYYMMDD-SESSION-NOTES.md`, where `<username>` is the output of `git config user.name` lowercased with spaces replaced by hyphens, and the date is today's in YYYYMMDD format. Include:

- What was accomplished
- What was NOT done (and why)
- Current blockers
- Next session starting point
- Any important context future sessions need

Create the file but do not commit it; Steve commits it during review.
