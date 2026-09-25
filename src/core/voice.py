"""
Project Kontroll: Jarvis British Voice Synthesizer & Zero-Lag Audio Subsystem.
Uses Microsoft Edge TTS (en-GB-RyanNeural) with local asset caching and
instantaneous background playback via Windows native multimedia MCI.
"""

import os
import sys
import time
import datetime
import threading
import ctypes
from typing import Optional

# Voice Configuration
VOICE_NAME = "en-GB-RyanNeural"

# Locate assets/audio relative to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUDIO_DIR = os.path.join(PROJECT_ROOT, "assets", "audio")

VOICE_PHRASES = {
    "boot_morning.mp3": "Good morning. Systems online sir.",
    "boot_afternoon.mp3": "Good afternoon. Systems online sir.",
    "boot_evening.mp3": "Good evening. Systems online sir.",
    "control_activated.mp3": "Virtual Control has been activated sir.",
    "control_deactivated.mp3": "Virtual Control has been deactivated sir.",
}


def get_boot_greeting_type(dt: Optional[datetime.datetime] = None) -> str:
    """Determines morning, afternoon, or evening based on local hour."""
    if dt is None:
        dt = datetime.datetime.now()
    hour = dt.hour
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    else:
        return "evening"


def get_boot_greeting_text(dt: Optional[datetime.datetime] = None) -> str:
    """Returns the time-appropriate British voice greeting text."""
    greeting_type = get_boot_greeting_type(dt)
    if greeting_type == "morning":
        return "Good morning. Systems online sir."
    elif greeting_type == "afternoon":
        return "Good afternoon. Systems online sir."
    else:
        return "Good evening. Systems online sir."


def get_boot_audio_path(dt: Optional[datetime.datetime] = None) -> str:
    """Returns absolute path to the cached boot greeting audio file."""
    greeting_type = get_boot_greeting_type(dt)
    filename = f"boot_{greeting_type}.mp3"
    return os.path.join(AUDIO_DIR, filename)


def get_activation_audio_path(is_active: bool) -> str:
    """Returns absolute path to the Shaka toggle audio file."""
    filename = "control_activated.mp3" if is_active else "control_deactivated.mp3"
    return os.path.join(AUDIO_DIR, filename)


class VoicePlayer:
    """
    Zero-latency, thread-safe Windows multimedia MCI voice synthesizer player.
    Supports instant audio playback, graceful interruption of prior phrases,
    and automatic cleanup of MCI device handles.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._current_alias: Optional[str] = None
        self._alias_counter = 0

    def play(self, file_path: str):
        """Plays an audio file instantaneously without blocking the UI thread."""
        def _play_worker():
            abs_path = os.path.abspath(file_path)
            if not os.path.exists(abs_path):
                _generate_single_phrase(abs_path)
                if not os.path.exists(abs_path):
                    return

            winmm = ctypes.windll.winmm

            with self._lock:
                # 1. Stop and close any previous playing alias immediately
                if self._current_alias:
                    try:
                        winmm.mciSendStringW(f'stop {self._current_alias}', None, 0, None)
                        winmm.mciSendStringW(f'close {self._current_alias}', None, 0, None)
                    except Exception:
                        pass
                    self._current_alias = None

                # 2. Allocate guaranteed-unique alias name
                self._alias_counter += 1
                alias = f"kontroll_voice_{self._alias_counter}"

                # 3. Determine short path or properly quoted path
                buf = ctypes.create_unicode_buffer(500)
                ctypes.windll.kernel32.GetShortPathNameW(abs_path, buf, 500)
                path_to_open = buf.value if buf.value else abs_path

                # 4. Open MCI mpegvideo device
                cmd_open = f'open "{path_to_open}" type mpegvideo alias {alias}'
                res_open = winmm.mciSendStringW(cmd_open, None, 0, None)
                if res_open != 0:
                    # Fallback to direct path without quotes if short path
                    cmd_open_fallback = f'open {path_to_open} type mpegvideo alias {alias}'
                    res_open = winmm.mciSendStringW(cmd_open_fallback, None, 0, None)
                    if res_open != 0:
                        return

                # 5. Play asynchronously (non-blocking)
                res_play = winmm.mciSendStringW(f'play {alias}', None, 0, None)
                if res_play == 0:
                    self._current_alias = alias
                else:
                    winmm.mciSendStringW(f'close {alias}', None, 0, None)
                    return

            # 6. Auto-close monitor in background
            self._monitor_playback(alias)

        threading.Thread(target=_play_worker, daemon=True).start()

    def _monitor_playback(self, alias: str):
        """Monitors playback in background and closes alias when stopped."""
        winmm = ctypes.windll.winmm
        buf = ctypes.create_unicode_buffer(100)
        while True:
            time.sleep(0.15)
            with self._lock:
                if self._current_alias != alias:
                    # Device was already stopped/closed by subsequent sound or stop()
                    return
                res = winmm.mciSendStringW(f'status {alias} mode', buf, 100, None)
                if res != 0 or buf.value != 'playing':
                    winmm.mciSendStringW(f'close {alias}', None, 0, None)
                    if self._current_alias == alias:
                        self._current_alias = None
                    return

    def stop(self):
        """Immediately halts and closes any currently active voice playback."""
        winmm = ctypes.windll.winmm
        with self._lock:
            if self._current_alias:
                try:
                    winmm.mciSendStringW(f'stop {self._current_alias}', None, 0, None)
                    winmm.mciSendStringW(f'close {self._current_alias}', None, 0, None)
                except Exception:
                    pass
                self._current_alias = None


_player = VoicePlayer()


def play_audio_file(file_path: str):
    """
    Plays an MP3 audio file instantaneously in a background daemon thread
    using native Windows multimedia MCI. Never blocks the UI or main thread.
    """
    _player.play(file_path)


def stop_audio():
    """Immediately halts and closes any active voice playback."""
    _player.stop()


def play_boot_greeting(dt: Optional[datetime.datetime] = None):
    """Plays the time-appropriate British greeting on system boot."""
    audio_path = get_boot_audio_path(dt)
    play_audio_file(audio_path)


def play_gesture_toggle_voice(is_active: bool):
    """Plays 'Virtual Control has been activated/deactivated sir' on Shaka gesture."""
    audio_path = get_activation_audio_path(is_active)
    play_audio_file(audio_path)


def _generate_single_phrase(file_path: str):
    """Generates a missing phrase file on demand using edge-tts if possible."""
    basename = os.path.basename(file_path)
    text = VOICE_PHRASES.get(basename)
    if not text:
        return
    try:
        import asyncio
        import edge_tts

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        comm = edge_tts.Communicate(text, VOICE_NAME)
        asyncio.run(comm.save(file_path))
    except Exception:
        pass


def ensure_voice_cache():
    """Validates that all required voice files exist in the cache directory."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    missing = [
        filename for filename in VOICE_PHRASES
        if not os.path.exists(os.path.join(AUDIO_DIR, filename))
    ]
    if missing:
        def _bg_generate():
            for filename in missing:
                _generate_single_phrase(os.path.join(AUDIO_DIR, filename))
        threading.Thread(target=_bg_generate, daemon=True).start()
