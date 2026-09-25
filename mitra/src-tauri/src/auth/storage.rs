//! storage.rs — Secure token storage in Windows Credential Locker (keyring)
use anyhow::{Context, Result};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tracing::{info, warn};

use super::providers::OAuthProvider;
use super::token::TokenBundle;

const KEYRING_SERVICE: &str = "com.project-sahachara.mitra.oauth";

pub trait TokenStorage: Send + Sync {
    fn save_token(&self, provider: OAuthProvider, token: &TokenBundle) -> Result<()>;
    fn load_token(&self, provider: OAuthProvider) -> Result<Option<TokenBundle>>;
    fn delete_token(&self, provider: OAuthProvider) -> Result<()>;
}

/// Production storage backed by Windows Credential Locker via the keyring crate
pub struct KeyringTokenStorage;

impl KeyringTokenStorage {
    pub fn new() -> Self {
        Self
    }
}

impl TokenStorage for KeyringTokenStorage {
    fn save_token(&self, provider: OAuthProvider, token: &TokenBundle) -> Result<()> {
        let entry = keyring::Entry::new(KEYRING_SERVICE, provider.as_str())
            .map_err(|e| anyhow::anyhow!("Failed to initialize keyring entry: {}", e))?;
        let json = serde_json::to_string(token)
            .context("Failed to serialize token bundle")?;
        entry.set_password(&json)
            .map_err(|e| anyhow::anyhow!("Failed to write to Windows Credential Locker: {}", e))?;
        info!("🔐 Token for {} secured in Windows Credential Locker", provider.as_str());
        Ok(())
    }

    fn load_token(&self, provider: OAuthProvider) -> Result<Option<TokenBundle>> {
        let entry = keyring::Entry::new(KEYRING_SERVICE, provider.as_str())
            .map_err(|e| anyhow::anyhow!("Failed to initialize keyring entry: {}", e))?;
        match entry.get_password() {
            Ok(json) => {
                let token: TokenBundle = serde_json::from_str(&json)
                    .context("Failed to deserialize token bundle from keyring")?;
                Ok(Some(token))
            }
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(e) => {
                warn!("Keyring load warning for {}: {}", provider.as_str(), e);
                Ok(None)
            }
        }
    }

    fn delete_token(&self, provider: OAuthProvider) -> Result<()> {
        let entry = keyring::Entry::new(KEYRING_SERVICE, provider.as_str())
            .map_err(|e| anyhow::anyhow!("Failed to initialize keyring entry: {}", e))?;
        match entry.delete_credential() {
            Ok(_) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(e) => Err(anyhow::anyhow!("Failed to delete token from keyring: {}", e)),
        }
    }
}

/// In-memory storage for deterministic automated tests
#[derive(Clone, Default)]
pub struct InMemoryTokenStorage {
    tokens: Arc<Mutex<HashMap<OAuthProvider, TokenBundle>>>,
}

impl InMemoryTokenStorage {
    pub fn new() -> Self {
        Self {
            tokens: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}

impl TokenStorage for InMemoryTokenStorage {
    fn save_token(&self, provider: OAuthProvider, token: &TokenBundle) -> Result<()> {
        let mut map = self.tokens.lock().unwrap();
        map.insert(provider, token.clone());
        Ok(())
    }

    fn load_token(&self, provider: OAuthProvider) -> Result<Option<TokenBundle>> {
        let map = self.tokens.lock().unwrap();
        Ok(map.get(&provider).cloned())
    }

    fn delete_token(&self, provider: OAuthProvider) -> Result<()> {
        let mut map = self.tokens.lock().unwrap();
        map.remove(&provider);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_in_memory_token_storage() {
        let storage = InMemoryTokenStorage::new();
        let provider = OAuthProvider::Google;

        // Initially empty
        assert!(storage.load_token(provider).unwrap().is_none());

        // Save token
        let token = TokenBundle::new(
            "test_access_123".to_string(),
            Some("test_refresh_123".to_string()),
            3600,
            None,
            vec!["email".to_string()],
        );
        storage.save_token(provider, &token).unwrap();

        // Load token
        let loaded = storage.load_token(provider).unwrap().expect("Token should be found");
        assert_eq!(loaded.access_token, "test_access_123");
        assert_eq!(loaded.refresh_token, Some("test_refresh_123".to_string()));

        // Delete token
        storage.delete_token(provider).unwrap();
        assert!(storage.load_token(provider).unwrap().is_none());
    }
}
