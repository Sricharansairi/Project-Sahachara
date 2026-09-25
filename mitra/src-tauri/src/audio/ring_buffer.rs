//! ring_buffer.rs — 2-second circular audio ring buffer
//! Privacy invariant: overwrite_all() wipes data when Stage 1 does not fire.

use std::collections::VecDeque;

/// Sample rate assumed: 16000 Hz. 2 seconds = 32000 samples.
pub struct RingBuffer {
    data: VecDeque<f32>,
    capacity: usize,
    /// Latest audio energy level (RMS), updated on each push_frame()
    pub current_level: f32,
}

impl RingBuffer {
    /// Create a new ring buffer for `seconds` of audio at `sample_rate` Hz.
    pub fn new(seconds: f32, sample_rate: u32) -> Self {
        let capacity = (seconds * sample_rate as f32) as usize;
        Self {
            data: VecDeque::with_capacity(capacity),
            capacity,
            current_level: 0.0,
        }
    }

    /// Push a frame of audio samples into the ring buffer.
    /// Old samples are discarded when capacity is reached.
    pub fn push_frame(&mut self, frame: &[f32]) {
        // Update current RMS level
        let rms = (frame.iter().map(|s| s * s).sum::<f32>() / frame.len() as f32).sqrt();
        self.current_level = rms;

        for &sample in frame {
            if self.data.len() == self.capacity {
                self.data.pop_front();
            }
            self.data.push_back(sample);
        }
    }

    /// Get the last `n_seconds` of audio samples.
    pub fn get_last_n_seconds(&self, n_seconds: f32, sample_rate: u32) -> Vec<f32> {
        let n_samples = (n_seconds * sample_rate as f32) as usize;
        let start = self.data.len().saturating_sub(n_samples);
        self.data.range(start..).cloned().collect()
    }

    /// Get a snapshot of all current samples in the buffer.
    pub fn get_all(&self) -> Vec<f32> {
        self.data.iter().cloned().collect()
    }

    /// PRIVACY INVARIANT: Overwrite all audio data with zeros.
    /// Called when Stage 1 wake word detection does NOT fire.
    pub fn overwrite_all(&mut self) {
        for sample in self.data.iter_mut() {
            *sample = 0.0;
        }
        self.current_level = 0.0;
        tracing::trace!("🔒 Ring buffer wiped (privacy invariant maintained)");
    }

    /// Returns how many samples are currently in the buffer.
    pub fn len(&self) -> usize {
        self.data.len()
    }

    /// Returns true if buffer is empty.
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ring_buffer_capacity() {
        let mut buf = RingBuffer::new(2.0, 16000);
        let frame = vec![0.5f32; 320]; // 20ms frame
        for _ in 0..200 {
            // push 4 seconds worth
            buf.push_frame(&frame);
        }
        // Should not exceed 2s capacity
        assert!(buf.len() <= 32000);
    }

    #[test]
    fn test_ring_buffer_overwrite() {
        let mut buf = RingBuffer::new(2.0, 16000);
        let frame = vec![0.9f32; 1600];
        buf.push_frame(&frame);
        assert!(buf.current_level > 0.0);

        buf.overwrite_all();

        let all = buf.get_all();
        assert!(all.iter().all(|&s| s == 0.0), "All samples should be zeroed");
        assert_eq!(buf.current_level, 0.0);
    }

    #[test]
    fn test_get_last_n_seconds() {
        let mut buf = RingBuffer::new(2.0, 16000);
        // Push 1 second of 1.0 samples, then 1 second of 0.5 samples
        buf.push_frame(&vec![1.0f32; 16000]);
        buf.push_frame(&vec![0.5f32; 16000]);
        let last_half = buf.get_last_n_seconds(0.5, 16000);
        assert_eq!(last_half.len(), 8000);
        assert!(last_half.iter().all(|&s| (s - 0.5).abs() < 1e-6));
    }
}
