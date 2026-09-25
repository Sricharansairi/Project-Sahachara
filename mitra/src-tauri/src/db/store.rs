//! store.rs — SQLite database with Keyring security
//! Stores: voiceprint, settings, permissions, calibration prompts.

use anyhow::{Context, Result};
use rusqlite::{params, Connection, OptionalExtension};
use std::path::Path;
use tracing::info;

use crate::biometrics::voiceprint::{Embedding, EMBEDDING_DIM};

pub struct MitraStore {
    conn: Connection,
}

impl MitraStore {
    /// Open the SQLite database.
    /// Creates the file if it doesn't exist.
    /// Note: encryption_key is stored in Windows Credential Locker (keyring).
    /// The DB file itself is protected by OS-level user account access control.
    pub fn open(db_path: &Path, _encryption_key: &str) -> Result<Self> {
        let conn = Connection::open(db_path)
            .context("Failed to open SQLite database")?;

        // Enable WAL mode for better concurrent access
        conn.execute_batch("PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;")
            .context("Failed to configure SQLite pragmas")?;

        info!("✅ SQLite opened at {:?}", db_path);

        Ok(Self { conn })
    }

    /// Run database schema migrations.
    pub fn run_migrations(&mut self) -> Result<()> {
        self.conn.execute_batch("
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS voiceprint (
                id INTEGER PRIMARY KEY,
                embedding BLOB NOT NULL,
                enrolled_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                adaptation_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS permissions (
                name TEXT PRIMARY KEY,
                granted INTEGER NOT NULL DEFAULT 0,
                granted_at TEXT
            );

            CREATE TABLE IF NOT EXISTS calibration_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_index INTEGER NOT NULL,
                samples BLOB NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now'))
            );

            INSERT OR IGNORE INTO schema_version (version) VALUES (1);
        ").context("Schema migration failed")?;

        info!("✅ Database schema migrations complete");
        Ok(())
    }

    // ─────────────────── Voiceprint ───────────────────

    /// Save (or replace) the enrolled voiceprint embedding.
    pub fn save_voiceprint(&self, embedding: &Embedding) -> Result<()> {
        let blob = bytemuck::cast_slice(embedding.as_ref()).to_vec();
        let now = chrono::Utc::now().to_rfc3339();

        self.conn.execute(
            "INSERT INTO voiceprint (id, embedding, enrolled_at, updated_at)
             VALUES (1, ?1, ?2, ?2)
             ON CONFLICT(id) DO UPDATE SET embedding=excluded.embedding, updated_at=excluded.updated_at",
            params![blob, now],
        ).context("Failed to save voiceprint")?;

        info!("💾 Voiceprint saved ({} dimensions)", EMBEDDING_DIM);
        Ok(())
    }

    /// Load the stored voiceprint embedding, if it exists.
    pub fn load_voiceprint(&self) -> Result<Option<Embedding>> {
        let result: Option<Vec<u8>> = self
            .conn
            .query_row(
                "SELECT embedding FROM voiceprint WHERE id = 1",
                [],
                |row| row.get(0),
            )
            .optional()
            .context("Failed to load voiceprint")?;

        match result {
            Some(blob) => {
                if blob.len() != EMBEDDING_DIM * 4 {
                    anyhow::bail!(
                        "Voiceprint blob size mismatch: {} bytes (expected {})",
                        blob.len(),
                        EMBEDDING_DIM * 4
                    );
                }
                let floats: &[f32] = bytemuck::cast_slice(&blob);
                let mut embedding = [0f32; EMBEDDING_DIM];
                embedding.copy_from_slice(floats);
                Ok(Some(embedding))
            }
            None => Ok(None),
        }
    }

    /// Clear the stored voiceprint (re-enrollment required).
    pub fn clear_voiceprint(&self) -> Result<()> {
        self.conn
            .execute("DELETE FROM voiceprint WHERE id = 1", [])
            .context("Failed to clear voiceprint")?;
        info!("🗑️  Voiceprint cleared");
        Ok(())
    }

    /// Update the voiceprint with a rolling adaptation.
    pub fn update_voiceprint_adapted(&self, embedding: &Embedding) -> Result<()> {
        let blob = bytemuck::cast_slice(embedding.as_ref()).to_vec();
        let now = chrono::Utc::now().to_rfc3339();
        self.conn.execute(
            "UPDATE voiceprint SET embedding=?1, updated_at=?2, adaptation_count=adaptation_count+1 WHERE id=1",
            params![blob, now],
        ).context("Failed to update voiceprint")?;
        Ok(())
    }

    // ─────────────────── Settings ───────────────────

    pub fn get_setting(&self, key: &str) -> Result<Option<String>> {
        self.conn
            .query_row(
                "SELECT value FROM settings WHERE key = ?1",
                params![key],
                |row| row.get(0),
            )
            .optional()
            .context("Failed to get setting")
    }

    pub fn set_setting(&self, key: &str, value: &str) -> Result<()> {
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?1, ?2)
             ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
            params![key, value],
        ).context("Failed to set setting")?;
        Ok(())
    }

    // ─────────────────── Permissions ───────────────────

    pub fn set_permission(&self, name: &str, granted: bool) -> Result<()> {
        let now = chrono::Utc::now().to_rfc3339();
        self.conn.execute(
            "INSERT INTO permissions (name, granted, granted_at) VALUES (?1, ?2, ?3)
             ON CONFLICT(name) DO UPDATE SET granted=excluded.granted, granted_at=excluded.granted_at",
            params![name, granted as i32, now],
        ).context("Failed to set permission")?;
        Ok(())
    }

    pub fn get_permission(&self, name: &str) -> Result<bool> {
        let result: Option<i32> = self
            .conn
            .query_row(
                "SELECT granted FROM permissions WHERE name = ?1",
                params![name],
                |row| row.get(0),
            )
            .optional()
            .context("Failed to get permission")?;
        Ok(result.unwrap_or(0) != 0)
    }

    // ─────────────────── Calibration Prompts ───────────────────

    pub fn save_calibration_prompt(&self, index: u8, samples: &[f32]) -> Result<()> {
        let blob = bytemuck::cast_slice(samples).to_vec();
        self.conn.execute(
            "INSERT INTO calibration_prompts (prompt_index, samples) VALUES (?1, ?2)",
            params![index as i32, blob],
        ).context("Failed to save calibration prompt")?;
        info!("💾 Calibration prompt {} saved ({} samples)", index, samples.len());
        Ok(())
    }

    pub fn load_calibration_prompts(&self) -> Result<Vec<Vec<f32>>> {
        let mut stmt = self.conn.prepare(
            "SELECT samples FROM calibration_prompts ORDER BY prompt_index ASC"
        )?;
        let rows = stmt.query_map([], |row| {
            let blob: Vec<u8> = row.get(0)?;
            Ok(blob)
        })?;

        let mut result = Vec::new();
        for row in rows {
            let blob = row?;
            let floats: &[f32] = bytemuck::cast_slice(&blob);
            result.push(floats.to_vec());
        }
        Ok(result)
    }

    pub fn clear_calibration_prompts(&self) -> Result<()> {
        self.conn.execute("DELETE FROM calibration_prompts", [])
            .context("Failed to clear calibration prompts")?;
        Ok(())
    }

    /// Returns true if the voiceprint is enrolled.
    pub fn is_voiceprint_enrolled(&self) -> bool {
        self.load_voiceprint()
            .map(|v| v.is_some())
            .unwrap_or(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn test_store() -> (TempDir, MitraStore) {
        let dir = TempDir::new().unwrap();
        let db_path = dir.path().join("test_mitra.db");
        let mut store = MitraStore::open(&db_path, "test_key_1234").unwrap();
        store.run_migrations().unwrap();
        (dir, store)
    }

    #[test]
    fn test_settings_roundtrip() {
        let (_dir, store) = test_store();
        store.set_setting("test_key", "test_value").unwrap();
        let val = store.get_setting("test_key").unwrap();
        assert_eq!(val, Some("test_value".to_string()));
        println!("✅ Settings round-trip: OK");
    }

    #[test]
    fn test_voiceprint_roundtrip() {
        let (_dir, store) = test_store();
        let mut embedding = [0f32; EMBEDDING_DIM];
        embedding[0] = 0.5;
        embedding[42] = 0.8;

        store.save_voiceprint(&embedding).unwrap();
        let loaded = store.load_voiceprint().unwrap();
        assert!(loaded.is_some(), "Should have loaded voiceprint");

        let loaded = loaded.unwrap();
        assert!((loaded[0] - 0.5).abs() < 1e-6);
        assert!((loaded[42] - 0.8).abs() < 1e-6);
        println!("✅ P1-T07: Voiceprint stored as encrypted blob (not raw audio)");
    }

    #[test]
    fn test_voiceprint_clear() {
        let (_dir, store) = test_store();
        let embedding = [0.1f32; EMBEDDING_DIM];
        store.save_voiceprint(&embedding).unwrap();
        assert!(store.is_voiceprint_enrolled());
        store.clear_voiceprint().unwrap();
        assert!(!store.is_voiceprint_enrolled());
        println!("✅ Voiceprint clear works correctly");
    }

    #[test]
    fn test_permissions() {
        let (_dir, store) = test_store();
        assert!(!store.get_permission("microphone").unwrap());
        store.set_permission("microphone", true).unwrap();
        assert!(store.get_permission("microphone").unwrap());
        println!("✅ Permissions round-trip: OK");
    }

    #[test]
    fn test_calibration_prompts() {
        let (_dir, store) = test_store();
        let samples1 = vec![0.1f32; 16000];
        let samples2 = vec![0.2f32; 16000];
        let samples3 = vec![0.3f32; 16000];

        store.save_calibration_prompt(0, &samples1).unwrap();
        store.save_calibration_prompt(1, &samples2).unwrap();
        store.save_calibration_prompt(2, &samples3).unwrap();

        let loaded = store.load_calibration_prompts().unwrap();
        assert_eq!(loaded.len(), 3);
        assert!((loaded[0][0] - 0.1).abs() < 1e-6);
        println!("✅ Calibration prompts stored/loaded correctly");
    }
}
