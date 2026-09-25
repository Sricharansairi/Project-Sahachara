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
