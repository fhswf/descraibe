# Changelog

## [0.19.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.18.0...v0.19.0) (2026-03-12)


### Features

* Replaced the custom AD audio strip UI with interactive WaveSurfer regions for audio descriptions, including playback controls, and refined image path parsing. ([a28f2f3](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/a28f2f30e18c0a6d2b2faf7e229a17f7b5fea861))


### Bug Fixes

* use nvidia/cuda base image instead of cudnn8-runtime to reduce size ([fdb27cf](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/fdb27cfecf4ebc74eafad3cc087de0fa81b26116))

## [0.18.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.17.1...v0.18.0) (2026-03-12)


### Features

* introduce a new configuration modal to manage pipeline parameters and models for all steps, replacing the old prompts step. ([a809f50](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/a809f50d069b53ef03411308e43cdb95161d53a1))

## [0.17.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.17.0...v0.17.1) (2026-03-12)


### Bug Fixes

* Adjust image preview styling and hover behavior in VideoTimeline to prevent overflow issues and refine positioning. ([1ca6d8e](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/1ca6d8ef8dadcad47d0fb2bafd76dd8006471e41))

## [0.17.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.16.1...v0.17.0) (2026-03-12)


### Features

* Add GitHub deployment creation for releases and remove ArgoCD deployment notification subscription. ([d2c8961](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/d2c896185528971b8d5c83108b2df3bce0bb1e6f))
* enhance video timeline UI with updated Wavesurfer styles, improved AD slot appearance, and interactive image thumbnails. ([ad6fac2](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/ad6fac25cca106412e7254c943d6d6e2fe5f758c))

## [0.16.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.16.0...v0.16.1) (2026-03-12)


### Bug Fixes

* Correct package.json path in Vite config. ([e9ee84a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e9ee84a196f09f6f2923681060937c4ee758765d))

## [0.16.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.15.0...v0.16.0) (2026-03-12)


### Features

* Display application version in the UI and update package versions. ([82460dd](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/82460ddfd2284769759dd8d8fe2b6f780c1cab31))
* Improve video timeline image visibility by increasing component heights. ([760ef5a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/760ef5a1ce5a9d36dc9bcdf9408fe688369e52f7))

## [0.15.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.14.1...v0.15.0) (2026-03-12)


### Features

* Implement model-specific parameters for temperature, max tokens, and detail, including fixed temperature for reasoning models. ([b728d2a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/b728d2ac87ff2547bf32dcb65112c3808430aeb7))


### Bug Fixes

* Update Kustomize configuration. ([ca65644](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/ca65644cadcd40144ad56db61b15018321e62482))

## [0.14.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.14.0...v0.14.1) (2026-03-11)


### Bug Fixes

* parsing presets ([2191f73](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2191f73c8676913ac58eccbf29bb4ea28822550b))
* parsing presets ([b3d183f](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/b3d183f41b7382e3bbc8f69b41e456e6341f3afa))

## [0.14.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.13.1...v0.14.0) (2026-03-10)


### Features

* implement uv-based dependency locking. ([4527471](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/45274717bee6d497b13ecc96d98c0c6624592962))


### Bug Fixes

* **ci:** revert updating deployment.yaml ([4527471](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/45274717bee6d497b13ecc96d98c0c6624592962))

## [0.13.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.13.0...v0.13.1) (2026-03-10)


### Bug Fixes

* minor fixes in useJob hook ([c1ea265](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/c1ea265a640a3eb7afb8a2d896a5457061e20ef4))

## [0.13.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.12.2...v0.13.0) (2026-03-10)


### Features

* add _load_available_models() and extend /api/system_info endpoint ([c32e5c7](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/c32e5c790b38216ebaad3b4bc20a38908a044b6e))


### Bug Fixes

* **config:** replace presets with full environments structure from notebook gpt_config.yaml ([2361ace](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2361ace7b4b7572ec9dc3e847fdaa93324b3ad39))
* **config:** replace presets with full environments structure from notebook gpt_config.yaml ([cfba03c](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/cfba03cec73bac53fa2ad4b8887655d2e091eb90))
* german error message and hint text in StepGenerate (Schritt 5) ([cda6db9](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/cda6db911a0626fb4915b824e697cb95bd50b78e))
* minor prompt template formatting adjustments. ([acfd245](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/acfd245cec8bdc989b50e7c8a9c9e2a7f365972e))
* minor prompt template formatting adjustments. ([c8ea022](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/c8ea022e45ecbbb5747d6b0f55b08accc6311e1c))

## [0.12.2](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.12.1...v0.12.2) (2026-03-09)


### Bug Fixes

* read gptParams from window on mount to fix race condition in StepGenerate ([9cc05a6](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/9cc05a6a754f2ed4c196300d9f591462fd7203b8))

## [0.12.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.12.0...v0.12.1) (2026-02-24)


### Bug Fixes

* Refactor progress bar callback to trigger on `attr == 'index'`, safely retrieve total, and include error handling. ([94989bb](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/94989bb437f5832edfb01784c197819f61958794))

## [0.12.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.11.0...v0.12.0) (2026-02-24)


### Features

* Update favicon and app logo, add custom scrollbar styling, and refactor Wavesurfer timeline integration. ([d0d7589](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/d0d7589e79cf25a30decb31761af3175ed3258ff))

## [0.11.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.10.1...v0.11.0) (2026-02-24)


### Features

* Add disk fallback to `get_job` to load jobs from disk if not found in memory. ([31e591c](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/31e591cd3f4d3e018a47a79d9532ff6d81288059))
* Add TTS generation and final video export functionality, including a new backend pipeline and frontend step. ([dcb5a26](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/dcb5a26806b89f4b767ea3a9107544140c3179f6))
* centralize progress display into a new `GlobalProgress` component and refactor step components to use global progress state. ([0283003](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/0283003f203188e0f9d25ddbd44160d4d3134346))

## [0.10.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.10.0...v0.10.1) (2026-02-24)


### Bug Fixes

* downgrade eslint to resolve compatibility issue in build ([0759bc6](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/0759bc6f9348dd16c914ee17f1db64af51ab729f))

## [0.10.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.9.0...v0.10.0) (2026-02-24)


### Features

* editing of ad slots ([4eda520](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/4eda52010753b6c3f266ad7169754aaafa5a2147))

## [0.9.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.8.1...v0.9.0) (2026-02-24)


### Features

* Introduce a new React/Vite frontend application featuring a multi-step UI for audiodescription job management, and update backend integration. ([2f83799](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2f8379905edf5d1f2a1518c314872fe5da4dc29e))
* Standardize time display with optional hours, enhance video timeline controls and interaction, and refactor the main application layout. ([8436ea8](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/8436ea8412d64eea193a26c00a2d03553a5393ac))

## [0.8.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.8.0...v0.8.1) (2026-02-23)


### Bug Fixes

* Update webapp Dockerfile. ([297fb0c](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/297fb0c13af2a91d1646fee664c36f30dfda1be8))

## [0.8.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.7.0...v0.8.0) (2026-02-23)


### Features

* enhance error handling in UI ([5bf0671](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/5bf067167a47b4943cb830629f83f2c5a17ab173))
* migrate the webapp backend from Flask to FastAPI and update associated dependencies. ([#60](https://github.com/fhswf/Audiodeskriptionen_SS25/issues/60)) ([5bf0671](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/5bf067167a47b4943cb830629f83f2c5a17ab173))


### Bug Fixes

* correct name of image column in data frame ([5bf0671](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/5bf067167a47b4943cb830629f83f2c5a17ab173))
* read prompts from config files ([5bf0671](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/5bf067167a47b4943cb830629f83f2c5a17ab173))

## [0.7.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.6.1...v0.7.0) (2026-02-23)


### Features

* Implement detailed progress reporting for audio extraction and transcription, including UI updates. ([7ef9f97](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/7ef9f97abebac0f9745eb671ea339d35579380ce))
* Implement GPU detection and utilization for transcription, displaying the status in the frontend UI. ([740635a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/740635acc68a4d54c95ec19cd3fc0a0817a06d91))

## [0.6.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.6.0...v0.6.1) (2026-02-23)


### Bug Fixes

* trigger workflow ([a8d4845](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/a8d4845cd08c3a20b8c2646da1886423cc3e40ae))

## [0.6.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.5.0...v0.6.0) (2026-02-23)


### Features

* Implement resumable chunked file uploads with dedicated backend endpoints for initialization, status, and chunk handling. ([15bbe0a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/15bbe0add464af41cf6e1ffbc2e9bfc17b15907c))
* Update PVC to use ReadWriteMany access mode and ceph-filesystem storage class. ([e34de27](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e34de27060507006c3fb4ae10476eb69424a8695))

## [0.5.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.4.0...v0.5.0) (2026-02-23)


### Features

* Add ArgoCD annotations for GitHub deployment notifications and an external link. ([16866af](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/16866af86d98b24614b869493b04b10f9c3fd969))

## [0.4.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.3.0...v0.4.0) (2026-02-23)


### Features

* Implement asynchronous slot generation with progress tracking and dedicated UI updates. ([dfbfdcd](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/dfbfdcda58e4c7881bb1b41cec70ee8c5cf962e2))

## [0.3.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.2.1...v0.3.0) (2026-02-23)


### Features

* Migrate Ingress configuration from Nginx to Traefik and update the host domain. ([88c84f2](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/88c84f2875dc4949bf0f02e3608bbbc7d6aaca82))


### Bug Fixes

* **ci:** correct release-please component file paths to avoid double webapp/ prefix ([61a8e69](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/61a8e6983b390fb06e8ff9f5bcfce419381a88d7))

## [0.2.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.2.0...v0.2.1) (2026-02-23)


### Bug Fixes

* **ci:** move k8s and CHANGELOG into webapp directory for release-please tracking ([d9a27f6](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/d9a27f6de0461a1355b0d6f883c4ace2c11df85c))
* Update ArgoCD application source repository URL and path to `fhswf` organization and `webapp/k8s` respectively. ([0b08825](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/0b088253bf3d041954da30db54e55bb26a84d350))

## [0.2.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.1.0...v0.2.0) (2026-02-23)


### Features

* Add Kubernetes deployment configurations and enhance image extraction with timestamp handling, blur detection, and refined frame selection. ([2a915a8](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2a915a8ac7fc6dd4f9632fb148edc7ef9344e1c6))
* add webapp for the AD process ([9def641](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/9def641f881646b6e6e6810a653fc23104f71564))
* Configure Playwright to automatically start the Flask backend and update `package.json` test scripts and module type. ([68b761f](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/68b761f5dd659399dcfe0c031686a3cd20a24736))
* Implement auto-loading of GPT prompts from a mounted directory, configured via Kubernetes ConfigMap. ([1747dc6](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/1747dc6187932a9bf6402b1bc7ad6c24b7620c8d))
* Implement job state persistence to disk, add ArgoCD deployment manifests, and include new tests for session management and VAD. ([bbd58e2](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/bbd58e2bbb726cb285f49c2559963e3ca81bb6bb))
* Implement session restoration and reset in the frontend, and update VAD audio loading to use soundfile. ([f9223bd](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/f9223bde193b8090a8a0c1c835b90820fc6fcc04))
