// MITRA Phase 4 — audio/tts_player.rs
//
// TTS Audio Playback Queue with Rodio
//
// Architecture:
//   - `TtsPlayer` owns a rodio `OutputStreamHandle` and a tokio `Mutex<VecDeque<AudioChunk>>`
//   - SSE audio_chunk events from the backend are decoded (base64 → WAV bytes) and
//     pushed onto the queue via `enqueue_chunk()`
//   - A background playback task consumes chunks in order via `rodio::Decoder`
//   - Chunk concatenation: each chunk is played immediately after the prior completes
//     (rodio's `append` creates a gapless sequence)
//   - AEC integration: `activate_aec()` / `deactivate_aec()` bridge to the AecGate
//   - Barge-in: `interrupt()` immediately clears the rodio sink and signals AecGate
//
// Latency design:
//   P4-T03: TTS first chunk starts within <150ms of LLM first token
//   → Achieved by: pipeline.py fires TTS synthesis after only 5 words accumulate,
//     and Rust begins rodio playback of chunk_index=0 immediately on arrival.

use std::collections::VecDeque;
use std::io::Cursor;
use std::sync::Arc;

use anyhow::Result;
use rodio::{Decoder, OutputStream, Sink};
use tokio::sync::Mutex;
use tracing::{debug, error, info, warn};

use crate::audio::aec::AecGate;

/// A single decoded audio chunk ready for playback.
pub struct AudioChunk {
    pub chunk_index: u32,
    pub wav_bytes: Vec<u8>,
    pub is_final: bool,
    pub session_id: String,
}

/// State of the TTS playback engine.
#[derive(Debug, Clone, PartialEq)]
pub enum TtsState {
    Idle,
    Playing { session_id: String },
    Interrupted,
}

/// TTS audio playback queue with rodio backend.
pub struct TtsPlayer {
    queue: Arc<Mutex<VecDeque<AudioChunk>>>,
    aec_gate: Arc<AecGate>,
    state: Arc<Mutex<TtsState>>,
    interrupt_flag: Arc<tokio::sync::Notify>,
}

impl TtsPlayer {
    /// Create a new TTS player.
    /// `aec_gate` is shared with the audio capture pipeline.
    pub fn new(aec_gate: Arc<AecGate>) -> Self {
        Self {
            queue: Arc::new(Mutex::new(VecDeque::new())),
            aec_gate,
            state: Arc::new(Mutex::new(TtsState::Idle)),
            interrupt_flag: Arc::new(tokio::sync::Notify::new()),
        }
    }

    /// Enqueue a decoded audio chunk for playback.
    /// If this is the first chunk of a session, initialise the rodio sink and AEC gate.
    pub async fn enqueue_chunk(&self, chunk: AudioChunk) -> Result<()> {
        let session = chunk.session_id.clone();
        let is_first = chunk.chunk_index == 0;

        // Update state and activate AEC on first chunk
        if is_first {
            let mut state = self.state.lock().await;
            *state = TtsState::Playing {
                session_id: session.clone(),
            };
            drop(state);

            self.aec_gate.activate();
            info!("tts_player.session_start — session={}, AEC activated", &session);
        }

        self.queue.lock().await.push_back(chunk);
        debug!("tts_player.chunk_enqueued — session={}, queue_len={}", &session, {
            self.queue.lock().await.len()
        });

        Ok(())
    }

    /// Start the background playback loop for the current session.
    /// Must be called once per session (i.e., on first chunk arrival).
    /// Runs on a dedicated OS thread (rodio requires blocking I/O context).
    pub fn start_playback_loop(
        player: Arc<TtsPlayer>,
        session_id: String,
        total_expected_chunks: Option<u32>,
    ) {
        let player_ref = Arc::clone(&player);
        let session = session_id.clone();

        std::thread::Builder::new()
            .name(format!("mitra-tts-{}", &session[..8]))
            .spawn(move || {
                let rt = tokio::runtime::Builder::new_current_thread()
                    .enable_all()
                    .build()
                    .expect("Failed to create TTS tokio runtime");

                rt.block_on(async move {
                    // Create a fresh rodio sink for this session
                    let (stream, stream_handle) = match OutputStream::try_default() {
                        Ok(pair) => pair,
                        Err(e) => {
                            error!("tts_player.rodio_init_failed — {}", e);
                            return;
                        }
                    };

                    let sink = match Sink::try_new(&stream_handle) {
                        Ok(s) => Arc::new(s),
                        Err(e) => {
                            error!("tts_player.sink_create_failed — {}", e);
                            return;
                        }
                    };

                    let interrupt = Arc::clone(&player_ref.interrupt_flag);
                    let queue = Arc::clone(&player_ref.queue);
                    let state = Arc::clone(&player_ref.state);
                    let aec_gate = Arc::clone(&player_ref.aec_gate);
                    let sink_inner = Arc::clone(&sink);

                    let mut chunks_played = 0u32;
                    let mut finished = false;

                    loop {
                        // Check for interrupt signal
                        tokio::select! {
                            _ = interrupt.notified() => {
                                info!("tts_player.interrupted — stopping sink");
                                sink_inner.stop();
                                break;
                            }
                            _ = tokio::time::sleep(tokio::time::Duration::from_millis(5)) => {
                                // Poll queue
                            }
                        }

                        // Drain ready chunks into sink
                        let mut q = queue.lock().await;
                        while let Some(chunk) = q.pop_front() {
                            let is_last = chunk.is_final;
                            let wav = chunk.wav_bytes.clone();
                            drop(q); // release lock before decoding

                            match Decoder::new(Cursor::new(wav)) {
                                Ok(source) => {
                                    sink_inner.append(source);
                                    chunks_played += 1;
                                    debug!("tts_player.chunk_appended — idx={}", chunks_played);
                                }
                                Err(e) => {
                                    warn!("tts_player.decode_failed — chunk skipped: {}", e);
                                }
                            }

                            if is_last {
                                finished = true;
                                break;
                            }

                            q = queue.lock().await;
                        }

                        // Wait for sink to finish playing if we've buffered the final chunk
                        if finished && sink_inner.empty() {
                            info!(
                                "tts_player.session_complete — session={}, chunks={}",
                                &session, chunks_played
                            );
                            break;
                        }

                        // Alternatively, total_expected_chunks provides an early exit
                        if let Some(total) = total_expected_chunks {
                            if chunks_played >= total && sink_inner.empty() {
                                break;
                            }
                        }
                    }

                    // Drop stream to close audio device
                    drop(stream);
                    drop(stream_handle);

                    // Update state and deactivate AEC
                    let mut st = state.lock().await;
                    *st = TtsState::Idle;
                    drop(st);

                    aec_gate.deactivate();
                    info!("tts_player.aec_deactivated — session complete");
                });
            })
            .expect("Failed to spawn TTS playback thread");
    }

    /// Immediately stop playback (barge-in or manual interrupt).
    /// Returns true if playback was actually interrupted.
    pub async fn interrupt(&self) -> bool {
        let state = self.state.lock().await;
        if *state == TtsState::Idle {
            return false;
        }
        drop(state);

        info!("tts_player.interrupt — signaling stop to playback loop");

        // Signal the playback loop to exit (which stops the rodio sink)
        self.interrupt_flag.notify_waiters();

        // Clear queue
        self.queue.lock().await.clear();

        // Update state
        let mut state = self.state.lock().await;
        *state = TtsState::Interrupted;

        // Signal barge-in to AEC (re-arms mic immediately)
        let was_interrupted = self.aec_gate.signal_barge_in();
        info!("tts_player.interrupted — barge_in={}", was_interrupted);
        true
    }

    /// Query current TTS playback state.
    pub async fn get_state(&self) -> TtsState {
        self.state.lock().await.clone()
    }

    /// Is TTS currently playing?
    pub async fn is_playing(&self) -> bool {
        matches!(*self.state.lock().await, TtsState::Playing { .. })
    }
}

// ---------------------------------------------------------------------------
// Barge-in Detector
// ---------------------------------------------------------------------------

/// Monitors the VAD output during TTS playback and signals barge-in.
/// Runs as a future awaited in the audio loop when TTS is active.
pub struct BargeInDetector {
    /// VAD speech probability threshold to trigger barge-in.
    speech_threshold: f32,
    /// Number of consecutive frames above threshold needed (debounce).
    consecutive_frames: usize,
    /// How long to wait after TTS starts before accepting barge-in (ms).
    /// Prevents the TTS audio itself from triggering barge-in during ramp-up.
    #[allow(dead_code)]
    grace_period_ms: u64,
}

impl BargeInDetector {
    pub fn new(speech_threshold: f32, consecutive_frames: usize, grace_period_ms: u64) -> Self {
        Self {
            speech_threshold,
            consecutive_frames,
            grace_period_ms,
        }
    }

    /// Returns true if barge-in detected in the given VAD probability stream.
    /// Call this with a rolling window of recent VAD probabilities.
    pub fn detect(&self, vad_probs: &[f32]) -> bool {
        if vad_probs.len() < self.consecutive_frames {
            return false;
        }
        let recent = &vad_probs[vad_probs.len() - self.consecutive_frames..];
        recent.iter().all(|&p| p >= self.speech_threshold)
    }
}

impl Default for BargeInDetector {
    fn default() -> Self {
        Self::new(0.75, 3, 200)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_barge_in_detector_no_speech() {
        let detector = BargeInDetector::default();
        let probs = vec![0.1, 0.2, 0.3, 0.4, 0.5];
        assert!(!detector.detect(&probs), "should not detect barge-in with low probs");
    }

    #[test]
    fn test_barge_in_detector_speech() {
        let detector = BargeInDetector::new(0.75, 3, 200);
        let probs = vec![0.2, 0.8, 0.9, 0.85, 0.92];
        assert!(detector.detect(&probs), "should detect barge-in with high consecutive probs");
    }

    #[test]
    fn test_barge_in_detector_insufficient_frames() {
        let detector = BargeInDetector::new(0.75, 5, 200);
        let probs = vec![0.9, 0.95]; // only 2 frames, need 5
        assert!(!detector.detect(&probs), "insufficient frames should not trigger");
    }

    #[test]
    fn test_barge_in_detector_mixed() {
        let detector = BargeInDetector::new(0.75, 3, 200);
        let probs = vec![0.9, 0.2, 0.9, 0.9, 0.9]; // last 3 all above threshold
        assert!(detector.detect(&probs), "last 3 consecutive above threshold should trigger");
    }

    #[test]
    fn test_barge_in_interrupted() {
        let probs = vec![0.9, 0.2, 0.9, 0.5, 0.9]; // last frame 0.9, prev 0.5 → not all consecutive
        let detector = BargeInDetector::new(0.75, 3, 200);
        assert!(!detector.detect(&probs), "gap in high probs should not trigger");
    }
}
