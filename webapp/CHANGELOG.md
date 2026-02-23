# Changelog

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
