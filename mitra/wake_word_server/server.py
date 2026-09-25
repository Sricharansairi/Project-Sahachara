#!/usr/bin/env python3
"""
MITRA Wake Word Server — openWakeWord IPC Server
Listens on TCP 127.0.0.1:8765 for audio frames from the Rust backend.
Uses openWakeWord to detect "Hey Mitra" and "Okay Mitra".

Protocol:
  Client → Server: [4-byte LE length][JSON: {"samples": [f32, ...]}]
  Server → Client: [4-byte LE length][JSON: {"detected": bool, "phrase": str|null, "score": float|null}]
"""

import socket
import struct
import json
import sys
import logging
import threading
import numpy as np
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mitra.wakeword")

HOST = "127.0.0.1"
PORT = 8765

# Wake word phrases to detect (maps to openWakeWord model names)
WAKE_PHRASES = {
    "hey_mitra": 0.5,    # confidence threshold
    "okay_mitra": 0.5,
}

SAMPLE_RATE = 16000


def load_model():
    """Load openWakeWord model. Returns None if not available (dev stub mode)."""
    try:
        import openwakeword
        from openwakeword.model import Model

        log.info("Loading openWakeWord model...")
        model = Model(
            wakeword_models=list(WAKE_PHRASES.keys()),
            inference_framework="onnx",
        )
        log.info("✅ openWakeWord model loaded")
        return model
    except ImportError:
        log.warning(
            "⚠️  openWakeWord not installed. Running in STUB mode "
            "(always returns detected=False). "
            "Install with: pip install openwakeword"
        )
        return None
    except Exception as e:
        log.warning(f"⚠️  Could not load openWakeWord: {e}. Running in STUB mode.")
        return None


def detect_wake_word(model, samples: list[float]) -> dict:
    """
    Run wake word detection on the given audio samples.
    Returns a dict: {detected, phrase, score}
    """
    if model is None:
        # Stub: never detect (safe default)
        return {"detected": False, "phrase": None, "score": None}

    try:
        audio = np.array(samples, dtype=np.float32)

        # openWakeWord expects int16 PCM
        audio_int16 = (audio * 32767).astype(np.int16)

        prediction = model.predict(audio_int16)

        for phrase, threshold in WAKE_PHRASES.items():
            score = prediction.get(phrase, 0.0)
            if score >= threshold:
                log.info(f"🔔 DETECTED: '{phrase}' score={score:.3f}")
                return {"detected": True, "phrase": phrase, "score": float(score)}

        return {"detected": False, "phrase": None, "score": None}

    except Exception as e:
        log.error(f"Detection error: {e}")
        return {"detected": False, "phrase": None, "score": None}


def handle_client(conn: socket.socket, addr, model):
    """Handle a single client connection."""
    log.info(f"🔗 Client connected: {addr}")
    try:
        while True:
            # Read 4-byte length prefix
            len_data = recv_exactly(conn, 4)
            if not len_data:
                break
            msg_len = struct.unpack("<I", len_data)[0]

            # Read message body
            body = recv_exactly(conn, msg_len)
            if not body:
                break

            # Parse JSON
            msg = json.loads(body.decode("utf-8"))
            samples = msg.get("samples", [])

            # Run detection
            result = detect_wake_word(model, samples)

            # Send response
            resp_bytes = json.dumps(result).encode("utf-8")
            conn.sendall(struct.pack("<I", len(resp_bytes)))
            conn.sendall(resp_bytes)

    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    except Exception as e:
        log.error(f"Client error: {e}")
    finally:
        conn.close()
        log.info(f"❌ Client disconnected: {addr}")


def recv_exactly(conn: socket.socket, n: int) -> bytes | None:
    """Receive exactly n bytes from a socket."""
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def main():
    model = load_model()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)

    log.info(f"🚀 MITRA Wake Word Server listening on {HOST}:{PORT}")
    log.info(f"   Watching for phrases: {list(WAKE_PHRASES.keys())}")

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr, model), daemon=True)
            t.start()
    except KeyboardInterrupt:
        log.info("Server stopped.")
    finally:
        server.close()


if __name__ == "__main__":
    main()
