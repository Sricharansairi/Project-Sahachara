//! commands.rs — Tauri IPC commands exposed to React frontend
//! Also contains the background audio capture + wake word loop.

use anyhow::Result;
use tauri::{Emitter, Manager, State};
use tracing::info;

use crate::{
    biometrics::voiceprint::VoiceprintEngine,
    state::machine::MitraEvent,
    AppState,
};

// ─────────────────────────────────────────────────────────────────────────────
// Database encryption key management
// ─────────────────────────────────────────────────────────────────────────────

/// Get or create the database encryption key from Windows Credential Locker.
pub fn get_or_create_db_key() -> Result<String> {
    let entry = keyring::Entry::new("com.sahachara.mitra", "db_encryption_key")?;
    match entry.get_password() {
        Ok(key) => {
            info!("🔑 DB encryption key loaded from Credential Locker");
            Ok(key)
        }
        Err(_) => {
            // First run: generate and store a new key
            let key = uuid::Uuid::new_v4().to_string().replace('-', "");
            entry.set_password(&key)?;
            info!("🔑 New DB encryption key generated and stored in Credential Locker");
            Ok(key)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Background audio loop
// ─────────────────────────────────────────────────────────────────────────────

/// Background task: starts audio capture and runs the VAD + wake word detection loop.
pub async fn start_background_audio_loop(app_handle: tauri::AppHandle) {
    info!("🎙️ Background audio loop starting...");

    let state = app_handle.state::<AppState>();

    // Main processing loop: runs every 80ms
    let mut interval = tokio::time::interval(tokio::time::Duration::from_millis(80));
    let mut prev_speech = false;

    loop {
        interval.tick().await;

        // Tick the state machine (handles VAD endpoint timer + keep-alive timer)
        {
            let mut sm = state.state_machine.lock().await;
            sm.tick().await;
        }

        // Get current audio frame from ring buffer
        let frame = {
            let rb = state.ring_buffer.lock().await;
            rb.get_last_n_seconds(0.08, 16000) // last 80ms
        };

        if frame.is_empty() {
            continue;
        }

        // Emit audio level to frontend (every loop iteration)
        {
            let rb = state.ring_buffer.lock().await;
            let level = rb.current_level;
            let _ = app_handle.emit("audio-level-update", serde_json::json!({"level": level}));
        }

        // Check if state machine is in idle sleep → only run wake word detection
        let current_state = {
            let sm = state.state_machine.lock().await;
            sm.state.clone()
        };

        match current_state {
            crate::state::machine::MitraState::IdleSleep => {
                // Run wake word detector
                let wake_event = {
                    let mut detector = state.wake_word_detector.lock().await;
                    detector.process_frame(&frame).await
                };

                if let Some(event) = wake_event {
                    let _ = app_handle.emit("wake-word-detected", &event);
                    let mut sm = state.state_machine.lock().await;
                    sm.transition(MitraEvent::WakeWordDetected).await;
                }
            }

            crate::state::machine::MitraState::ActiveListening
            | crate::state::machine::MitraState::UserSpeaking
            | crate::state::machine::MitraState::VADEndpointing
            | crate::state::machine::MitraState::ConversationalKeepAlive => {
                // Run VAD on incoming audio
                let speech_prob = {
                    let mut vad = state.vad.lock().await;
                    vad.is_speech(&frame).unwrap_or(0.0)
                };

                let is_speech = speech_prob >= crate::audio::vad::VAD_THRESHOLD;

                if is_speech && !prev_speech {
                    // Speech onset
                    let mut sm = state.state_machine.lock().await;
                    sm.transition(MitraEvent::SpeechDetected).await;
                } else if !is_speech && prev_speech {
                    // Speech offset
                    let mut sm = state.state_machine.lock().await;
                    sm.transition(MitraEvent::SilenceDetected).await;
                }

                prev_speech = is_speech;
            }

            crate::state::machine::MitraState::DeepProcessing => {
                // In Phase 1, simulate processing and immediately fire a "response ready"
                // Phase 2+ will wire the real LLM here
                tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                let mut sm = state.state_machine.lock().await;
                sm.transition(MitraEvent::ResponseReady).await;
                // Immediately simulate playback done (no TTS in Phase 1)
                tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
                sm.transition(MitraEvent::PlaybackDone).await;
            }

            _ => {}
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tauri IPC Commands
// ─────────────────────────────────────────────────────────────────────────────

/// Get the current MITRA state.
#[tauri::command]
pub async fn get_mitra_state(state: State<'_, AppState>) -> Result<String, String> {
    let sm = state.state_machine.lock().await;
    Ok(format!("{:?}", sm.state))
}

/// Manually wake MITRA (same as saying the wake word).
#[tauri::command]
pub async fn manual_wake(state: State<'_, AppState>) -> Result<(), String> {
    let mut sm = state.state_machine.lock().await;
    sm.transition(MitraEvent::ManualWake).await;
    Ok(())
}

/// Manually put MITRA to sleep.
#[tauri::command]
pub async fn manual_sleep(state: State<'_, AppState>) -> Result<(), String> {
    let mut sm = state.state_machine.lock().await;
    sm.transition(MitraEvent::ManualSleep).await;
    Ok(())
}

/// Get the current audio input level (RMS, 0.0–1.0).
#[tauri::command]
pub async fn get_audio_level(state: State<'_, AppState>) -> Result<f32, String> {
    let rb = state.ring_buffer.lock().await;
    Ok(rb.current_level)
}

/// Start the 3-prompt voiceprint calibration flow.
#[tauri::command]
pub async fn start_calibration(state: State<'_, AppState>) -> Result<(), String> {
    let store = state.store.lock().await;
    store
        .clear_calibration_prompts()
        .map_err(|e| e.to_string())?;

    let mut ve = state.voiceprint_engine.lock().await;
    ve.calibration.clear();

    info!("🎙️ Calibration started — 3 prompts required");
    Ok(())
}

/// Record a single calibration prompt (called 3 times).
/// `prompt_index`: 0, 1, or 2.
#[tauri::command]
pub async fn record_calibration_prompt(
    prompt_index: u8,
    state: State<'_, AppState>,
) -> Result<String, String> {
    if prompt_index > 2 {
        return Err("prompt_index must be 0, 1, or 2".to_string());
    }

    // Capture 3 seconds of audio from ring buffer
    let samples = {
        let rb = state.ring_buffer.lock().await;
        rb.get_last_n_seconds(3.0, 16000)
    };

    if samples.len() < crate::biometrics::voiceprint::MIN_SAMPLES_FOR_EMBED {
        return Err(format!(
            "Not enough audio: {} samples (need at least {})",
            samples.len(),
            crate::biometrics::voiceprint::MIN_SAMPLES_FOR_EMBED
        ));
    }

    // Save to DB
    {
        let store = state.store.lock().await;
        store
            .save_calibration_prompt(prompt_index, &samples)
            .map_err(|e| e.to_string())?;
    }

    // Add to in-memory calibration buffer
    {
        let mut ve = state.voiceprint_engine.lock().await;
        ve.calibration.add_prompt(samples);
        info!(
            "✅ Calibration prompt {} recorded ({}/3)",
            prompt_index,
            ve.calibration.prompts.len()
        );
    }

    let prompts = {
        let ve = state.voiceprint_engine.lock().await;
        ve.calibration.prompts.len()
    };

    Ok(format!("{}/3 prompts recorded", prompts))
}

/// Finalize calibration: average the 3 embeddings and save the voiceprint.
#[tauri::command]
pub async fn finish_calibration(state: State<'_, AppState>) -> Result<(), String> {
    let embeddings = {
        let mut ve = state.voiceprint_engine.lock().await;
        if !ve.calibration.is_complete() {
            return Err("Calibration requires 3 prompts. Not yet complete.".to_string());
        }

        // Compute embeddings for each prompt
        let mut embeddings = Vec::new();
        let prompts = ve.calibration.prompts.clone();
        for samples in &prompts {
            let emb = ve.embed(samples).map_err(|e| e.to_string())?;
            embeddings.push(emb);
        }
        ve.calibration.clear();
        embeddings
    };

    // Average the embeddings
    let avg = VoiceprintEngine::average_embeddings(&embeddings);

    // Save to DB
    {
        let store = state.store.lock().await;
        store.save_voiceprint(&avg).map_err(|e| e.to_string())?;
        store.clear_calibration_prompts().map_err(|e| e.to_string())?;
    }

    info!("✅ Voiceprint calibration complete — voiceprint enrolled");
    Ok(())
}

/// Clear the stored voiceprint (requires re-enrollment).
#[tauri::command]
pub async fn reset_voiceprint(state: State<'_, AppState>) -> Result<(), String> {
    let store = state.store.lock().await;
    store.clear_voiceprint().map_err(|e| e.to_string())?;
    info!("🗑️  Voiceprint reset by user");
    Ok(())
}

/// Returns whether the user has enrolled their voiceprint.
#[tauri::command]
pub async fn is_voiceprint_enrolled(state: State<'_, AppState>) -> Result<bool, String> {
    let store = state.store.lock().await;
    Ok(store.is_voiceprint_enrolled())
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 3: Permissions & Screen Capture & Auth Commands
// ─────────────────────────────────────────────────────────────────────────────

#[tauri::command]
pub async fn get_permission(state: State<'_, AppState>, name: String) -> Result<bool, String> {
    let store = state.store.lock().await;
    store.get_permission(&name).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn set_permission(
    state: State<'_, AppState>,
    name: String,
    granted: bool,
) -> Result<(), String> {
    let store = state.store.lock().await;
    store.set_permission(&name, granted).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn auth_start_flow(provider: String) -> Result<(String, String), String> {
    let prov = match provider.to_lowercase().as_str() {
        "google" => crate::auth::OAuthProvider::Google,
        "microsoft365" | "microsoft" | "ms365" => crate::auth::OAuthProvider::Microsoft365,
        "apple" => crate::auth::OAuthProvider::Apple,
        _ => return Err(format!("Unsupported provider: {}", provider)),
    };
    let storage = std::sync::Arc::new(crate::auth::KeyringTokenStorage::new());
    let manager = crate::auth::OAuthManager::new(storage);
    Ok(manager.start_flow(prov))
}

#[tauri::command]
pub async fn auth_exchange_code(
    state: String,
    code: String,
) -> Result<crate::auth::TokenBundle, String> {
    let storage = std::sync::Arc::new(crate::auth::KeyringTokenStorage::new());
    let manager = crate::auth::OAuthManager::new(storage);
    manager.exchange_code(&state, &code).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn auth_silent_refresh(provider: String) -> Result<crate::auth::TokenBundle, String> {
    let prov = match provider.to_lowercase().as_str() {
        "google" => crate::auth::OAuthProvider::Google,
        "microsoft365" | "microsoft" | "ms365" => crate::auth::OAuthProvider::Microsoft365,
        "apple" => crate::auth::OAuthProvider::Apple,
        _ => return Err(format!("Unsupported provider: {}", provider)),
    };
    let storage = std::sync::Arc::new(crate::auth::KeyringTokenStorage::new());
    let manager = crate::auth::OAuthManager::new(storage);
    manager.get_valid_token(prov).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn screen_set_shutter(active: bool) -> Result<(), String> {
    let win_mgr = std::sync::Arc::new(crate::screen::WindowManager::new().with_mock_displays());
    let engine = crate::screen::ScreenCaptureEngine::new(win_mgr);
    engine.set_on_demand_shutter(active);
    Ok(())
}

#[tauri::command]
pub async fn screen_capture_focused() -> Result<crate::screen::CapturePayload, String> {
    let win_mgr = std::sync::Arc::new(crate::screen::WindowManager::new().with_mock_displays());
    let engine = crate::screen::ScreenCaptureEngine::new(win_mgr);
    engine.set_on_demand_shutter(true);
    engine.capture_focused_window(None).map_err(|e| e.to_string())
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 4: Voice Pipeline IPC Commands
// ─────────────────────────────────────────────────────────────────────────────

/// Relay a raw audio buffer (base64 WAV) to the backend STT endpoint.
/// Returns the transcript string.
/// The Rust side handles: base64 encode → POST /api/v1/voice/transcribe → return transcript.
#[tauri::command]
pub async fn voice_transcribe(
    state: State<'_, AppState>,
    audio_b64: String,
    sample_rate: u32,
) -> Result<serde_json::Value, String> {
    let url = "http://127.0.0.1:8766/api/v1/voice/transcribe";

    let body = serde_json::json!({
        "audio_b64": audio_b64,
        "sample_rate": sample_rate,
        "channels": 1,
        "language": "en",
    });

    let client = reqwest::Client::new();
    let resp = client
        .post(url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("STT request failed: {}", e))?;

    let json: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("STT response parse failed: {}", e))?;

    info!("voice_transcribe — transcript={:?}", json.get("transcript"));
    let _ = state; // accessed to validate state is available
    Ok(json)
}

/// Synthesize text → audio via backend TTS endpoint.
/// Returns base64-encoded WAV audio bytes.
#[tauri::command]
pub async fn voice_synthesize(
    state: State<'_, AppState>,
    text: String,
    voice: Option<String>,
    speed: Option<f32>,
) -> Result<serde_json::Value, String> {
    let url = "http://127.0.0.1:8766/api/v1/tts/synthesize";

    let body = serde_json::json!({
        "text": text,
        "voice": voice.unwrap_or_else(|| "af_bella".to_string()),
        "speed": speed.unwrap_or(1.0),
    });

    let client = reqwest::Client::new();
    let resp = client
        .post(url)
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("TTS request failed: {}", e))?;

    let json: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("TTS response parse failed: {}", e))?;

    info!("voice_synthesize — latency_ms={:?}", json.get("latency_ms"));
    let _ = state;
    Ok(json)
}

/// Run the full voice pipeline (STT→LLM→TTS) for a captured audio buffer.
/// Returns session metadata + first latency profile.
/// Real-time SSE chunks are delivered via the EventSource opened by the frontend.
#[tauri::command]
pub async fn voice_pipeline_run(
    state: State<'_, AppState>,
    audio_b64: String,
    conversation_id: Option<String>,
    screen_payload: Option<String>,
) -> Result<serde_json::Value, String> {
    let url = "http://127.0.0.1:8766/api/v1/voice/pipeline";

    let body = serde_json::json!({
        "audio_b64": audio_b64,
        "sample_rate": 16000,
        "conversation_id": conversation_id.unwrap_or_else(|| uuid::Uuid::new_v4().to_string()),
        "screen_payload": screen_payload.unwrap_or_default(),
        "voice": "af_bella",
        "tts_speed": 1.0,
        "enable_tts": true,
    });

    let client = reqwest::Client::new();
    let resp = client
        .post(url)
        .json(&body)
        .timeout(std::time::Duration::from_secs(60))
        .send()
        .await
        .map_err(|e| format!("Pipeline request failed: {}", e))?;

    let json: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("Pipeline response parse failed: {}", e))?;

    info!(
        "voice_pipeline_run — session={:?}, total_ms={:?}",
        json.get("session_id"),
        json.pointer("/latency/total_ms")
    );
    let _ = state;
    Ok(json)
}

/// Query AEC gate status (for frontend privacy ring display).
#[tauri::command]
pub async fn aec_status(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    // TtsPlayer stores AecGate state; here we check via the AppState tts_player field
    // (added in lib.rs Phase 4 update). Gracefully handle if not yet initialized.
    let is_muted = state.aec_gate.is_muted();
    let tts_playing = state.tts_player.is_playing().await;

    Ok(serde_json::json!({
        "aec_active": is_muted,
        "tts_playing": tts_playing,
    }))
}

/// Interrupt current TTS playback (barge-in from frontend).
#[tauri::command]
pub async fn voice_interrupt(state: State<'_, AppState>) -> Result<bool, String> {
    let interrupted = state.tts_player.interrupt().await;
    info!("voice_interrupt — result={}", interrupted);
    Ok(interrupted)
}

