//! capture.rs — cpal-based audio capture engine
//! Captures 16kHz mono audio in 20ms frames, feeds into shared RingBuffer.

use anyhow::{Context, Result};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, Stream, StreamConfig};
use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::{error, info, warn};

use crate::audio::ring_buffer::RingBuffer;

pub const SAMPLE_RATE: u32 = 16000;
pub const FRAME_SIZE: usize = 320; // 20ms at 16kHz

pub struct AudioCaptureEngine {
    _stream: Stream, // keep alive; dropped = stream stops
}

impl AudioCaptureEngine {
    /// Start capturing audio from the default input device.
    /// Frames are resampled to 16kHz mono and pushed into `ring_buffer`.
    pub fn start(ring_buffer: Arc<Mutex<RingBuffer>>) -> Result<Self> {
        let host = cpal::default_host();
        let device = host
            .default_input_device()
            .context("No audio input device found")?;

        let device_name = device.name().unwrap_or_else(|_| "unknown".to_string());
        info!("🎙️ Audio capture starting on device: {}", device_name);

        // Try to get a 16kHz mono config; fall back to default
        let (config, sample_format) = Self::find_16khz_config(&device).unwrap_or_else(|| {
            warn!("16kHz config not found, using device default (will resample)");
            let default_supported = device.default_input_config().expect("No default input config");
            let fmt = default_supported.sample_format();
            (default_supported.config(), fmt)
        });

        let device_sample_rate = config.sample_rate.0;
        let device_channels = config.channels as usize;

        info!(
            "Audio config: {} Hz, {} channels, {:?}",
            device_sample_rate,
            device_channels,
            sample_format
        );

        let stream = match sample_format {
            SampleFormat::F32 => Self::build_stream::<f32>(
                &device,
                &config,
                ring_buffer,
                device_sample_rate,
                device_channels,
            )?,
            SampleFormat::I16 => Self::build_stream_i16(
                &device,
                &config,
                ring_buffer,
                device_sample_rate,
                device_channels,
            )?,
            fmt => anyhow::bail!("Unsupported sample format: {:?}", fmt),
        };

        stream.play().context("Failed to start audio stream")?;
        info!("✅ Audio capture running");

        Ok(Self { _stream: stream })
    }

    fn find_16khz_config(device: &cpal::Device) -> Option<(StreamConfig, SampleFormat)> {
        let supported = device.supported_input_configs().ok()?;
        for range in supported {
            if range.channels() == 1
                && range.min_sample_rate().0 <= SAMPLE_RATE
                && range.max_sample_rate().0 >= SAMPLE_RATE
            {
                let fmt = range.sample_format();
                let cfg = range.with_sample_rate(cpal::SampleRate(SAMPLE_RATE)).config();
                return Some((cfg, fmt));
            }
        }
        None
    }

    fn build_stream<T: cpal::Sample + cpal::SizedSample + Into<f32>>(
        device: &cpal::Device,
        config: &StreamConfig,
        ring_buffer: Arc<Mutex<RingBuffer>>,
        device_sample_rate: u32,
        channels: usize,
    ) -> Result<Stream> {
        let err_fn = |e| error!("Audio stream error: {}", e);

        let stream = device.build_input_stream(
            config,
            move |data: &[T], _: &cpal::InputCallbackInfo| {
                // Mix down to mono
                let mono: Vec<f32> = data
                    .chunks(channels)
                    .map(|ch| ch.iter().map(|s| (*s).into()).sum::<f32>() / channels as f32)
                    .collect();

                // Resample to 16kHz if needed
                let resampled = if device_sample_rate != SAMPLE_RATE {
                    resample(&mono, device_sample_rate, SAMPLE_RATE)
                } else {
                    mono
                };

                // Push frames in 20ms chunks
                let rb = ring_buffer.clone();
                for chunk in resampled.chunks(FRAME_SIZE) {
                    if let Ok(mut buf) = rb.try_lock() {
                        buf.push_frame(chunk);
                    }
                }
            },
            err_fn,
            None,
        )?;

        Ok(stream)
    }

    fn build_stream_i16(
        device: &cpal::Device,
        config: &StreamConfig,
        ring_buffer: Arc<Mutex<RingBuffer>>,
        device_sample_rate: u32,
        channels: usize,
    ) -> Result<Stream> {
        let err_fn = |e| error!("Audio stream error: {}", e);

        let stream = device.build_input_stream(
            config,
            move |data: &[i16], _: &cpal::InputCallbackInfo| {
                // Convert i16 → f32 and mix down to mono
                let mono: Vec<f32> = data
                    .chunks(channels)
                    .map(|ch| {
                        ch.iter().map(|&s| s as f32 / 32768.0).sum::<f32>() / channels as f32
                    })
                    .collect();

                let resampled = if device_sample_rate != SAMPLE_RATE {
                    resample(&mono, device_sample_rate, SAMPLE_RATE)
                } else {
                    mono
                };

                let rb = ring_buffer.clone();
                for chunk in resampled.chunks(FRAME_SIZE) {
                    if let Ok(mut buf) = rb.try_lock() {
                        buf.push_frame(chunk);
                    }
                }
            },
            err_fn,
            None,
        )?;

        Ok(stream)
    }
}

/// Linear interpolation resampler (simple but sufficient for 16kHz target)
fn resample(input: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    if from_rate == to_rate {
        return input.to_vec();
    }
    let ratio = from_rate as f64 / to_rate as f64;
    let out_len = (input.len() as f64 / ratio) as usize;
    let mut output = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let pos = i as f64 * ratio;
        let idx = pos as usize;
        let frac = (pos - idx as f64) as f32;
        let a = input.get(idx).copied().unwrap_or(0.0);
        let b = input.get(idx + 1).copied().unwrap_or(a);
        output.push(a + frac * (b - a));
    }
    output
}
