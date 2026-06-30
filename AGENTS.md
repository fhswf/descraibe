# AI Agent & Developer Guidelines

Welcome to the repository! To maintain high code quality and ensure smooth deployments, all AI agents and human developers must strictly follow these rules.

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
