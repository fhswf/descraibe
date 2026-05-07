# Changelog

## [0.22.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.22.0...v0.22.1) (2026-05-07)


### Bug Fixes

* update CSV writer to use comma delimiter and adjust frame time format to dot ([25e3144](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/25e31447b4fa0c8eaa4152fda941f1d28d15f8ba))

## [0.22.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.21.0...v0.22.0) (2026-05-06)


### Features

* Add scene detection progress reporting and frame count functionality ([bab6606](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/bab6606731e2650e7fd5a28be0c42f2178b69801))
* Add transcript context handling and previous AD context to GPT description ([df13084](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/df130845f7d5933b8eba0cf386945dd06b5cee14))
* Display storage quota information in the frontend ([e740f72](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e740f72a9b1f79634e8fd950c11b08ce939a8be0))
* Enhance audio extraction process in VAD pipeline ([e740f72](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e740f72a9b1f79634e8fd950c11b08ce939a8be0))
* Enhance error handling and text management in GPT processing and SRT widget ([90dbcae](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/90dbcae6190605b93cced62ffa15ecd92dc3f478))
* enhance transcription process with progress tracking and job status updates ([188f054](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/188f054705a4b355d2623ad423e51fefecc3a85a))
* Enhance video handling by introducing displayedVideo state and updating VideoTimeline to use timelineJobData ([8219146](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/82191462aef2c79e6b1e5671bd6b5e658b029827))
* Extend session manager to include original video filename and SHA256 ([e740f72](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e740f72a9b1f79634e8fd950c11b08ce939a8be0))
* implement chunked video upload functionality and enhance progress tracking ([d54c198](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/d54c19810a5f495798439028abb68fa9d3bbc152))
* Implement consecutive error handling in GPT generation and add corresponding tests ([bbb23dd](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/bbb23dd7813f2a4f01303ed58f485e1fd6824e87))
* Implement in-process event bus for pub/sub with event replay ([e740f72](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e740f72a9b1f79634e8fd950c11b08ce939a8be0))
* implement job summary streaming and enhance upload progress tracking ([be89cf7](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/be89cf78ee5fc9fbff817e69d245cd672275639e))
* implement video caching mechanism and enhance progress tracking in image extraction ([501372b](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/501372b20fd4ea667856cf9c8a382880637b7810))
* Improve model selection handling in ConfigModal and JobProvider ([b183f6c](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/b183f6caa3e026bbaf478a55aa03dab831a33e89))
* Introduce environment variables for frontend build configuration ([e740f72](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e740f72a9b1f79634e8fd950c11b08ce939a8be0))
* **k8s:** add SealedSecrets for OpenAI API keys in staging and release environments ([69e8fde](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/69e8fde17b525c9727553131091ea083bd09cd5f))
* **k8s:** restructure deployment configuration for staging and release environments ([8f82711](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/8f8271111a82c6e91672eb1dd2b5591dc5bd3bff))
* Refactor VideoTimeline to improve state management and enhance audio region handling ([e403121](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e403121185e1ae7b73d19810a9019ce58ca1196f))
* Strip whitespace from API key in TTS generation and add corresponding test ([f765fec](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/f765feca0ca72830154a8769c2837a0b28c82a11))
* Update GPT model references to gpt-5-mini-2025-08-07 and improve model selection handling ([f3d72ef](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/f3d72ef3bda88fa81ec367073cc027864386f209))


### Bug Fixes

* **docs:** update README and SealedSecret manifest for OpenAI API key handling ([21d348f](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/21d348fef5ad34e34e017be16d5107e36565f1c4))
* **k8s:** correct indentation in openai-sealedsecret.yaml template section ([6c46474](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/6c46474ccaa289a01adb14aa837d143cb4d1bd55))
* **k8s:** revert webapp image tag to v0.20.0 ([2616fbe](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2616fbeef12d063d44778dafdac1d5f83f8ad1fa))
* **k8s:** update Ingress host value for staging environment ([6e45fcc](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/6e45fcce01cc8ec3fe04b2efd1b202a1b10a3963))
* **k8s:** update OPENAI_API_KEY in SealedSecret for staging environment ([72e0f8b](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/72e0f8b84a97d2a4acddc872c24e955cebc7dc76))
* Update job metadata handling to include original video filename ([e740f72](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e740f72a9b1f79634e8fd950c11b08ce939a8be0))

## [0.21.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.20.0...v0.21.0) (2026-03-17)


### Features

* Add `store=True` to `llm.generate` calls to enable response storage. ([fcefe7c](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/fcefe7c6e0d093dd4dffb8b5858a3fc6f53ce44f))
* Add configurable syllables per second parameter to the UI and update its default value to 6.0 across the application. ([b25fa9e](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/b25fa9e7518df98d25136ce99d6f6d6e0c076f46))
* implement per-job logging to a dedicated file and expose it via API. ([58c8434](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/58c8434cf1e197dd2b0ef66225331316cfe3970d))

## [0.20.0](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.19.1...v0.20.0) (2026-03-13)


### Features

* add _load_available_models() and extend /api/system_info endpoint ([c32e5c7](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/c32e5c790b38216ebaad3b4bc20a38908a044b6e))
* Add ArgoCD annotations for GitHub deployment notifications and an external link. ([16866af](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/16866af86d98b24614b869493b04b10f9c3fd969))
* Add disk fallback to `get_job` to load jobs from disk if not found in memory. ([31e591c](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/31e591cd3f4d3e018a47a79d9532ff6d81288059))
* Add GitHub deployment creation for releases and remove ArgoCD deployment notification subscription. ([d2c8961](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/d2c896185528971b8d5c83108b2df3bce0bb1e6f))
* Add Kubernetes deployment configurations and enhance image extraction with timestamp handling, blur detection, and refined frame selection. ([2a915a8](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2a915a8ac7fc6dd4f9632fb148edc7ef9344e1c6))
* Add TTS generation and final video export functionality, including a new backend pipeline and frontend step. ([dcb5a26](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/dcb5a26806b89f4b767ea3a9107544140c3179f6))
* add webapp for the AD process ([9def641](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/9def641f881646b6e6e6810a653fc23104f71564))
* centralize progress display into a new `GlobalProgress` component and refactor step components to use global progress state. ([0283003](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/0283003f203188e0f9d25ddbd44160d4d3134346))
* Configure Playwright to automatically start the Flask backend and update `package.json` test scripts and module type. ([68b761f](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/68b761f5dd659399dcfe0c031686a3cd20a24736))
* Display application version in the UI and update package versions. ([82460dd](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/82460ddfd2284769759dd8d8fe2b6f780c1cab31))
* editing of ad slots ([4eda520](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/4eda52010753b6c3f266ad7169754aaafa5a2147))
* enhance error handling in UI ([5bf0671](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/5bf067167a47b4943cb830629f83f2c5a17ab173))
* enhance video timeline UI with updated Wavesurfer styles, improved AD slot appearance, and interactive image thumbnails. ([ad6fac2](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/ad6fac25cca106412e7254c943d6d6e2fe5f758c))
* Implement asynchronous slot generation with progress tracking and dedicated UI updates. ([dfbfdcd](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/dfbfdcda58e4c7881bb1b41cec70ee8c5cf962e2))
* Implement auto-loading of GPT prompts from a mounted directory, configured via Kubernetes ConfigMap. ([1747dc6](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/1747dc6187932a9bf6402b1bc7ad6c24b7620c8d))
* Implement detailed progress reporting for audio extraction and transcription, including UI updates. ([7ef9f97](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/7ef9f97abebac0f9745eb671ea339d35579380ce))
* Implement GPU detection and utilization for transcription, displaying the status in the frontend UI. ([740635a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/740635acc68a4d54c95ec19cd3fc0a0817a06d91))
* Implement job state persistence to disk, add ArgoCD deployment manifests, and include new tests for session management and VAD. ([bbd58e2](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/bbd58e2bbb726cb285f49c2559963e3ca81bb6bb))
* Implement model-specific parameters for temperature, max tokens, and detail, including fixed temperature for reasoning models. ([b728d2a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/b728d2ac87ff2547bf32dcb65112c3808430aeb7))
* Implement resumable chunked file uploads with dedicated backend endpoints for initialization, status, and chunk handling. ([15bbe0a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/15bbe0add464af41cf6e1ffbc2e9bfc17b15907c))
* Implement session restoration and reset in the frontend, and update VAD audio loading to use soundfile. ([f9223bd](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/f9223bde193b8090a8a0c1c835b90820fc6fcc04))
* implement uv-based dependency locking. ([4527471](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/45274717bee6d497b13ecc96d98c0c6624592962))
* Improve video timeline image visibility by increasing component heights. ([760ef5a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/760ef5a1ce5a9d36dc9bcdf9408fe688369e52f7))
* introduce a new configuration modal to manage pipeline parameters and models for all steps, replacing the old prompts step. ([a809f50](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/a809f50d069b53ef03411308e43cdb95161d53a1))
* Introduce a new React/Vite frontend application featuring a multi-step UI for audiodescription job management, and update backend integration. ([2f83799](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2f8379905edf5d1f2a1518c314872fe5da4dc29e))
* Migrate Ingress configuration from Nginx to Traefik and update the host domain. ([88c84f2](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/88c84f2875dc4949bf0f02e3608bbbc7d6aaca82))
* migrate the webapp backend from Flask to FastAPI and update associated dependencies. ([#60](https://github.com/fhswf/Audiodeskriptionen_SS25/issues/60)) ([5bf0671](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/5bf067167a47b4943cb830629f83f2c5a17ab173))
* Replaced the custom AD audio strip UI with interactive WaveSurfer regions for audio descriptions, including playback controls, and refined image path parsing. ([a28f2f3](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/a28f2f30e18c0a6d2b2faf7e229a17f7b5fea861))
* Standardize time display with optional hours, enhance video timeline controls and interaction, and refactor the main application layout. ([8436ea8](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/8436ea8412d64eea193a26c00a2d03553a5393ac))
* Update favicon and app logo, add custom scrollbar styling, and refactor Wavesurfer timeline integration. ([d0d7589](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/d0d7589e79cf25a30decb31761af3175ed3258ff))
* Update PVC to use ReadWriteMany access mode and ceph-filesystem storage class. ([e34de27](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e34de27060507006c3fb4ae10476eb69424a8695))


### Bug Fixes

* Adjust image preview styling and hover behavior in VideoTimeline to prevent overflow issues and refine positioning. ([1ca6d8e](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/1ca6d8ef8dadcad47d0fb2bafd76dd8006471e41))
* Change CSV export time format from milliseconds to frames using a new `_frame_time` function. ([407b6e4](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/407b6e4af45c2fdbae3d291a0dba92341c48d8bd)), closes [#91](https://github.com/fhswf/Audiodeskriptionen_SS25/issues/91)
* **ci:** correct release-please component file paths to avoid double webapp/ prefix ([61a8e69](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/61a8e6983b390fb06e8ff9f5bcfce419381a88d7))
* **ci:** move k8s and CHANGELOG into webapp directory for release-please tracking ([d9a27f6](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/d9a27f6de0461a1355b0d6f883c4ace2c11df85c))
* **ci:** revert updating deployment.yaml ([4527471](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/45274717bee6d497b13ecc96d98c0c6624592962))
* **config:** replace presets with full environments structure from notebook gpt_config.yaml ([2361ace](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2361ace7b4b7572ec9dc3e847fdaa93324b3ad39))
* **config:** replace presets with full environments structure from notebook gpt_config.yaml ([cfba03c](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/cfba03cec73bac53fa2ad4b8887655d2e091eb90))
* correct name of image column in data frame ([5bf0671](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/5bf067167a47b4943cb830629f83f2c5a17ab173))
* Correct package.json path in Vite config. ([e9ee84a](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/e9ee84a196f09f6f2923681060937c4ee758765d))
* downgrade eslint to resolve compatibility issue in build ([0759bc6](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/0759bc6f9348dd16c914ee17f1db64af51ab729f))
* german error message and hint text in StepGenerate (Schritt 5) ([cda6db9](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/cda6db911a0626fb4915b824e697cb95bd50b78e))
* Import `useMemo` in `useJob` hook. ([f376291](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/f37629181f17d42f8da95ec81c5dd98bc982ed03))
* minor fixes in useJob hook ([c1ea265](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/c1ea265a640a3eb7afb8a2d896a5457061e20ef4))
* minor prompt template formatting adjustments. ([acfd245](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/acfd245cec8bdc989b50e7c8a9c9e2a7f365972e))
* minor prompt template formatting adjustments. ([c8ea022](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/c8ea022e45ecbbb5747d6b0f55b08accc6311e1c))
* parsing presets ([2191f73](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/2191f73c8676913ac58eccbf29bb4ea28822550b))
* parsing presets ([b3d183f](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/b3d183f41b7382e3bbc8f69b41e456e6341f3afa))
* read gptParams from window on mount to fix race condition in StepGenerate ([9cc05a6](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/9cc05a6a754f2ed4c196300d9f591462fd7203b8))
* read prompts from config files ([5bf0671](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/5bf067167a47b4943cb830629f83f2c5a17ab173))
* Refactor progress bar callback to trigger on `attr == 'index'`, safely retrieve total, and include error handling. ([94989bb](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/94989bb437f5832edfb01784c197819f61958794))
* trigger workflow ([a8d4845](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/a8d4845cd08c3a20b8c2646da1886423cc3e40ae))
* Update ArgoCD application source repository URL and path to `fhswf` organization and `webapp/k8s` respectively. ([0b08825](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/0b088253bf3d041954da30db54e55bb26a84d350))
* Update Kustomize configuration. ([ca65644](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/ca65644cadcd40144ad56db61b15018321e62482))
* Update webapp Dockerfile. ([297fb0c](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/297fb0c13af2a91d1646fee664c36f30dfda1be8))
* use nvidia/cuda base image instead of cudnn8-runtime to reduce size ([fdb27cf](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/fdb27cfecf4ebc74eafad3cc087de0fa81b26116))

## [0.19.1](https://github.com/fhswf/Audiodeskriptionen_SS25/compare/v0.19.0...v0.19.1) (2026-03-13)


### Bug Fixes

* Change CSV export time format from milliseconds to frames using a new `_frame_time` function. ([407b6e4](https://github.com/fhswf/Audiodeskriptionen_SS25/commit/407b6e4af45c2fdbae3d291a0dba92341c48d8bd)), closes [#91](https://github.com/fhswf/Audiodeskriptionen_SS25/issues/91)

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
