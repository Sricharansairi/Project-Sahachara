// MITRA Phase 1 — lib.rs
// Module declarations and Tauri app builder

pub mod audio;
pub mod auth;
pub mod biometrics;
pub mod commands;
pub mod db;
pub mod screen;
pub mod state;
pub mod wake_word;

use std::sync::Arc;
use tauri::Manager;
use tokio::sync::Mutex;
use tracing::info;

use crate::{
    audio::{aec::AecGate, capture::AudioCaptureEngine, ring_buffer::RingBuffer, tts_player::TtsPlayer, vad::SileroVAD},
    biometrics::voiceprint::VoiceprintEngine,
    db::store::MitraStore,
    state::machine::StateMachine,
    wake_word::detector::WakeWordDetector,
};

/// Shared application state across all Tauri commands and background tasks
pub struct AppState {
    pub store: Arc<Mutex<MitraStore>>,
    pub state_machine: Arc<Mutex<StateMachine>>,
    pub ring_buffer: Arc<Mutex<RingBuffer>>,
    pub vad: Arc<Mutex<SileroVAD>>,
    pub voiceprint_engine: Arc<Mutex<VoiceprintEngine>>,
    pub wake_word_detector: Arc<Mutex<WakeWordDetector>>,
    // Phase 4: Voice pipeline
    pub tts_player: Arc<TtsPlayer>,
    pub aec_gate: Arc<AecGate>,
}

/// Tauri application entry point
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("mitra=debug,warn")),
        )
        .init();

    info!("🚀 MITRA starting — Project Sahachara Phase 1");

    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let app_handle = app.handle().clone();

            // Initialize encrypted database
            let db_path = app
                .path()
                .app_data_dir()
                .expect("Failed to resolve app data dir")
                .join("mitra.db");

            std::fs::create_dir_all(db_path.parent().unwrap())?;

            let encryption_key = commands::get_or_create_db_key()?;
            let mut store = MitraStore::open(&db_path, &encryption_key)
                .expect("Failed to open encrypted database");
            store.run_migrations().expect("DB migration failed");

            // Initialize shared components
            let ring_buffer = Arc::new(Mutex::new(RingBuffer::new(2.0, 16000)));
            let vad = Arc::new(Mutex::new(
                SileroVAD::new().expect("Failed to load Silero VAD model"),
            ));
            let voiceprint_engine = Arc::new(Mutex::new(
                VoiceprintEngine::new().expect("Failed to load voiceprint model"),
            ));
            let store = Arc::new(Mutex::new(store));
            let state_machine = Arc::new(Mutex::new(StateMachine::new(app_handle.clone())));
            let wake_word_detector = Arc::new(Mutex::new(WakeWordDetector::new(
                Arc::clone(&ring_buffer),
                Arc::clone(&voiceprint_engine),
                Arc::clone(&store),
            )));

            // Phase 4: AEC gate + TTS player
            let aec_gate = Arc::new(AecGate::new(200)); // 200ms re-arm delay
            let tts_player = Arc::new(TtsPlayer::new(Arc::clone(&aec_gate)));

            let app_state = AppState {
                store,
                state_machine: Arc::clone(&state_machine),
                ring_buffer: Arc::clone(&ring_buffer),
                vad: Arc::clone(&vad),
                voiceprint_engine: Arc::clone(&voiceprint_engine),
                wake_word_detector: Arc::clone(&wake_word_detector),
                tts_player: Arc::clone(&tts_player),
                aec_gate: Arc::clone(&aec_gate),
            };

            app.manage(app_state);

            // Start background audio capture on dedicated OS thread
            let ring_buffer_capture = Arc::clone(&ring_buffer);
            std::thread::Builder::new()
                .name("mitra-audio-capture".into())
                .spawn(move || {
                    match AudioCaptureEngine::start(ring_buffer_capture) {
                        Ok(_engine) => {
                            info!("✅ Audio capture engine running on dedicated thread");
                            loop {
                                std::thread::park();
                            }
                            #[allow(unreachable_code)]
                            drop(_engine);
                        }
                        Err(e) => {
                            tracing::error!("❌ Failed to start audio capture: {}", e);
                        }
                    }
                })
                .expect("Failed to spawn audio capture thread");

            // Start background wake word and VAD tick loop
            let app_handle_bg = app_handle.clone();
            tauri::async_runtime::spawn(async move {
                commands::start_background_audio_loop(app_handle_bg).await;
            });

            // Register Ctrl+Space global hotkey for manual wake
            use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
            let shortcut = Shortcut::new(Some(Modifiers::CONTROL), Code::Space);
            app.global_shortcut().on_shortcut(shortcut, move |_app, _shortcut, _event| {
                info!("Ctrl+Space: manual wake triggered");
                let sm = Arc::clone(&state_machine);
                tauri::async_runtime::spawn(async move {
                    let mut sm = sm.lock().await;
                    sm.transition(crate::state::machine::MitraEvent::ManualWake).await;
                });
            })?;

            info!("✅ MITRA initialized — entering IdleSleep");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_mitra_state,
            commands::manual_wake,
            commands::manual_sleep,
            commands::get_audio_level,
            commands::start_calibration,
            commands::record_calibration_prompt,
            commands::finish_calibration,
            commands::reset_voiceprint,
            commands::is_voiceprint_enrolled,
            commands::get_permission,
            commands::set_permission,
            commands::auth_start_flow,
            commands::auth_exchange_code,
            commands::auth_silent_refresh,
            commands::screen_set_shutter,
            commands::screen_capture_focused,
            // Phase 4: Voice pipeline
            commands::voice_transcribe,
            commands::voice_synthesize,
            commands::voice_pipeline_run,
            commands::aec_status,
            commands::voice_interrupt,
        ])
        .run(tauri::generate_context!())
        .expect("Error while running MITRA");
}
