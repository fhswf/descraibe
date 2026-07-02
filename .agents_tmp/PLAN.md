# 1. OBJECTIVE

Migrate the frontend codebase from React with plain JavaScript (`.js/.jsx`) to TypeScript (`.ts/.tsx`), enabling:
- Static type safety across all components and utilities
- Better IDE support and developer experience
- Catch type-related errors at compile time rather than runtime
- Improved code documentation and maintainability

---

# 2. CONTEXT SUMMARY

**Current State:**
- Frontend uses Vite + React 19 + plain JavaScript (JSX)
- 14 JSX components in `frontend/src/components/features/`
- 2 custom hooks (`useJob.jsx`, `useCachedVideoUrl.jsx`)
- 1 utility file (`utils/uploadVideo.js`)
- Uses ESLint for linting (no TypeScript yet)
- Already has `@types/react` and `@types/react-dom` in devDependencies
- Uses Tailwind CSS v4

**Technology Stack:**
- Vite as build tool (supports TypeScript natively)
- React 19.2
- Tailwind CSS v4 with `@tailwindcss/vite` plugin
- ESLint for linting

**Files to Migrate:**
```
frontend/src/
├── App.jsx                          (main component)
├── main.jsx                          (entry point)
├── hooks/
│   ├── useJob.jsx                   (large context provider)
│   └── useCachedVideoUrl.jsx
├── utils/
│   └── uploadVideo.js
└── components/features/
    ├── ConfigModal.jsx
    ├── FaceMergeDialog.jsx
    ├── GlobalProgress.jsx
    ├── SRTWidget.jsx
    ├── StepGenerate.jsx
    ├── StepImages.jsx
    ├── StepPersons.jsx
    ├── StepResults.jsx
    ├── StepSlots.jsx
    ├── StepTTS.jsx
    ├── StepTranscribe.jsx
    ├── StepUpload.jsx
    ├── StepVAD.jsx
    └── VideoTimeline.jsx
```

---

# 3. APPROACH OVERVIEW

**Strategy:** Incremental migration using a **type-first approach**:
1. Set up TypeScript configuration without enforcing strict mode initially
2. Add types for shared interfaces (API responses, job data structures)
3. Convert files incrementally from `.jsx` → `.tsx`, starting with leaf components
4. Enable stricter TypeScript checking progressively
5. Use `.d.ts` declaration files for untyped dependencies

**Why this approach:**
- Minimal disruption to existing functionality
- Can run TypeScript alongside JavaScript during migration
- Allows catching obvious type issues first before tackling complex types
- Aligns with Vite's native TypeScript support (esbuild for transpilation)

---

# 4. IMPLEMENTATION STEPS

## Phase 1: Foundation Setup

### Step 1 -- Add TypeScript dependencies
Add required packages to `frontend/package.json`:

```json
"devDependencies": {
  "typescript": "^5.4.0",
  "@typescript-eslint/eslint-plugin": "^7.0.0",
  "@typescript-eslint/parser": "^7.0.0",
  // existing types already present: @types/react, @types/react-dom
}
```

Run `npm install` to install dependencies.

**Reference:** `frontend/package.json`

---

### Step 2 -- Create `tsconfig.json`
Create a TypeScript configuration file:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": false,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": false,
    "allowJs": true,
    "checkJs": false,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

**Note:** Start with `strict: false` to allow incremental migration. Enable stricter options later in Phase 3.

**Reference:** New file `frontend/tsconfig.json`

---

### Step 3 -- Create `tsconfig.node.json`
Create Node-specific TypeScript config for Vite:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

**Reference:** New file `frontend/tsconfig.node.json`

---

### Step 4 -- Update ESLint config for TypeScript
Update `frontend/eslint.config.js` to support TypeScript:

```javascript
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    plugins: {
      '@typescript-eslint': tsPlugin,
    },
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
      '@typescript-eslint/no-unused-vars': ['warn', { 
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_' 
      }],
    },
  },
])
```

**Reference:** `frontend/eslint.config.js`

---

### Step 5 -- Update vite.config.js to .ts
Rename `vite.config.js` to `vite.config.ts` and add TypeScript-friendly imports:

```typescript
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import fs from 'fs'
import path from 'path'
import process from 'node:process'
```

**Reference:** `frontend/vite.config.js` → `frontend/vite.config.ts`

---

## Phase 2: Type Definitions

### Step 6 -- Create shared type definitions
Create `frontend/src/types/index.ts` with interfaces for:

```typescript
// Job-related types
export interface JobData {
  job_id: string
  status: 'idle' | 'running' | 'error' | 'complete'
  original_video_filename?: string
  video_path?: string
  video_cache_key?: string
  latest_progress?: ProgressInfo
  created_at?: string
  // ... other fields from backend
}

export interface ProgressInfo {
  step?: string
  current?: number
  total?: number
  message?: string
}

export interface ProgressData {
  [step: string]: { msg: string; percent: number } | null
}

// Saved job metadata
export interface SavedJobMeta {
  name: string
  status: 'idle' | 'uploading' | 'running' | 'error'
  progressPercent: number | null
  progressMessage: string | null
  updatedAt?: string
}

// Auth state
export interface AuthState {
  loading: boolean
  enabled: boolean
  authenticated: boolean
  user: User | null
}

export interface User {
  id: string
  email: string
  name?: string
}

// Config params types
export interface GPTParams {
  system_prompt: string
  user_prompt: string
  ad_rules: string
  few_shots: string
  model: string
  temperature: number
  max_tokens: number
  detail: 'low' | 'high'
  cut: 'broadcast' | 'cinema'
  syllables_per_second: number
}

export interface VADParams {
  threshold: number
  min_speech_duration_ms: number
  min_silence_duration_ms: number
  min_pause_duration_s: number
}

export interface TranscribeParams {
  model_size: string
  language: string
  use_fw_vad: boolean
}

// Upload types
export interface UploadProgress {
  percent: number
  chunkIndex: number
  totalChunks: number
  uploadedBytes: number
  totalBytes: number
}

export interface UploadOptions {
  jobId: string
  file: File
  onProgress?: (progress: UploadProgress) => void
}

// SSE event types
export interface SSEEvent {
  event: string
  data: Record<string, unknown>
  job_id?: string
  step?: string
  message?: string
  progress?: ProgressInfo
}

// Video cache
export type CacheStatus = 'idle' | 'loading' | 'network' | 'opfs'

export interface CachedVideoResult {
  videoUrl: string | null
  cacheStatus: CacheStatus
}

// Theme
export type ThemeMode = 'system' | 'light' | 'dark'
```

**Reference:** New file `frontend/src/types/index.ts`

---

### Step 7 -- Create Vite environment types
Update `frontend/src/vite-env.d.ts` (or create if missing):

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_VERSION: string
  readonly VITE_APP_BUILD_CHANNEL: string
  readonly VITE_APP_COMMIT_SHA: string
  readonly VITE_APP_REPOSITORY_URL: string
  readonly VITE_APP_VERSION_LABEL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

**Reference:** New file `frontend/src/vite-env.d.ts`

---

## Phase 3: Incremental File Conversion

### Step 8 -- Convert utility files first
Convert in dependency order (no component dependencies):

1. `utils/uploadVideo.js` → `utils/uploadVideo.ts`

Key changes:
- Add `UploadOptions` interface type
- Add explicit return types
- Add error types

**Reference:** `frontend/src/utils/uploadVideo.ts`

---

### Step 9 -- Convert hooks
Convert custom hooks with type annotations:

1. `hooks/useCachedVideoUrl.jsx` → `hooks/useCachedVideoUrl.ts`
   - Add `CacheStatus` and `CachedVideoResult` types
   - Add explicit return type

2. `hooks/useJob.jsx` → `hooks/useJob.tsx`
   - Export context type: `JobContextValue`
   - Export param types: `GPTParams`, `VADParams`, `TranscribeParams`, etc.
   - Add explicit return types
   - Add prop types for `JobProvider`

**Reference:** `frontend/src/hooks/useJob.tsx`, `frontend/src/hooks/useCachedVideoUrl.ts`

---

### Step 10 -- Convert components (leaf components first)
Convert from simplest to most complex:

1. **Simple/Presentational components:**
   - `GlobalProgress.jsx` → `GlobalProgress.tsx`
   - `VideoTimeline.jsx` → `VideoTimeline.tsx`
   - `SRTWidget.jsx` → `SRTWidget.tsx`

2. **Medium complexity:**
   - `ConfigModal.jsx` → `ConfigModal.tsx`
   - `FaceMergeDialog.jsx` → `FaceMergeDialog.tsx`
   - `StepUpload.jsx` → `StepUpload.tsx`

3. **Step components:**
   - `StepVAD.jsx` → `StepVAD.tsx`
   - `StepTranscribe.jsx` → `StepTranscribe.tsx`
   - `StepSlots.jsx` → `StepSlots.tsx`
   - `StepImages.jsx` → `StepImages.tsx`
   - `StepPersons.jsx` → `StepPersons.tsx`
   - `StepGenerate.jsx` → `StepGenerate.tsx`
   - `StepTTS.jsx` → `StepTTS.tsx`
   - `StepResults.jsx` → `StepResults.tsx`

4. **Main components:**
   - `App.jsx` → `App.tsx`
   - `main.jsx` → `main.tsx`

For each component:
- Add prop interfaces (or `FC<Props>` for function components)
- Add explicit return types
- Import types from `types/index.ts`
- Convert `.js/.jsx` extensions to `.ts/.tsx` in imports

**Reference:** Each `frontend/src/components/features/*.tsx`

---

## Phase 4: Strict Mode & Polish

### Step 11 -- Enable strict TypeScript checks
Update `tsconfig.json` to enable stricter options:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true
  }
}
```

Fix any resulting type errors in the codebase.

---

### Step 12 -- Add TypeScript npm scripts
Update `frontend/package.json` scripts:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "lint": "eslint .",
    "type-check": "tsc --noEmit",
    "preview": "vite preview"
  }
}
```

---

### Step 13 -- Clean up legacy JS files
After all files are converted, remove original `.js/.jsx` files:
- `src/App.jsx` (replaced by `App.tsx`)
- `src/main.jsx` (replaced by `main.tsx`)
- `src/hooks/*.jsx` → `src/hooks/*.tsx`
- `src/utils/*.js` → `src/utils/*.ts`
- `src/components/features/*.jsx` → `src/components/features/*.tsx`

---

## Phase 5: Testing & Validation

### Step 14 -- Run type checking
```bash
cd frontend && npm run type-check
```

Fix any remaining type errors until clean.

---

### Step 15 -- Run linting
```bash
cd frontend && npm run lint
```

Fix any ESLint/TypeScript linting issues.

---

### Step 16 -- Build verification
```bash
cd frontend && npm run build
```

Verify production build succeeds without errors.

---

### Step 17 -- Manual testing
Test key workflows:
1. Video upload functionality
2. Pipeline step execution
3. Config modal interactions
4. Theme switching
5. Job persistence and reload

---

# 5. TESTING AND VALIDATION

## Type Checking
Run `npm run type-check`:
- [ ] `tsc --noEmit` passes with no errors
- [ ] All `.tsx` files compile without errors

## Linting
Run `npm run lint`:
- [ ] No TypeScript-related ESLint errors
- [ ] All `@typescript-eslint` rules pass

## Build
Run `npm run build`:
- [ ] Production build completes successfully
- [ ] No TypeScript compilation errors
- [ ] All assets bundled correctly

## Runtime Testing
Test in browser:
- [ ] All components render correctly
- [ ] Video upload works end-to-end
- [ ] All step components function properly
- [ ] Hooks (useJob, useCachedVideoUrl) work correctly
- [ ] No runtime type errors in console

## Success Criteria
- All `.js/.jsx` files converted to `.ts/.tsx`
- `tsconfig.json` with `strict: true` passes
- `npm run type-check` exits with code 0
- `npm run build` produces working production build
- No type-related runtime errors during manual testing
