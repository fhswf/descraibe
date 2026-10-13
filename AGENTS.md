# AI Agent & Developer Guidelines

Welcome to the repository! To maintain high code quality and ensure smooth deployments, all AI agents and human developers must strictly follow these rules.

## Task management with `bd` - Beads Tracking & Versioning

This repository uses **Beads** (`bd`) for coordinated tracking of AI tasks across multiple agent platforms (Codex, Open Hands, Antigravity). You must strictly document your progress and coordinate with other agents.

### Available Tools
- **MCP Server / Shell CLI:** Use the `bd` tool for all task management.
- **Central Storage:** The `issues.jsonl` file in the project root holds the current global task state.

### Workflow Rules (Multi-Agent Protocol)

1. **Check Status (Before any action):**
   - Always run `bd list` first to review open tasks and their current status.

2. **Claim Tasks (Concurrency Protection):**
   - Before starting work on any task (`<id>`), you must reserve it for yourself.
   - Use the command: `bd claim <id>` (or alternatively `bd update <id> --status claimed`).
   - **Strict Rule:** Never work on tasks that are already claimed or in progress by another agent!

3. **Document New Subtasks:**
   - If you discover new bugs, edge cases, or necessary next steps during your work, create a new bead immediately: `bd add "Task description"`.

4. **Synchronization & Commits:**
   - Beads stores its state locally in `issues.jsonl`.
   - Whenever you create, claim, or complete a task, you must commit the `issues.jsonl` file **along with your code changes** to Git (`git add issues.jsonl`).

5. **Complete Tasks:**
   - Once a code component is fully implemented and successfully tested, mark the task as done: `bd finish <id>`.

### Constraints
- **Do not** create automatic Git commit hooks via Beads to preserve clean, manual Git logs.
- Never overwrite another agent's claim unless explicitly instructed by the user (human).
Verwende Code mit Vorsicht.Would you like to add any specific naming conventions for the task descriptions (e.g., prefixing with [Feature], [Bug], or [Refactor]) so your agents categorize their work consistently?KI-Antworten können Fehler enthalten. Weitere Informationen

## 1. Commit Messages & Releases (`release-please`)

We use **`release-please`** to automate our versioning and changelogs. Because it parses commit history, all commit messages must strictly adhere to the **Conventional Commits** specification.

### Format:
`<type>(<scope>): <description>`

### Allowed Types for Releases:
- **feat**: A new feature (triggers a MINOR version bump).
- **fix**: A bug fix (triggers a PATCH version bump).
- **docs**: Documentation-only changes.
- **style**: Code formatting and white-space changes.
- **refactor**: Code changes that neither fix a bug nor add a feature.
- **test**: Adding or correcting tests.
- **chore**: Build tasks or package updates (does not trigger a release).

*Breaking Changes:* Append an `!` after the type/scope or add `BREAKING CHANGE:` in the footer to trigger a MAJOR version bump (e.g., `feat(api)!: remove deprecated v1 endpoints`).

---

## 2. Pre-Commit & Pre-Push Verification

Before committing or pushing code, you must verify that your local environment is stable. Run these validation steps in their respective monorepo directories.

### Local Tests Must Be Green

#### Frontend (React / TypeScript / Vite)
Navigate to the frontend package directory and run:
- **Linting:** `npm run lint`
- **Type-Check:** `npm run type-check` (or `tsc --noEmit`)
- **Unit Tests:** `npm run test` (Vite/Vitest)
- **Status:** 🟢 Green

#### Backend (Python / FastAPI)
Navigate to the backend package directory and run:
- **Unit Tests:** `pytest`
- **Status:** 🟢 Green

### Local Build & Kubernetes Validation
Since we deploy to Kubernetes (k8s), you must manually verify the build steps locally before pushing to prevent CI/CD pipeline breaks.

1. **Docker Builds:** Ensure both individual Dockerfiles build successfully.
   - Frontend: `docker build -t frontend:local ./frontend`
   - Backend: `docker build -t backend:local ./backend`
2. **Kustomize Validation:** Validate that your Kubernetes manifests render correctly.
   - Run: `kubectl kustomize ./k8s/overlays/dev` (adjust overlay path if needed)
   - Ensure the output renders without syntax or structural errors.

---

## 3. Secret Management (Sealed Secrets)

**Never commit raw secrets, passwords, or API keys in plaintext to this repository.**

- We use **Bitnami Sealed Secrets** to safely store sensitive data in Git.
- If you add or update environment variables, you must encrypt them using `kubeseal` before committing.
- Only commit the generated `SealedSecret` manifest (`kind: SealedSecret`). The raw `Secret` object must never leave your local environment.

---

Violations of these guidelines will break the automated release pipeline, and your pull request will not be merged.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
