import React from 'react';

// Job-related types
export type JobStatus = 'idle' | 'created' | 'uploading' | 'running' | 'error' | 'complete';

export interface ProgressInfo {
  step?: string;
  current?: number;
  total?: number;
  message?: string;
}

export interface JobData {
  job_id: string;
  status: JobStatus;
  original_video_filename?: string;
  video_path?: string;
  video_cache_key?: string;
  latest_progress?: ProgressInfo;
  created_at?: string;
  vad_result?: VADResult;
  transcription?: TranscriptionResult;
  slots?: Slot[];
  images?: Image[];
  persons?: Person[];
  gpt_results?: GPTResult[];
  gpt_records?: GPTRecord[];
  tts_result?: TTSResult;
  srt_texts?: Record<string, string>;
  // Additional fields from API responses
  video_stats?: unknown;
  pauses_count?: number;
  transcript_meta?: unknown;
  transcript_preview?: string;
  transcript_segments_count?: number;
  slots_count?: number;
  images_count?: number;
  persons_count?: number;
  gpt_records_broadcast?: unknown;
  gpt_records_directors?: unknown;
  final_mp4_path?: string;
  // Raw segments array used by VideoTimeline
  segments?: Array<{
    text?: string;
    start_s?: number;
    end_s?: number;
    index?: number;
  }>;
  [key: string]: unknown;
}

export interface VADResult {
  duration?: number;
  speech_chunks?: Array<[number, number]>;
}

export interface TranscriptionResult {
  text?: string;
  segments?: TranscriptionSegment[];
}

export interface TranscriptionSegment {
  start: number;
  end: number;
  text: string;
}

export interface Slot {
  id: number;
  start: number;
  end: number;
  slot?: number;
  start_s?: number;
  end_s?: number;
  person_id?: number;
  text?: string;
  image_path?: string;
  ad?: boolean;
}

export interface Image {
  path: string;
  timestamp: number;
  thumbnail?: string;
}

export interface Person {
  id: number;
  name?: string;
  embedding?: number[];
  face_path?: string;
}

export interface GPTResult {
  id: string;
  slot_id: number;
  text: string;
  ad: boolean;
  voice?: string;
}

export interface TTSResult {
  audio_path?: string;
  duration?: number;
}

export interface ProgressData {
  [step: string]: { msg: string; percent: number } | null;
}

// Saved job metadata
export interface SavedJobMeta {
  name: string;
  status: JobStatus | null;
  progressPercent: number | null;
  progressMessage: string | null;
  updatedAt?: string;
}

// Auth state
export interface AuthState {
  loading: boolean;
  enabled: boolean;
  authenticated: boolean;
  user: User | null;
}

export interface User {
  id: string;
  email: string;
  name?: string;
  picture?: string;
  sub?: string;
}

// Config params types
export interface GPTParams {
  system_prompt: string;
  user_prompt: string;
  ad_rules: string;
  few_shots: string;
  model: string;
  temperature: number;
  max_tokens: number;
  detail: 'low' | 'high';
  cut: 'broadcast' | 'cinema';
  syllables_per_second: number;
}

export interface VADParams {
  threshold: number;
  min_speech_duration_ms: number;
  min_silence_duration_ms: number;
  min_pause_duration_s: number;
}

export interface TranscribeParams {
  model_size: string;
  language: string;
  use_fw_vad: boolean;
}

export interface SlotsParams {
  min_slot_s: number;
  pad_in_s: number;
  pad_out_s: number;
  filter_whisper: boolean;
}

export interface TTSParams {
  apiKey: string;
  voice: string;
  duckingVolume: string;
}

export interface ImagesParams {
  threshold: number;
  blur_threshold: number;
  min_scene_length: number;
  short_scene_s: number;
}

// Upload types
export interface UploadProgress {
  percent: number;
  chunkIndex: number;
  totalChunks: number;
  uploadedBytes: number;
  totalBytes: number;
}

export interface UploadOptions {
  jobId: string;
  file: File;
  onProgress?: (_progress: UploadProgress) => void;
}

// SSE event types
export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
  job_id?: string;
  step?: string;
  message?: string;
  progress?: ProgressInfo;
}

// Video cache
export type CacheStatus = 'idle' | 'loading' | 'network' | 'opfs';

export interface CachedVideoResult {
  videoUrl: string | null;
  cacheStatus: CacheStatus;
}

// Theme
export type ThemeMode = 'system' | 'light' | 'dark';

// Job Context Value
export interface JobContextValue {
  jobId: string | null;
  setJobId: (_id: string | null) => void;
  savedJobIds: string[];
  savedJobMeta: Record<string, SavedJobMeta>;
  selectJob: (_id: string) => void;
  removeSavedJobId: (_id: string) => void;
  updateSavedJobMeta: (_id: string, _meta: Partial<SavedJobMeta>) => void;
  jobData: JobData | null;
  sseConnected: boolean;
  gptRecords: GPTRecord[];
  setGptRecords: React.Dispatch<React.SetStateAction<GPTRecord[]>>;
  currentStep: number;
  setCurrentStep: (_step: number) => void;
  doneSteps: Set<number>;
  markStepDone: (_step: number) => void;
  progressData: ProgressData;
  setProgressData: React.Dispatch<React.SetStateAction<ProgressData>>;
  focusedSlot: number | null;
  setFocusedSlot: (_id: number | null) => void;
  createJob: () => Promise<string | null>;
  fetchJobData: (_jobId: string) => Promise<void>;
  srtTexts: Record<string, string>;
  setSrtTexts: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  isSavingSrt: boolean;
  handleSaveSrtTexts: () => Promise<void>;
  handleUpdateSlotTiming: (_slotId: number, _start: number, _end: number) => Promise<void>;
  isConfigModalOpen: boolean;
  setIsConfigModalOpen: (_open: boolean) => void;
  gptParams: GPTParams;
  setGptParams: React.Dispatch<React.SetStateAction<GPTParams>>;
  availableModels: string[];
  setAvailableModels: React.Dispatch<React.SetStateAction<string[]>>;
  vadParams: VADParams;
  setVadParams: React.Dispatch<React.SetStateAction<VADParams>>;
  transcribeParams: TranscribeParams;
  setTranscribeParams: React.Dispatch<React.SetStateAction<TranscribeParams>>;
  slotsParams: SlotsParams;
  setSlotsParams: React.Dispatch<React.SetStateAction<SlotsParams>>;
  ttsParams: TTSParams;
  setTtsParams: React.Dispatch<React.SetStateAction<TTSParams>>;
  imagesParams: ImagesParams;
  setImagesParams: React.Dispatch<React.SetStateAction<ImagesParams>>;
  handleRunVAD: () => Promise<void>;
  handleRunTranscribe: () => Promise<void>;
  handleRunSlots: () => Promise<void>;
  handleRunImages: () => Promise<void>;
  handleRunPersons: () => Promise<void>;
  handleRunGPT: () => Promise<void>;
  handleUpdateGPTRecord: (_recordId: string, _updates: Partial<GPTRecord>) => void;
  handleRunTTS: () => Promise<void>;
  runAllSteps: () => void;
  isRunAllActive: boolean;
  stopRunAll: () => void;
  authState: AuthState;
  login: () => void;
  logout: () => Promise<void>;
  refreshAuthState: () => Promise<void>;
}

export interface GPTRecord {
  id: string;
  slot_id: number;
  text: string;
  ad: boolean;
  voice?: string;
  // Additional properties from API responses
  slot?: number;
  start_s?: number;
  end_s?: number;
  duration_s?: number;
  // Status properties
  skipped?: boolean;
  ok?: boolean;
  error?: { message?: string };
  reason?: string;
  // Syllable information
  syllable_limit?: number;
  syllables_original?: number;
  syllables_final?: number;
  // Original text for director's cut
  original_text?: string;
}
