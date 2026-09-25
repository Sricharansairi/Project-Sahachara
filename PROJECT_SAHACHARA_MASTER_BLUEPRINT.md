# PROJECT SAHACHARA: PRODUCTION ARCHITECTURE & MASTER BLUEPRINT
**Version:** 4.0.0-PROD  
**Assistant Official Name:** **MITRA** (*"The Trusted Companion & Guardian"*)  
**Wake Phrases:** *"Hey Mitra"* / *"Okay Mitra"*  
**Target:** Enterprise & Corporate Multi-Persona Productivity Companion  
**Form Factor:** Native Desktop (Tauri v2 + Rust) with Ambient Floating Pill / Tray UI & High-Performance Cloud Backend

---

## 1. THE HACKATHON PITCH & THE PROBLEM GAP

> *"On mobile, Google Gemini and Siri live seamlessly with you—waking on voice, seeing what is on your screen, and assisting you effortlessly. But on desktop personal computers—where 90% of high-value professional work, architectural modeling, video editing, corporate negotiations, and document drafting actually happens—AI is still trapped in a browser tab or a bulky chat window.*
>
> *Project Sahachara bridges this gap with **MITRA**. It is the first ambient, voice-biometric-activated, vision-aware AI companion built natively for PC professionals. It wakes up on your unique voice using a private 2-stage acoustic detector, docks elegantly like a Dynamic Island, glances at active software on-demand, tracks all commitments and deadlines autonomously, searches company drives semantically, and executes actions safely via native connectors and n8n orchestration."*

---

## 2. CLIENT-SIDE ARCHITECTURE (DESKTOP INTERFACE)

### 2.1 Technology Stack & Resource Budget
* **Shell Framework:** Tauri v2 (Rust core + Webview frontend).
* **Binary Size & Memory Footprint:** < 35 MB installer, **35–50 MB idle RAM** (90% lighter than Electron apps like Slack/Teams which consume 400MB+).
* **CPU Usage:** < 0.8% at idle (VAD running in low-power sleep mode).
* **Frontend:** React 19 / Svelte 5 + TypeScript + Tailwind CSS (Glassmorphism, animated soundwaves, Dynamic Island morphing).

### 2.2 First-Run Privacy Onboarding & Permission Handshake
Before capturing a single frame or audio sample, the application presents a transparent **System Permission Consent Modal**:
1. **Microphone Access:** Explicit OS privacy prompt + explanation of local-only wake-word buffering.
2. **Screen Recording / Capture:** OS Graphics Capture consent with clear declaration of on-demand shutter triggers (no background passive recording).
3. **Connectors Authorization (OAuth):** Opt-in permissions for Google Workspace, MS 365, or n8n webhooks.
4. **Visual Mic/Screen Indicator:** Whenever the microphone is streaming or screen is captured, the floating pill displays a glowing green privacy ring with active indicator badges.

### 2.3 Personalized Voiceprint Biometrics (Option B Architecture)
To ensure only **your** voice can trigger Mitra on your PC:
* **3-Prompt Onboarding Calibration:**
  * *"Say: 'Hey Mitra, what's on my screen?'"*
  * *"Say: 'Okay Mitra, follow up on this email.'"*
  * *"Say: 'Hey Mitra, remind me at 4 PM.'"*
* **Local Embedding Vector Extraction:**
  * Uses a compact local acoustic ONNX model (Resemblyzer / ECAPA-TDNN, ~15MB) running on CPU via `ort`.
  * Extracts a 192-dimensional voiceprint vector stored strictly in local encrypted SQLite.
* **Rolling Acoustic Adaptation:**
  * When you switch microphones (e.g. laptop mic to AirPods) or have morning voice, successful confirmed interactions smoothly update your rolling voice print vector so you are never locked out.
  * Colleague / stranger speech is rejected automatically via cosine thresholding.

### 2.4 Apple / Gemini Two-Stage Wake Word Architecture
To ensure 100% privacy, near-zero CPU usage, and zero false-cloud streaming:
1. **Stage 1 (Local Ultra-Low Power Micro-Head):** Runs locally on CPU via ONNX (`ort` crate). Operates on an ephemeral 2-second circular audio buffer in RAM. If sound level or phoneme signature doesn't match *"Hey Mitra"* or *"Okay Mitra"*, audio is instantly overwritten in RAM. **Zero bytes ever leave the PC**.
2. **Stage 2 (Local Acoustic Verifier + Voice Biometrics):** A 50ms verification pass verifies the wake word and confirms the voice embedding matches your registered profile.
3. **Stage 3 (Cloud Wake Handshake):** Only after Stage 2 fires does Mitra light up the floating pill with a visual ring and open the streaming WebSocket to the cloud backend.

### 2.5 Intelligent Conversational State Machine (8-Second Keep-Alive Window)
```mermaid
stateDiagram-v2
    [*] --> IdleSleep : Standby (Wake word only)
    IdleSleep --> ActiveListening : 'Hey Mitra' / 'Okay Mitra' / Hotkey
    
    ActiveListening --> UserSpeaking : Audio energy detected
    UserSpeaking --> VADEndpointing : User pauses speech
    
    VADEndpointing --> DeepProcessing : 700ms silence + ANN confirms turn completion
    VADEndpointing --> UserSpeaking : User resumes speaking within 700ms
    
    DeepProcessing --> AgentSpeaking : Kokoro streaming voice output
    
    AgentSpeaking --> ConversationalKeepAlive : Voice output finishes
    
    state ConversationalKeepAlive {
        [*] --> ListeningForFollowUp : 8-second countdown timer starts
        ListeningForFollowUp --> ResetTimer : User speaks before timeout
    }
    
    ConversationalKeepAlive --> ActiveListening : User speaks within 8 seconds
    ConversationalKeepAlive --> IdleSleep : 8 seconds expire with no speech (Pill auto-minimizes)
```

1. **Dynamic Speech Endpointing (VAD + ANN):** 700ms silence + turn-completion classification triggers reply without push-to-talk.
2. **8-Second Follow-up Keep-Alive:** Assistant remains listening for 8 seconds after speaking. Natural continuous multi-turn dialogue without repeating the wake word.
3. **Graceful Auto-Sleep:** Shuts down audio streams after 8 seconds of silence to conserve battery and cloud tokens.

### 2.6 Screen Capture Engine & Hardware Handling
* **Technology:** Windows Graphics Capture API / DirectX Desktop Duplication (`IDXGIOutputDuplication` via `windows-rs`).
* **HWND-Targeted Window Capture:** Targets specific active application handles (HWND) to eliminate DPI blur and coordinate displacement across multi-monitor 4K / high-DPI setups (125%, 150%, 200%).
* **Zero-Obstruction Auto-Docking:** Snaps into a 3px translucent border on the screen edge when working in full-screen creative software (Premiere, AutoCAD), expanding instantly when called.
* **Client-Side Privacy Filter:** Local heuristic/regex canvas masking for sensitive fields (credit cards, passwords, SSNs) before compression to WebP.

---

## 3. PROFESSIONAL AUTHENTICATION & LOGIN FLOW

* **Architecture:** OAuth 2.0 with PKCE via System Default Browser + Custom Deep Link (`sahachara://auth/callback`).
* **Supported Providers:**
  1. **Google Workspace (1-Click Gmail/Google Account)**
  2. **Microsoft 365 (Corporate Azure AD / Entra ID for corporate SSO)**
  3. **Apple ID (Sign in with Apple)**
* **Secure Token Vault:** Tokens are encrypted in the OS-native **Windows Credential Locker** using the Rust `keyring` crate. Zero plaintext credentials on disk.

---

## 4. NVIDIA NIM PRODUCTION MODEL MAPPING (PRIMARY + FALLBACK MATRIX)

Based on empirical live benchmarking against the NVIDIA integrate gateway, the system implements a resilient **Multi-Tier Primary & Fallback Routing Matrix**:

| Role in MITRA | Primary Model (Fast & Live) | Latency | Fallback Model | Rationale & Strengths |
| :--- | :--- | :---: | :--- | :--- |
| **Fast Brain & Voice Router** ⚡ | **`nvidia/nemotron-3-super-120b-a12b`** | **0.37s** | **`z-ai/glm-5.3`** (1.00s) | 120B MoE (12B active). Sub-400ms TTFT! Ultra-fast, ideal for live conversational speech. |
| **Deep Reasoning & LangGraph Brain** 🧠 | **`nvidia/nemotron-3-ultra-550b-a55b`** | **0.77s - 2.9s** | **`google/gemma-4-31b-it`** (11.4s) | 550B MoE (55B active). 1M context hybrid Mamba-Transformer. Frontier reasoning & tool-calling. |
| **Screen Glance & App Vision** 👁️ | **`meta/llama-3.2-11b-vision-instruct`** | **1.21s** | **`meta/muse-glimmer-30b`** (2.06s) | Real-time visual UI layout recognition, Premiere/CAD screen comprehension. |
| **Document, Table & Clause OCR** 📄 | **`nvidia/nemotron-parse-2.0`** | **0.71s** | **`meta/llama-3.2-11b-vision-instruct`** | Fine-tuned for dense tables, complex PDFs, and contract legal clause parsing. |
| **Semantic Search Embeddings** 🔍 | **`nvidia/nemotron-3-embed-1b`** | **0.55s** | **Local `BGE-M3` (ONNX)** | 2048-dim vector embeddings for hybrid cross-app search (Drive + Email + Disk). |
| **Real-Time Speech Recognition (STT)** 🎙️ | **`nvidia/parakeet-tdt-0.6b-v2`** | **< 150ms** | **Local Whisper / Deepgram Nova-3** | Ultra-low latency English ASR with built-in word timestamps and capitalization. |
| **Content Safety & Anti-Injection Guard** 🛡️ | **`nvidia/llama-3.1-nemoguard-8b-content-safety`** | **< 200ms** | **Local Regex / ANN Classifier Head** | Guards against indirect prompt injection from untrusted web pages and malicious documents. |

---

## 5. INTEGRATION ECOSYSTEM & CONNECTORS (N8N + NATIVE APIS)

```mermaid
flowchart TD
    Sahachara[Sahachara Brain / LangGraph] --> Sandbox[Action Sandbox & Approval Gate]
    
    subgraph NativeConnectors["Native Zero-Latency Connectors"]
        Sandbox --> Gmail[Gmail & Outlook / Exchange API]
        Sandbox --> Calendar[Google Calendar & MS 365 Calendar]
        Sandbox --> Drive[Google Drive, OneDrive & Notion API]
        Sandbox --> LocalFS[Local File System & Desktop Apps]
    end

    subgraph N8N_Bridge["n8n Workflow Automation Hub (Custom & Enterprise Webhooks)"]
        Sandbox --> Webhook[n8n Webhook / API Node]
        Webhook --> Slack[Slack / Teams Channel Bot]
        Webhook --> Jira[Jira / Linear / ClickUp Tickets]
        Webhook --> CRM[HubSpot / Salesforce Records]
        Webhook --> Custom[Custom 500+ n8n Community Integrations]
    end
```

### 5.1 Native Direct Connectors
* **Google Workspace:** Gmail (inbox scan, draft replies), Google Calendar (auto-scheduling), Google Drive (instant document retrieval).
* **Microsoft 365:** Outlook, MS Teams, OneDrive, SharePoint (via Microsoft Graph API for corporate enterprise users).
* **Notion & Slack:** Direct bridges for team channels and company wikis.

### 5.2 The n8n Workflow Supercharger
* Mitra acts as the **Intelligent Brain**, while **n8n acts as the Multi-System Muscle**.
* Structured JSON payloads sent to n8n webhooks trigger deterministic multi-step actions across 400+ SaaS apps (Jira, Salesforce, Slack, QuickBooks) with automatic retry and error reporting.

---

## 6. COGNITIVE ARCHITECTURE & ADVANCED INTELLIGENCE FEATURES

### 6.1 The "Ghost Follow-Up" Radar (Two-Way Commitment Engine)
1. **Outbound Promises ("I Owe You"):** Detects promises made in emails/Slack (*"I'll send the quote by 4 PM"*) and proactively alerts you 1 hour before.
2. **Inbound Awaiting ("You Owe Me"):** Tracks deliverables promised by others (*"Will send pricing by Wednesday"*) and prompts a 1-click polite follow-up draft if they miss it.

### 6.2 Meeting-Mode Auto-Ducking & Pre-Meeting Dossier
* **Meeting-Mode Auto-Ducking:** Automatically monitors Windows Audio Sessions. If Zoom, Teams, or Google Meet is active, Mitra **never speaks out loud**, automatically switching to silent on-screen floating cards.
* **Pre-Meeting 2-Minute Dossier:** Pulses 2 minutes before Google/Outlook calendar calls with a 3-bullet dossier (attendees, previous decisions, today's objective).

### 6.3 Universal Intelligent Clipboard Augmenter (`Ctrl + Shift + V`)
* Copying messy unstructured text triggers an instant badge to paste **auto-cleaned, formatted into a clean markdown table, summarized into bullets, or converted into structured JSON**.

### 6.4 The 10-Second Undo Action Buffer (`Ctrl + Z`)
* Every executed action (email draft, calendar invite, Jira ticket) shows a 10-second countdown toast: `[Undo Action (Ctrl + Z)]`. Pressing it triggers a zero-consequence rollback.

### 6.5 Contextual "Project Workspaces" Snapshots
* Freeze and restore full desktop mental context (open software, reference files, pending checklists) under project tags (e.g., *"Save Workspace: Q3 Architecture Review"*).

---

## 7. STREAMING VOICE ENGINE (KOKORO-82M)

* **Speech-to-Text (STT):** NVIDIA Parakeet-TDT 0.6b v2 or Deepgram Nova-3 (< 150ms).
* **Fast LLM:** DeepSeek-v4.1-Flash NIM (< 150ms TTFT).
* **Streaming Voice (TTS): Kokoro-82M Engine:**
  * Self-hosted on low-cost cloud GPU / CPU via `kokoro-fastapi` or ONNX.
  * **Chunk-based streaming:** Synthesizes and transmits audio buffers as soon as 4–6 words are generated by the LLM. Total voice round-trip latency < 400ms.
  * Acoustic Echo Cancellation (AEC) & Software Ducking: Automatically ducks microphone input during TTS playback unless speech barge-in is detected.
  * Fallback option: Cartesia Sonic API for managed zero-infra sub-100ms TTS.

---

## 8. ACTION SANDBOX & AUTONOMY GOVERNANCE

* **Tier 0 (Read-Only Ambient):** Screen OCR, document summarization, answering questions. No confirmation needed.
* **Tier 1 (Staged Draft / 1-Click Approval):** Drafting emails, scheduling meetings, triggering n8n flows. Actionable card in the floating pill: `[Enter: Approve | Esc: Reject | Space: Edit]`.
* **Tier 2 (Governed Execution):** Routine file organization and ticket generation.
* **Tier 3 (Prohibited):** System settings modification, file deletion, automated payment transmission.
* **Indirect Prompt Injection Defense:** All screen/document OCR text is wrapped in `<untrusted_visual_payload>` tags.

---

## 9. IMPLEMENTATION ROADMAP

See **[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)** for the full 7-phase execution plan with detailed tasks, acceptance criteria, and rigorous testing gates at each phase boundary.

**Phase summary:**
* **Phase 1** — Foundation Shell, Wake-Word Engine, Voiceprint Biometrics *(local/offline only)*
* **Phase 2** — Cloud Brain: FastAPI + NVIDIA NIM + LangGraph + RAG Memory
* **Phase 3** — Authentication (OAuth PKCE) + HWND Screen Capture Engine
* **Phase 4** — Full Voice Pipeline: STT → LLM → Kokoro TTS (<400ms E2E)
* **Phase 5** — Connectors (Google/MS365/n8n), Ghost Radar, Meeting Guard, Clipboard Augmenter, Undo Buffer
* **Phase 6** — Frontend UI Polish: Glassmorphic Floating Pill, Dynamic Island, Onboarding *(frontend is deliberately LAST)*
* **Phase 7** — Packaging, Code Signing, Auto-Updater, Final E2E Regression

---

## 10. SYSTEM FLOWCHARTS

### 10.1 Complete Feature Architecture Flowchart

```mermaid
flowchart TD
    User(["👤 User"]) -->|Voice / Hotkey / Click| WW

    subgraph Stage1["🔒 Stage 1 — Local Wake Word (Zero Cloud)"]
        WW["Ring Buffer\n(2s circular, RAM only)"]
        VAD["Silero VAD\n(ONNX, CPU)"]
        KWS["Keyword Spotter\nHey Mitra / Okay Mitra\n(ONNX, ~5MB)"]
        WW --> VAD --> KWS
    end

    subgraph Stage2["🔐 Stage 2 — Biometric Verification (Local)"]
        VP["ECAPA-TDNN\nVoiceprint Verifier\n(192-dim cosine match)"]
        KWS -->|Wake word detected| VP
    end

    VP -->|Identity confirmed| SM

    subgraph StateMachine["🔄 Conversational State Machine"]
        SM["ActiveListening"]
        SM --> US["UserSpeaking\n(VAD energy detected)"]
        US --> EP["VADEndpointing\n(700ms silence)"]
        EP --> DP["DeepProcessing\n(STT + LLM)"]
        DP --> AS["AgentSpeaking\n(TTS streaming)"]
        AS --> KA["ConversationalKeepAlive\n(8s window)"]
        KA -->|User speaks| SM
        KA -->|8s expires| SL["IdleSleep\n(streams closed)"]
    end

    EP -->|Audio stream| STT

    subgraph VoicePipeline["🎙️ Voice Pipeline"]
        STT["STT\nParakeet-TDT-0.6b\n<150ms"] -->|Transcript| Safety
        Safety["NemoGuard\nSafety Classifier\n<200ms"] -->|Clean input| Router
    end

    subgraph BrainRouter["🧠 NVIDIA NIM Model Router"]
        Router{"Intent\nClassifier"} -->|Conversational / Fast| FastBrain["nemotron-super-120b\n0.37s TTFT"]
        Router -->|Deep reasoning / Think mode| DeepBrain["nemotron-ultra-550b\n0.77-2.9s TTFT"]
        Router -->|Vision / Screen| Vision["llama-3.2-11b-vision\n1.21s"]
        Router -->|Document / OCR| OCR["nemotron-parse-2.0\n0.71s"]
        FastBrain -.->|Fallback| FB1["glm-5.3"]
        DeepBrain -.->|Fallback| FB2["gemma-4-31b-it"]
    end

    FastBrain --> LG
    DeepBrain --> LG
    Vision --> LG

    subgraph LangGraph["⚙️ LangGraph MitraGraph Orchestration"]
        LG["MitraGraph\nAgent Brain"] --> T0["Tier 0: Read-Only\nSummarize / Answer / Search"]
        LG --> T1["Tier 1: Staged Draft\n(Approval Required)"]
        LG --> T2["Tier 2: Governed Execution"]
        LG --> T3["Tier 3: PROHIBITED\n(File delete, payments)"]
    end

    T0 -->|Instant response| TTS
    T1 --> AG

    subgraph ActionGate["🛡️ Action Sandbox & Approval Gate"]
        AG["Approval Card\n[Enter: Approve | Esc: Reject]"]
        AG -->|Approved| Exec["Execute Action"]
        AG -->|10s countdown| Undo["Ctrl+Z Undo Buffer\n(10-second rollback window)"]
    end

    Exec --> Connectors

    subgraph Connectors["🔌 Connector Ecosystem"]
        Gmail["Gmail\n(draft, send, inbox)"]
        GCal["Google Calendar\n(schedule, find slots)"]
        GDrive["Google Drive\n(search, retrieve)"]
        MS365["Microsoft 365\n(Outlook, Teams, OneDrive)"]
        N8N["n8n Bridge\n(Slack, Jira, HubSpot,\nSalesforce, 400+ SaaS)"]
    end

    subgraph Intelligence["🧩 High-Value Intelligence Features"]
        Ghost["Ghost Follow-Up Radar\n(Outbound promises +\nInbound awaiting)"]
        Meeting["Meeting-Mode Auto-Ducking\n+ Pre-Meeting Dossier\n(2-min briefing)"]
        Clipboard["Clipboard Augmenter\n(Ctrl+Shift+V)\nClean / Summarize / JSON"]
        Workspace["Project Workspaces\n(Freeze & Restore\nDesktop Context)"]
    end

    subgraph Memory["💾 4-Tier Memory & RAG"]
        L1["L1: Conversation Buffer\n(20 turns, in-RAM)"]
        L2["L2: Session Summary\n(SQLite, compressed)"]
        L3["L3: Semantic Memory\n(ChromaDB + nemotron-embed)"]
        L4["L4: Connector Index\n(Drive + Email + OneDrive)"]
        Search["Hybrid Search\nBM25 + Dense + Rerank"]
        L3 --> Search
        L4 --> Search
    end

    LG <--> Memory
    LG --> Intelligence

    subgraph TTS_Pipeline["🔊 TTS Voice Output"]
        TTS["Kokoro-82M\n(chunk streaming\n<150ms first chunk)"] -->|Audio chunks| AEC
        AEC["Acoustic Echo\nCancellation"] --> Speaker["🔈 Speaker Output"]
        TTS -.->|Fallback| CartesiaSonic["Cartesia Sonic API"]
    end

    Speaker --> AS
```

---

### 10.2 User Interaction Flow — From First Boot to Active Use

```mermaid
flowchart TD
    Start(["🚀 First Launch"]) --> OB

    subgraph Onboarding["📋 First-Run Onboarding (One-Time Setup)"]
        OB["Welcome Screen\n+ MITRA Pitch"] --> PC
        PC["Permission Consent Modal\n✅ Microphone\n✅ Screen Capture\n✅ Connector Auth (opt-in)"] --> Auth
        Auth{"Choose Login"} -->|Google| GAuth["Google OAuth PKCE\n→ Gmail + Calendar + Drive"]
        Auth -->|Microsoft| MAuth["MS 365 OAuth PKCE\n→ Outlook + OneDrive + Teams"]
        Auth -->|Apple| AAuth["Apple ID Login"]
        GAuth & MAuth & AAuth --> VP_Setup
        VP_Setup["🎙️ Voiceprint Calibration\n3 prompts recorded:\n1. Hey Mitra, what's on my screen?\n2. Okay Mitra, follow up on this email.\n3. Hey Mitra, remind me at 4 PM."] --> VP_Store
        VP_Store["192-dim embedding\nstored encrypted in SQLite"] --> N8N_Setup
        N8N_Setup["n8n Webhook URL\nConfiguration (optional)"] --> Done
        Done["🎉 Setup Complete!\nMITRA enters Idle Sleep"] --> Idle
    end

    Idle["💤 Idle Sleep\n(Ring buffer only, <0.8% CPU)"]

    Idle -->|'Hey Mitra' / 'Okay Mitra'| WW_Stage1
    Idle -->|Ctrl+Space hotkey| Active

    subgraph WakeFlow["🔔 Wake Sequence"]
        WW_Stage1["Stage 1: Keyword Spotter\n(ONNX, local)"] -->|Match| WW_Stage2
        WW_Stage2["Stage 2: Voiceprint Verify\n(cosine similarity >0.82)"] -->|Identity confirmed| Active
        WW_Stage2 -->|Unknown speaker| WW_Reject["Rejected silently\n(ring buffer overwritten)"]
        WW_Reject --> Idle
    end

    Active["🟢 Active Listening\n(Pill expands + green ring glow)"]
    Active --> Speaking

    Speaking["🗣️ User Speaks"] --> VAD_End
    VAD_End["VAD Endpointing\n(700ms silence detected)"] --> STT_Proc

    subgraph Processing["⚡ Processing Pipeline"]
        STT_Proc["STT: Parakeet-TDT\n→ Transcript <150ms"] --> Guard
        Guard["NemoGuard Safety Check\n<200ms"] --> Intent
        Intent{"Intent Classification"} -->|Screen question| Screen_Cap
        Intent -->|Calendar request| Cal_Action
        Intent -->|Email request| Email_Action
        Intent -->|General question| Fast_LLM
        Intent -->|Complex reasoning| Deep_LLM
        Intent -->|Search my files| Search_Action

        Screen_Cap["📸 HWND Screen Capture\n(DXGI, on-demand only)\n→ Privacy masked WebP"] --> Vision_LLM
        Vision_LLM["llama-3.2-11b-vision\nScreen analysis"]

        Fast_LLM["nemotron-super-120b\n<400ms TTFT"]
        Deep_LLM["nemotron-ultra-550b\nThink mode"]
        Search_Action["Hybrid Semantic Search\nAll connected sources"]
    end

    Vision_LLM & Fast_LLM & Deep_LLM & Search_Action --> Response

    subgraph ResponseFlow["💬 Response & Actions"]
        Response{"Response Type"} -->|Answer / Info| TTS_Stream
        Response -->|Action Required| Approval_Card

        Approval_Card["📋 Approval Card appears in pill\n[Enter: Approve] [Esc: Reject] [Space: Edit]"] -->|Approved| Execute
        Approval_Card -->|Rejected| Discard["Action discarded"]

        Execute["Action Executed\n(Email sent / Event created / n8n triggered)"] --> Undo_Toast
        Undo_Toast["⏱️ 10-second Undo Toast\n[Ctrl+Z to rollback]"] --> TTS_Stream

        TTS_Stream["🔊 Kokoro-82M TTS\nChunk streaming <150ms first audio"]
    end

    TTS_Stream --> KA

    subgraph KeepAlive["🔄 8-Second Keep-Alive Window"]
        KA["MITRA Listening\n(no wake word needed)"] -->|User speaks within 8s| Speaking
        KA -->|8 seconds of silence| Auto_Sleep
    end

    Auto_Sleep["😴 Auto-Sleep\n(Audio streams closed\nPill minimizes)"] --> Idle

    subgraph BGIntelligence["🔮 Always-On Background Intelligence"]
        BG1["Ghost Follow-Up Radar\n(scanning emails 24/7)"]
        BG2["Calendar Event Monitor\n(pre-meeting dossier at -2min)"]
        BG3["Commitment Deadline Tracker\n(alerts 1hr before deadline)"]
        BG4["Incremental Re-indexer\n(30-min background sync)"]
        BG5["WASAPI Meeting Detector\n(Zoom/Teams auto-duck)"]
    end

    Idle --> BGIntelligence
    BGIntelligence -->|Alert / Notification| Pill_Pulse["💛 Pill pulses yellow\n(ambient notification)"]
    Pill_Pulse -->|User clicks| Active

    subgraph SpecialModes["🎨 Special Interaction Modes"]
        Clipboard_Mode["📋 Clipboard Augmenter\nCtrl+Shift+V → transform options"]
        Screen_Glance["👁️ Screen Glance\n'What's on my screen?'"]
        Meeting_Mode["🔇 Meeting Mode\n(TTS muted, card-only output)"]
        Workspace_Mode["💼 Workspace Snapshot\n'Save / Restore workspace'"]
    end
```

---

### 10.3 Action Safety Tier Flowchart

```mermaid
flowchart LR
    Input["User Request\nor Tool Call"] --> Safety

    Safety["🛡️ NemoGuard\nSafety Check"] -->|Flagged as unsafe| Block["❌ Blocked\nUser notified"]
    Safety -->|Clean| Tier

    Tier{"Action\nTier"}

    Tier -->|Tier 0: Read-Only| T0["✅ Execute immediately\nNo confirmation needed\n\nExamples:\n• Summarize screen\n• Answer question\n• Search memory\n• OCR document"]

    Tier -->|Tier 1: Staged Draft| T1["📋 Show Approval Card\nUser must confirm\n\nExamples:\n• Draft email\n• Create calendar event\n• Trigger n8n webhook\n• Create Jira ticket"]

    T1 -->|Approved| T1_Exec["✅ Execute\n+ 10s Undo Toast"]
    T1 -->|Rejected| T1_Discard["❌ Discard"]
    T1_Exec -->|Ctrl+Z within 10s| Rollback["↩️ Rollback\nAction reversed"]
    T1_Exec -->|10s expires| Committed["⚠️ Committed\nCannot undo"]

    Tier -->|Tier 2: Governed Execution| T2["⚙️ Execute with logging\n+ audit trail\n\nExamples:\n• File organization\n• Tag emails\n• Update CRM record"]

    Tier -->|Tier 3: Prohibited| T3["🚫 Hard Blocked\nAlways refused\n\nExamples:\n• System settings change\n• File deletion\n• Automated payments\n• Security config changes"]
```

---

### 10.4 Ghost Follow-Up Radar Flow

```mermaid
flowchart TD
    Email_Scan["📧 Email Scanner\n(Background, every 15 min)"] --> NLP

    NLP["NLP Commitment Extractor\n(nemotron-super-120b)"] --> Classify

    Classify{"Direction?"} -->|Outbound: I promised| Out_Track
    Classify -->|Inbound: They promised| In_Track

    Out_Track["📤 Outbound Commitment Stored\nparty, description, due_date, status=PENDING"] --> Out_Monitor
    In_Track["📥 Inbound Commitment Stored\nparty, description, due_date, status=AWAITING"] --> In_Monitor

    Out_Monitor["⏰ Deadline Monitor\n(running every 5 min)"] -->|1 hour before deadline| Out_Alert
    In_Monitor["⏳ Overdue Checker"] -->|Past due_date, no follow-up| In_Alert

    Out_Alert["🟡 Pill pulses yellow\n'You promised to send X to John by 4 PM'\n[Mark Done] [Snooze 30min] [Draft Update]"]
    In_Alert["🔴 Pill pulses red\n'Sarah was supposed to send pricing by Wednesday'\n[Draft Follow-Up] [Mark Resolved] [Snooze]"]

    Out_Alert -->|Draft Update clicked| Draft_Out["✍️ Generate polite update email\n→ Approval Card → Gmail Draft"]
    In_Alert -->|Draft Follow-Up clicked| Draft_In["✍️ Generate polite follow-up email\n→ Approval Card → Gmail Draft"]
```
