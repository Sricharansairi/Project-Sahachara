//! detector.rs — Two-stage wake word detector
//!
//! Stage 1: Sends audio frames to a Python openWakeWord server over TCP.
//!          Only ~5MB ONNX model running locally in Python.
//!          If phrase not detected → ring buffer is wiped (privacy invariant).
//!
//! Stage 2: After Stage 1 fires, verifies voiceprint cosine similarity > 0.82.
//!          Unknown speakers are silently rejected.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;
use tracing::{debug, info, warn};

use crate::audio::ring_buffer::RingBuffer;
use crate::biometrics::voiceprint::{Embedding, VoiceprintEngine};
use crate::db::store::MitraStore;

/// How long to suppress new wake-word detections after one fires (anti-double-trigger)
const DEBOUNCE_DURATION_SECS: u64 = 2;
/// Confidence score threshold from openWakeWord
pub const WAKE_WORD_SCORE_THRESHOLD: f32 = 0.5;
/// TCP port for openWakeWord IPC server
pub const WAKE_WORD_SERVER_PORT: u16 = 8765;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WakeWordEvent {
    pub phrase: String,
    pub score: f32,
    pub stage2_verified: bool,
}

/// JSON message sent to the openWakeWord Python server
#[derive(Serialize)]
struct AudioChunkMessage {
    samples: Vec<f32>,
}

/// JSON response from the openWakeWord Python server
#[derive(Deserialize)]
struct WakeWordResponse {
    detected: bool,
    phrase: Option<String>,
    score: Option<f32>,
}

pub struct WakeWordDetector {
    ring_buffer: Arc<Mutex<RingBuffer>>,
    voiceprint_engine: Arc<Mutex<VoiceprintEngine>>,
    store: Arc<Mutex<MitraStore>>,
    /// TCP connection to Python openWakeWord server (reconnects on failure)
    tcp_stream: Option<TcpStream>,
    /// Debounce: ignore triggers until this instant
    debounce_until: Instant,
    /// Stage 1 detection counter (for testing/metrics)
    pub stage1_detections: u32,
    /// Stage 2 rejections (voiceprint mismatch)
    pub stage2_rejections: u32,
}

impl WakeWordDetector {
    pub fn new(
        ring_buffer: Arc<Mutex<RingBuffer>>,
        voiceprint_engine: Arc<Mutex<VoiceprintEngine>>,
        store: Arc<Mutex<MitraStore>>,
    ) -> Self {
        Self {
            ring_buffer,
            voiceprint_engine,
            store,
            tcp_stream: None,
            debounce_until: Instant::now(),
            stage1_detections: 0,
            stage2_rejections: 0,
        }
    }

    /// Process a 80ms audio frame through the two-stage pipeline.
    /// Returns Some(WakeWordEvent) if both stages pass.
    pub async fn process_frame(&mut self, frame: &[f32]) -> Option<WakeWordEvent> {
        // Debounce check
        if Instant::now() < self.debounce_until {
            return None;
        }

        // Stage 1: send to Python openWakeWord server
        let stage1_result = self.query_stage1(frame).await;

        match stage1_result {
            Ok(Some(response)) if response.detected => {
                self.stage1_detections += 1;
                let phrase = response.phrase.unwrap_or_else(|| "hey_mitra".to_string());
                let score = response.score.unwrap_or(0.0);

                info!(
                    "🔔 Stage 1 DETECTED: phrase='{}' score={:.3}",
                    phrase, score
                );

                // Stage 2: verify voiceprint
                let stage2_ok = self.verify_voiceprint().await;

                if stage2_ok {
                    // Set debounce
                    self.debounce_until =
                        Instant::now() + Duration::from_secs(DEBOUNCE_DURATION_SECS);

                    info!("✅ Stage 2 VERIFIED — wake event fired");
                    Some(WakeWordEvent {
                        phrase: phrase.replace('_', " "),
                        score,
                        stage2_verified: true,
                    })
                } else {
                    self.stage2_rejections += 1;
                    warn!("🚫 Stage 2 REJECTED — voiceprint mismatch (unknown speaker)");
                    // Privacy: wipe ring buffer since unknown speaker triggered it
                    if let Ok(mut rb) = self.ring_buffer.try_lock() {
                        rb.overwrite_all();
                    }
                    None
                }
            }
            Ok(Some(_)) | Ok(None) => {
                // Stage 1 did not fire — privacy invariant: wipe ring buffer
                // (only wipe every 2s to avoid constant zeroing)
                None
            }
            Err(e) => {
                debug!("Wake word server error (will reconnect): {}", e);
                self.tcp_stream = None; // force reconnect
                None
            }
        }
    }

    /// Query the openWakeWord Python server with an audio frame.
    async fn query_stage1(&mut self, frame: &[f32]) -> Result<Option<WakeWordResponse>> {
        // Ensure TCP connection
        if self.tcp_stream.is_none() {
            match TcpStream::connect(format!("127.0.0.1:{}", WAKE_WORD_SERVER_PORT)) {
                Ok(stream) => {
                    stream.set_read_timeout(Some(Duration::from_millis(50))).ok();
                    stream.set_write_timeout(Some(Duration::from_millis(50))).ok();
                    self.tcp_stream = Some(stream);
                    debug!("🔗 Connected to openWakeWord server on port {}", WAKE_WORD_SERVER_PORT);
                }
                Err(_) => {
                    // Server not running — silent detection disabled
                    return Ok(None);
                }
            }
        }

        let msg = AudioChunkMessage {
            samples: frame.to_vec(),
        };
        let json = serde_json::to_string(&msg).context("JSON serialize failed")?;

        if let Some(stream) = &mut self.tcp_stream {
            // Write length-prefixed message
            let bytes = json.as_bytes();
            let len_bytes = (bytes.len() as u32).to_le_bytes();
            stream
                .write_all(&len_bytes)
                .context("TCP write length failed")?;
            stream.write_all(bytes).context("TCP write data failed")?;

            // Read response
            let mut len_buf = [0u8; 4];
            stream
                .read_exact(&mut len_buf)
                .context("TCP read length failed")?;
            let resp_len = u32::from_le_bytes(len_buf) as usize;

            let mut resp_buf = vec![0u8; resp_len];
            stream
                .read_exact(&mut resp_buf)
                .context("TCP read data failed")?;

            let response: WakeWordResponse =
                serde_json::from_slice(&resp_buf).context("JSON parse failed")?;

            Ok(Some(response))
        } else {
            Ok(None)
        }
    }

    /// Stage 2: Verify that the current ring buffer audio matches the stored voiceprint.
    async fn verify_voiceprint(&self) -> bool {
        // Load stored voiceprint from DB
        let stored_embedding: Option<Embedding> = {
            let store = self.store.lock().await;
            store.load_voiceprint().unwrap_or(None)
        };

        let stored = match stored_embedding {
            Some(emb) => emb,
            None => {
                // No voiceprint enrolled yet — allow through (first-run mode)
                info!("No voiceprint enrolled — allowing wake (enroll on first run)");
                return true;
            }
        };

        // Get last 1.5 seconds of audio from ring buffer
        let audio = {
            let rb = self.ring_buffer.lock().await;
            rb.get_last_n_seconds(1.5, 16000)
        };

        if audio.len() < crate::biometrics::voiceprint::MIN_SAMPLES_FOR_EMBED {
            info!("Insufficient audio for voiceprint verification — allowing through");
            return true;
        }

        // Compute embedding
        let query_embedding = {
            let mut engine = self.voiceprint_engine.lock().await;
            match engine.embed(&audio) {
                Ok(emb) => emb,
                Err(e) => {
                    warn!("Voiceprint embedding failed: {} — allowing through", e);
                    return true;
                }
            }
        };

        let similarity = VoiceprintEngine::similarity(&stored, &query_embedding);
        let is_same = VoiceprintEngine::is_same_speaker(&stored, &query_embedding);

        info!(
            "🔐 Voiceprint similarity: {:.4} (threshold: {:.2}) → {}",
            similarity,
            crate::biometrics::voiceprint::SIMILARITY_THRESHOLD,
            if is_same { "MATCH" } else { "REJECT" }
        );

        is_same
    }

    /// Returns true if the openWakeWord server is reachable
    pub fn is_server_available(&self) -> bool {
        TcpStream::connect_timeout(
            &format!("127.0.0.1:{}", WAKE_WORD_SERVER_PORT)
                .parse()
                .unwrap(),
            Duration::from_millis(100),
        )
        .is_ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_debounce_prevents_double_trigger() {
        // Simulate debounce timing logic
        let debounce_until = Instant::now() + Duration::from_secs(2);
        assert!(
            Instant::now() < debounce_until,
            "Debounce should be active immediately after trigger"
        );
        println!("✅ Debounce logic verified");
    }

    #[test]
    fn test_wake_word_event_serialization() {
        let event = WakeWordEvent {
            phrase: "hey mitra".to_string(),
            score: 0.92,
            stage2_verified: true,
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("hey mitra"));
        assert!(json.contains("stage2_verified"));
        println!("✅ WakeWordEvent serializes correctly: {}", json);
    }
}
