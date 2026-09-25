//! vad.rs — Silero VAD ONNX inference
//! Classifies each 512-sample audio frame as speech or silence.
//! Model: silero_vad.onnx (~1.8MB), runs on CPU via ort.

use anyhow::{Context, Result};
use ndarray::{Array1, Array2, Array3};
use ort::session::Session;
use ort::session::builder::GraphOptimizationLevel;
use std::path::PathBuf;
use tracing::debug;

pub const VAD_THRESHOLD: f32 = 0.5;
pub const VAD_FRAME_SIZE: usize = 512; // samples at 16kHz = 32ms

pub struct SileroVAD {
    session: Session,
    /// Internal state tensors required by Silero VAD (h, c)
    h: Array3<f32>, // [2, 1, 64]
    c: Array3<f32>, // [2, 1, 64]
    sample_rate: i64,
}

impl SileroVAD {
    /// Create a new Silero VAD instance.
    /// Looks for `silero_vad.onnx` in the models directory.
    pub fn new() -> Result<Self> {
        let model_path = Self::find_model_path();

        if !model_path.exists() {
            anyhow::bail!(
                "Silero VAD model not found at {:?}. Run the model download script first.",
                model_path
            );
        }

        let session = Session::builder()
            .map_err(|e| anyhow::anyhow!("Failed to create ONNX session builder: {e}"))?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|e| anyhow::anyhow!("Failed to set optimization level: {e}"))?
            .commit_from_file(&model_path)
            .map_err(|e| anyhow::anyhow!("Failed to load Silero VAD model: {e}"))?;

        tracing::info!("✅ Silero VAD loaded from {:?}", model_path);

        Ok(Self {
            session,
            h: Array3::zeros((2, 1, 64)),
            c: Array3::zeros((2, 1, 64)),
            sample_rate: 16000,
        })
    }

    /// Classify a 512-sample audio frame.
    /// Returns speech probability (0.0 = silence, 1.0 = speech).
    pub fn is_speech(&mut self, samples: &[f32]) -> Result<f32> {
        if samples.len() < VAD_FRAME_SIZE {
            return Ok(0.0); // insufficient data = treat as silence
        }

        let chunk = &samples[..VAD_FRAME_SIZE];
        let input = Array2::from_shape_vec((1, VAD_FRAME_SIZE), chunk.to_vec())
            .context("Failed to create input tensor")?;

        let sr = Array1::from_vec(vec![self.sample_rate]);

        let input_val = ort::value::Value::from_array(input)
            .context("Failed to create input tensor")?;
        let sr_val = ort::value::Value::from_array(sr)
            .context("Failed to create sr tensor")?;
        let h_val = ort::value::Value::from_array(self.h.clone())
            .context("Failed to create h tensor")?;
        let c_val = ort::value::Value::from_array(self.c.clone())
            .context("Failed to create c tensor")?;

        use ort::inputs;
        let outputs = self
            .session
            .run(inputs![
                "input" => &input_val,
                "sr" => &sr_val,
                "h" => &h_val,
                "c" => &c_val,
            ])
            .context("Silero VAD inference failed")?;

        let prob = if let Ok((_, data)) = outputs["output"].try_extract_tensor::<f32>() {
            data.first().copied().unwrap_or(0.0)
        } else {
            0.0
        };

        // Update stateful h,c tensors
        if let Ok((_, data)) = outputs["hn"].try_extract_tensor::<f32>() {
            if let Ok(arr) = Array3::from_shape_vec((2, 1, 64), data.to_vec()) {
                self.h = arr;
            }
        }
        if let Ok((_, data)) = outputs["cn"].try_extract_tensor::<f32>() {
            if let Ok(arr) = Array3::from_shape_vec((2, 1, 64), data.to_vec()) {
                self.c = arr;
            }
        }

        debug!("VAD probability: {:.3}", prob);
        Ok(prob)
    }

    /// Reset internal VAD state (call between utterances)
    pub fn reset_state(&mut self) {
        self.h = Array3::zeros((2, 1, 64));
        self.c = Array3::zeros((2, 1, 64));
    }

    fn find_model_path() -> PathBuf {
        let candidates = [
            PathBuf::from("models/silero_vad.onnx"),
            PathBuf::from("../models/silero_vad.onnx"),
            PathBuf::from("../../models/silero_vad.onnx"),
        ];
        for path in &candidates {
            if path.exists() {
                return path.clone();
            }
        }
        PathBuf::from("models/silero_vad.onnx")
    }
}

/// A mock VAD for testing — always returns the configured probability.
#[cfg(test)]
pub struct MockVAD {
    pub speech_probability: f32,
}

#[cfg(test)]
impl MockVAD {
    pub fn is_speech(&self, _samples: &[f32]) -> f32 {
        self.speech_probability
    }
}
