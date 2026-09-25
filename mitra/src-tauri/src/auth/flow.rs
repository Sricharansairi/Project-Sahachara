//! flow.rs — Full OAuth 2.0 PKCE lifecycle manager (initiation, exchange, silent refresh, API test)
use anyhow::{bail, Context, Result};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tracing::{info, warn};

use super::pkce::PkcePair;
use super::providers::{OAuthProvider, ProviderConfig};
use super::storage::TokenStorage;
use super::token::TokenBundle;

pub struct AuthSession {
    pub provider: OAuthProvider,
    pub verifier: String,
    pub state: String,
    pub created_at: i64,
}

pub struct OAuthManager {
    storage: Arc<dyn TokenStorage>,
    pending_sessions: Arc<Mutex<HashMap<String, AuthSession>>>,
    client: reqwest::Client,
    mock_mode: bool,
}

impl OAuthManager {
    pub fn new(storage: Arc<dyn TokenStorage>) -> Self {
        Self {
            storage,
            pending_sessions: Arc::new(Mutex::new(HashMap::new())),
            client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(10))
                .build()
                .unwrap_or_default(),
            mock_mode: false,
        }
    }

    pub fn with_mock_mode(mut self, mock: bool) -> Self {
        self.mock_mode = mock;
        self
    }

    /// Step 1: Start OAuth flow — returns (auth_url, state)
    pub fn start_flow(&self, provider: OAuthProvider) -> (String, String) {
        let pkce = PkcePair::generate();
        let state = uuid::Uuid::new_v4().to_string();
        let config = ProviderConfig::for_provider(provider);
        let auth_url = config.build_auth_url(&pkce.challenge, &state);

        let session = AuthSession {
            provider,
            verifier: pkce.verifier,
            state: state.clone(),
            created_at: chrono::Utc::now().timestamp(),
        };

        let mut sessions = self.pending_sessions.lock().unwrap();
        sessions.insert(state.clone(), session);

        info!("🚀 OAuth flow started for {}: state={}", provider.as_str(), state);
        (auth_url, state)
    }

    /// Step 2: Handle authorization code callback and exchange for tokens
    pub async fn exchange_code(&self, state: &str, code: &str) -> Result<TokenBundle> {
        let session = {
            let mut sessions = self.pending_sessions.lock().unwrap();
            sessions.remove(state)
                .ok_or_else(|| anyhow::anyhow!("Invalid or expired OAuth state parameter"))?
        };

        let config = ProviderConfig::for_provider(session.provider);

        let token_bundle = if self.mock_mode {
            // Deterministic mock exchange for automated testing
            TokenBundle::new(
                format!("mock_access_token_{}_{}", session.provider.as_str(), code),
                Some(format!("mock_refresh_token_{}", session.provider.as_str())),
                3600, // 1 hour
                Some("Bearer".to_string()),
                config.scopes.clone(),
            )
        } else {
            // Live HTTP exchange
            let mut params = HashMap::new();
            params.insert("grant_type", "authorization_code");
            params.insert("code", code);
            params.insert("redirect_uri", &config.redirect_uri);
            params.insert("client_id", &config.client_id);
            params.insert("code_verifier", &session.verifier);

            let res = self.client
                .post(&config.token_endpoint)
                .form(&params)
                .send()
                .await
                .context("Token exchange HTTP request failed")?;

            if !res.status().is_success() {
                let err_text = res.text().await.unwrap_or_default();
                bail!("Token exchange rejected by provider: {}", err_text);
            }

            #[derive(serde::Deserialize)]
            struct TokenResponse {
                access_token: String,
                refresh_token: Option<String>,
                expires_in: Option<i64>,
                token_type: Option<String>,
            }

            let data: TokenResponse = res.json().await
                .context("Failed to parse token response")?;

            TokenBundle::new(
                data.access_token,
                data.refresh_token,
                data.expires_in.unwrap_or(3600),
                data.token_type,
                config.scopes.clone(),
            )
        };

        // Persist token in secure credential locker
        self.storage.save_token(session.provider, &token_bundle)?;
        info!("✅ OAuth token exchange complete and persisted for {}", session.provider.as_str());

        Ok(token_bundle)
    }

    /// Step 3: Refresh token using refresh_token
    pub async fn refresh_token(&self, provider: OAuthProvider, refresh_token: &str) -> Result<TokenBundle> {
        let config = ProviderConfig::for_provider(provider);

        let refreshed = if self.mock_mode {
            TokenBundle::new(
                format!("mock_refreshed_access_{}_{}", provider.as_str(), uuid::Uuid::new_v4()),
                Some(refresh_token.to_string()),
                3600,
                Some("Bearer".to_string()),
                config.scopes.clone(),
            )
        } else {
            let mut params = HashMap::new();
            params.insert("grant_type", "refresh_token");
            params.insert("refresh_token", refresh_token);
            params.insert("client_id", &config.client_id);

            let res = self.client
                .post(&config.token_endpoint)
                .form(&params)
                .send()
                .await
                .context("Token refresh HTTP request failed")?;

            if !res.status().is_success() {
                let err_text = res.text().await.unwrap_or_default();
                bail!("Token refresh rejected by provider: {}", err_text);
            }

            #[derive(serde::Deserialize)]
            struct RefreshResponse {
                access_token: String,
                refresh_token: Option<String>,
                expires_in: Option<i64>,
                token_type: Option<String>,
            }

            let data: RefreshResponse = res.json().await
                .context("Failed to parse refresh response")?;

            TokenBundle::new(
                data.access_token,
                data.refresh_token.or_else(|| Some(refresh_token.to_string())),
                data.expires_in.unwrap_or(3600),
                data.token_type,
                config.scopes.clone(),
            )
        };

        self.storage.save_token(provider, &refreshed)?;
        info!("🔄 Token refreshed silently and saved for {}", provider.as_str());
        Ok(refreshed)
    }

    /// Step 4: Silent auto-refresh — retrieves active token, auto-refreshing if within 5 min of expiry
    pub async fn get_valid_token(&self, provider: OAuthProvider) -> Result<TokenBundle> {
        let token = self.storage.load_token(provider)?
            .ok_or_else(|| anyhow::anyhow!("No active token for provider {}", provider.as_str()))?;

        if token.needs_refresh() {
            info!("⏳ Token for {} needs refresh (within 5-minute window). Refreshing silently...", provider.as_str());
            if let Some(ref refresh_tok) = token.refresh_token {
                self.refresh_token(provider, refresh_tok).await
            } else {
                warn!("Token for {} is expiring but has no refresh token", provider.as_str());
                Ok(token)
            }
        } else {
            Ok(token)
        }
    }

    /// Step 5: Test Microsoft Graph API call
    pub async fn test_ms_graph_call(&self, token: &str) -> Result<serde_json::Value> {
        if self.mock_mode {
            // Mock Microsoft Graph response
            return Ok(serde_json::json!({
                "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users/$entity",
                "displayName": "Sahachara Test User",
                "mail": "user@sahachara.test",
                "userPrincipalName": "user@sahachara.test",
                "id": "mock-ms365-guid-1234"
            }));
        }

        let res = self.client
            .get("https://graph.microsoft.com/v1.0/me")
            .bearer_auth(token)
            .send()
            .await
            .context("Graph API request failed")?;

        if !res.status().is_success() {
            let err_text = res.text().await.unwrap_or_default();
            bail!("Graph API call failed: {}", err_text);
        }

        let json = res.json().await.context("Failed to parse Graph API JSON")?;
        Ok(json)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::storage::InMemoryTokenStorage;

    #[tokio::test]
    async fn test_full_google_pkce_flow() {
        let storage = Arc::new(InMemoryTokenStorage::new());
        let manager = OAuthManager::new(storage.clone()).with_mock_mode(true);

        // 1. Start flow
        let (auth_url, state) = manager.start_flow(OAuthProvider::Google);
        assert!(auth_url.contains("code_challenge="));
        assert!(auth_url.contains(&format!("state={}", state)));

        // 2. Exchange authorization code
        let token = manager.exchange_code(&state, "auth_code_xyz123").await.unwrap();
        assert!(token.access_token.contains("google_auth_code_xyz123"));
        assert_eq!(token.refresh_token, Some("mock_refresh_token_google".to_string()));

        // 3. Verify token was stored
        let loaded = storage.load_token(OAuthProvider::Google).unwrap().unwrap();
        assert_eq!(loaded.access_token, token.access_token);
    }

    #[tokio::test]
    async fn test_ms365_flow_and_graph_api() {
        let storage = Arc::new(InMemoryTokenStorage::new());
        let manager = OAuthManager::new(storage.clone()).with_mock_mode(true);

        let (_auth_url, state) = manager.start_flow(OAuthProvider::Microsoft365);
        let token = manager.exchange_code(&state, "ms_code_abc").await.unwrap();
        
        let graph_res = manager.test_ms_graph_call(&token.access_token).await.unwrap();
        assert_eq!(graph_res["displayName"], "Sahachara Test User");
        assert_eq!(graph_res["mail"], "user@sahachara.test");
    }

    #[tokio::test]
    async fn test_silent_token_refresh() {
        let storage = Arc::new(InMemoryTokenStorage::new());
        let manager = OAuthManager::new(storage.clone()).with_mock_mode(true);

        let now = chrono::Utc::now().timestamp();
        // Insert a token that expires in 2 minutes (120s < 300s window)
        let soon_expiring = TokenBundle {
            access_token: "old_access_token".to_string(),
            refresh_token: Some("valid_refresh_token".to_string()),
            token_type: "Bearer".to_string(),
            expires_at: now + 120,
            scopes: vec!["email".to_string()],
        };
        storage.save_token(OAuthProvider::Google, &soon_expiring).unwrap();

        // get_valid_token should trigger silent refresh automatically
        let refreshed = manager.get_valid_token(OAuthProvider::Google).await.unwrap();
        assert_ne!(refreshed.access_token, "old_access_token");
        assert!(refreshed.access_token.starts_with("mock_refreshed_access_google"));
        assert!(refreshed.expires_at > now + 3000);
    }
}
