import React, { useState } from 'react';
import { useJob } from '../../hooks/useJob.jsx';

export function ConfigModal() {
  const { 
    isConfigModalOpen, setIsConfigModalOpen, 
    gptParams, setGptParams, availableModels,
    vadParams, setVadParams,
    transcribeParams, setTranscribeParams,
    slotsParams, setSlotsParams,
    ttsParams, setTtsParams,
    imagesParams, setImagesParams
  } = useJob();

  const [activeTab, setActiveTab] = useState('gpt');

  if (!isConfigModalOpen) return null;

  const inputCls = "resize-y bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15";
  const selectCls = "bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 py-2 outline-none transition-colors focus:border-violet-500 focus:ring-3 focus:ring-violet-500/15";

  const isFixedTemp = gptParams.model && (
    gptParams.model.startsWith('o1') || 
    gptParams.model.startsWith('o3') || 
    gptParams.model.startsWith('gpt-5')
  );

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-[#0f0f0f] border border-border-subtle rounded-2xl w-[80vw] h-[80vh] shadow-2xl flex flex-col">
        
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border-subtle shrink-0">
          <div className="flex items-center gap-3">
            <div className="text-2xl leading-none">⚙️</div>
            <div>
              <h2 className="text-xl font-bold">Pipeline-Konfiguration</h2>
              <p className="text-xs text-text-secondary">Passe Modelle, Parameter und Metadaten für alle Schritte an.</p>
            </div>
          </div>
          <button 
            className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors"
            onClick={() => setIsConfigModalOpen(false)}
          >
            <span className="material-icons-round text-text-primary">close</span>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border-subtle overflow-x-auto shrink-0 custom-scrollbar">
          {[
            { id: 'vad', label: '🔇 Sprechpausen (VAD)' },
            { id: 'transcribe', label: '📝 Transkription' },
            { id: 'slots', label: '🕐 AD-Slots' },
            { id: 'images', label: '🖼️ Bilder' },
            { id: 'gpt', label: '💬 Prompts & GPT' },
            { id: 'tts', label: '🎙️ Vertonung (TTS)' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === tab.id 
                  ? 'border-violet-500 text-violet-500 bg-violet-500/5' 
                  : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-white/5'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex flex-col gap-5 flex-1 custom-scrollbar">
          
          {/* --- VAD TAB --- */}
          {activeTab === 'vad' && (
            <div className="bg-bg-card border border-border-subtle rounded-xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Parameter</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">VAD-Schwellwert: {vadParams.threshold}</label>
                        <input
                            type="range" min="0.1" max="0.9" step="0.05"
                            value={vadParams.threshold}
                            onChange={e => setVadParams({ ...vadParams, threshold: parseFloat(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 outline-none transition-colors accent-violet-500 pr-0 pl-0 py-0"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Sprachdauer (ms)</label>
                        <input
                            type="number" min="100" step="100"
                            value={vadParams.min_speech_duration_ms}
                            onChange={e => setVadParams({ ...vadParams, min_speech_duration_ms: parseInt(e.target.value) })}
                            className={inputCls}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Stille (ms)</label>
                        <input
                            type="number" min="50" step="50"
                            value={vadParams.min_silence_duration_ms}
                            onChange={e => setVadParams({ ...vadParams, min_silence_duration_ms: parseInt(e.target.value) })}
                            className={inputCls}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Pausen-Dauer (s)</label>
                        <input
                            type="number" min="0.1" step="0.1"
                            value={vadParams.min_pause_duration_s}
                            onChange={e => setVadParams({ ...vadParams, min_pause_duration_s: parseFloat(e.target.value) })}
                            className={inputCls}
                        />
                    </div>
                </div>
            </div>
          )}

          {/* --- TRANSCRIBE TAB --- */}
          {activeTab === 'transcribe' && (
            <div className="bg-bg-card border border-border-subtle rounded-xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Modell & Optionen</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Whisper Modell</label>
                        <select
                            value={transcribeParams.model_size}
                            onChange={e => setTranscribeParams({ ...transcribeParams, model_size: e.target.value })}
                            className={selectCls}
                        >
                            <option value="large-v3">large-v3 (beste Qualität)</option>
                            <option value="medium">medium</option>
                            <option value="small">small (schnell)</option>
                        </select>
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Sprache</label>
                        <select
                            value={transcribeParams.language}
                            onChange={e => setTranscribeParams({ ...transcribeParams, language: e.target.value })}
                            className={selectCls}
                        >
                            <option value="de">Deutsch</option>
                            <option value="en">Englisch</option>
                        </select>
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Faster-Whisper VAD</label>
                        <select
                            value={transcribeParams.use_fw_vad.toString()}
                            onChange={e => setTranscribeParams({ ...transcribeParams, use_fw_vad: e.target.value === 'true' })}
                            className={selectCls}
                        >
                            <option value="true">Ja</option>
                            <option value="false">Nein</option>
                        </select>
                    </div>
                </div>
            </div>
          )}

          {/* --- SLOTS TAB --- */}
          {activeTab === 'slots' && (
            <div className="bg-bg-card border border-border-subtle rounded-xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Slot-Parameter</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Slot-Dauer (s)</label>
                        <input
                            type="number" min="0.1" step="0.1"
                            value={slotsParams.min_slot_s}
                            onChange={e => setSlotsParams({ ...slotsParams, min_slot_s: parseFloat(e.target.value) })}
                            className={inputCls}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Eingangs-Padding (s)</label>
                        <input
                            type="number" min="0" step="0.05"
                            value={slotsParams.pad_in_s}
                            onChange={e => setSlotsParams({ ...slotsParams, pad_in_s: parseFloat(e.target.value) })}
                            className={inputCls}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Ausgangs-Padding (s)</label>
                        <input
                            type="number" min="0" step="0.05"
                            value={slotsParams.pad_out_s}
                            onChange={e => setSlotsParams({ ...slotsParams, pad_out_s: parseFloat(e.target.value) })}
                            className={inputCls}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Whisper-Filter</label>
                        <select
                            value={slotsParams.filter_whisper.toString()}
                            onChange={e => setSlotsParams({ ...slotsParams, filter_whisper: e.target.value === 'true' })}
                            className={selectCls}
                        >
                            <option value="false">Nein</option>
                            <option value="true">Ja (Slots mit Sprache entfernen)</option>
                        </select>
                        <p className="text-[0.7rem] text-text-muted mt-1">Gefundene Wörter beschneiden die Dauer von Pausen.</p>
                    </div>
                </div>
            </div>
          )}

          {/* --- IMAGES TAB --- */}
          {activeTab === 'images' && (
            <div className="bg-bg-card border border-border-subtle rounded-xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Parameter</p>
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Scene-Threshold: {imagesParams.threshold}</label>
                        <input
                            type="range" min="10" max="50" step="1"
                            value={imagesParams.threshold}
                            onChange={e => setImagesParams({ ...imagesParams, threshold: parseInt(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 outline-none transition-colors accent-violet-500 pr-0 pl-0 py-0"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Blur-Threshold: {imagesParams.blur_threshold}</label>
                        <input
                            type="range" min="20" max="200" step="5"
                            value={imagesParams.blur_threshold}
                            onChange={e => setImagesParams({ ...imagesParams, blur_threshold: parseInt(e.target.value) })}
                            className="bg-white/5 border border-border-subtle rounded-md text-text-primary text-[0.875rem] px-2.5 outline-none transition-colors accent-violet-500 pr-0 pl-0 py-0"
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Min. Szenenlänge (Frames)</label>
                        <input
                            type="number" min="5"
                            value={imagesParams.min_scene_length}
                            onChange={e => setImagesParams({ ...imagesParams, min_scene_length: parseInt(e.target.value) })}
                            className={inputCls}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <label className="text-[0.8rem] font-medium text-text-secondary">Kurzszenen-Grenze (s)</label>
                        <input
                            type="number" min="0.5" step="0.5"
                            value={imagesParams.short_scene_s}
                            onChange={e => setImagesParams({ ...imagesParams, short_scene_s: parseFloat(e.target.value) })}
                            className={inputCls}
                        />
                    </div>
                </div>
            </div>
          )}

          {/* --- GPT TAB --- */}
          {activeTab === 'gpt' && (
            <div className="flex flex-col gap-5">
            {/* System instruction */}
            <div className="bg-bg-card border border-border-subtle rounded-xl p-4 flex flex-col">
              <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">System-Instruktion (Rolle & Grundregeln)</p>
              <textarea placeholder="Du bist ein professioneller Audiodeskriptions-Autor…"
                value={gptParams.system_prompt}
                onChange={e => setGptParams({ ...gptParams, system_prompt: e.target.value })}
                className={`w-full min-h-[100px] ${inputCls}`} />
            </div>

            {/* User instruction */}
            <div className="bg-bg-card border border-border-subtle rounded-xl p-4 flex flex-col">
              <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">User-Instruktion (Aufgabe & Format)</p>
              <textarea placeholder="Erstelle eine präzise Audiodeskription für die folgenden Szenenbilder…"
                value={gptParams.user_prompt}
                onChange={e => setGptParams({ ...gptParams, user_prompt: e.target.value })}
                className={`w-full min-h-[100px] ${inputCls}`} />
            </div>

            {/* AD rules */}
            <div className="bg-bg-card border border-border-subtle rounded-xl p-4 flex flex-col">
              <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">AD-Regeln</p>
              <textarea placeholder="1. Beschreibe Handlungen im Präsens…"
                value={gptParams.ad_rules}
                onChange={e => setGptParams({ ...gptParams, ad_rules: e.target.value })}
                className={`w-full min-h-[150px] ${inputCls}`} />
            </div>

            {/* Few shots */}
            <div className="bg-bg-card border border-border-subtle rounded-xl p-4 flex flex-col">
              <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">Few-Shots (optional)</p>
              <textarea placeholder="Beispiel 1: …"
                value={gptParams.few_shots}
                onChange={e => setGptParams({ ...gptParams, few_shots: e.target.value })}
                className={`w-full min-h-[100px] ${inputCls}`} />
            </div>

          {/* GPT model & params */}
          <div className="bg-bg-card border border-border-subtle rounded-xl p-4">
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">GPT-Modell & Parameter</p>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-4">

              {/* Model dropdown */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[0.8rem] font-medium text-text-secondary min-h-[1.25rem]">Modell</label>
                <select value={gptParams.model}
                  onChange={e => {
                    const selectedModel = e.target.value;
                    const modelInfo = availableModels.find(m => m.model === selectedModel);
                    if (modelInfo) {
                      setGptParams({
                        ...gptParams, 
                        model: modelInfo.model,
                        temperature: modelInfo.temperature !== undefined ? modelInfo.temperature : gptParams.temperature,
                        max_tokens: modelInfo.max_tokens !== undefined ? modelInfo.max_tokens : gptParams.max_tokens,
                        detail: modelInfo.detail !== undefined ? modelInfo.detail : gptParams.detail
                      });
                    } else {
                      setGptParams({ ...gptParams, model: selectedModel });
                    }
                  }}
                  className={selectCls}>
                  {availableModels.length > 0
                    ? availableModels.map(({ env, model }) => (
                        <option key={`${env}-${model}`} value={model}>{model}</option>
                      ))
                    : (
                      <>
                        <option value="gpt-4o">gpt-4o</option>
                        <option value="gpt-4o-mini">gpt-4o-mini</option>
                      </>
                    )
                  }
                </select>
              </div>

              {/* Temperature */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[0.8rem] font-medium text-text-secondary min-h-[1.25rem]">
                  Temperature: {gptParams.temperature} {isFixedTemp && "(Fixiert)"}
                </label>
                <input type="range" min="0" max="1.5" step="0.05"
                  value={gptParams.temperature}
                  disabled={isFixedTemp}
                  onChange={e => setGptParams({ ...gptParams, temperature: parseFloat(e.target.value) })}
                  className={`py-0 ${isFixedTemp ? "opacity-50 cursor-not-allowed" : "accent-violet-500"}`} />
              </div>

              {/* Max tokens */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[0.8rem] font-medium text-text-secondary min-h-[1.25rem]">Max. Tokens</label>
                <input type="number" min="64" step="64"
                  value={gptParams.max_tokens}
                  onChange={e => setGptParams({ ...gptParams, max_tokens: parseInt(e.target.value) })}
                  className={selectCls} />
              </div>

              {/* Cut type */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[0.8rem] font-medium text-text-secondary min-h-[1.25rem]">Cut-Typ</label>
                <select value={gptParams.cut}
                  onChange={e => setGptParams({ ...gptParams, cut: e.target.value })}
                  className={selectCls}>
                  <option value="broadcast">Broadcast (Silbenlimit)</option>
                  <option value="directors">Director's Cut (ausführlich)</option>
                </select>
              </div>
              
              {/* Syllables per second */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[0.8rem] font-medium text-text-secondary min-h-[1.25rem]">Sprechtempo (Silben/s)</label>
                <input type="number" min="1" max="20" step="0.5"
                  value={gptParams.syllables_per_second}
                  onChange={e => setGptParams({ ...gptParams, syllables_per_second: parseFloat(e.target.value) })}
                  className={selectCls} />
              </div>
          </div>
        </div>
      </div>
      )}
          {activeTab === 'tts' && (
            <div className="bg-bg-card border border-border-subtle rounded-xl p-5 backdrop-blur-md">
                <p className="text-sm font-semibold text-text-secondary uppercase tracking-wider mb-3.5">Einstellungen</p>
                <div className="flex flex-col gap-4 max-w-xl">
                    <div className="flex flex-col gap-1.5">
                        <label className="text-sm font-medium text-text-primary">OpenAI API-Key (Optional wenn im Backend gesetzt)</label>
                        <input
                            type="password"
                            value={ttsParams.apiKey}
                            onChange={(e) => setTtsParams({ ...ttsParams, apiKey: e.target.value })}
                            className={inputCls}
                            placeholder="sk-..."
                        />
                    </div>

                    <div className="flex flex-col gap-1.5">
                        <label className="text-sm font-medium text-text-primary">Stimme</label>
                        <select
                            value={ttsParams.voice}
                            onChange={(e) => setTtsParams({ ...ttsParams, voice: e.target.value })}
                            className={selectCls}
                        >
                            <option value="alloy">Alloy (Männlich, neutral)</option>
                            <option value="echo">Echo (Männlich, warm)</option>
                            <option value="fable">Fable (Männlich, erzählend)</option>
                            <option value="onyx">Onyx (Männlich, tief)</option>
                            <option value="nova">Nova (Weiblich, lebhaft)</option>
                            <option value="shimmer">Shimmer (Weiblich, ruhig)</option>
                        </select>
                    </div>

                    <div className="flex flex-col gap-1.5">
                        <label className="text-sm font-medium text-text-primary">Hintergrund-Lautstärke (0.0 - 1.0)</label>
                        <input
                            type="number"
                            step="0.1"
                            min="0"
                            max="1"
                            value={ttsParams.duckingVolume}
                            onChange={(e) => setTtsParams({ ...ttsParams, duckingVolume: e.target.value })}
                            className={inputCls}
                        />
                        <p className="text-[0.75rem] text-text-muted">Die Originaltonspur wird während der gesamten Wiedergabe auf diesen Wert reduziert.</p>
                    </div>
                </div>
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border-subtle shrink-0 flex justify-end">
          <button
            className="px-6 py-2 bg-violet-500 hover:bg-violet-600 transition-all rounded-lg text-white font-medium"
            onClick={() => setIsConfigModalOpen(false)}
          >
            Schließen & Übernehmen
          </button>
        </div>

      </div>
    </div>
  );
}
