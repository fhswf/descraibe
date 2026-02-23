# Changelog

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
