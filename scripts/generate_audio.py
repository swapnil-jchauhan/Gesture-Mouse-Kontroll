import asyncio
import os
import edge_tts

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

VOICE = "en-GB-RyanNeural"

PHRASES = {
    "boot_morning.mp3": "Good morning. Systems online sir.",
    "boot_afternoon.mp3": "Good afternoon. Systems online sir.",
    "boot_evening.mp3": "Good evening. Systems online sir.",
    "control_activated.mp3": "Virtual Control has been activated sir.",
    "control_deactivated.mp3": "Virtual Control has been deactivated sir.",
}

async def generate():
    for filename, text in PHRASES.items():
        out_path = os.path.join(AUDIO_DIR, filename)
        print(f"Generating {filename}: {text}")
        comm = edge_tts.Communicate(text, VOICE)
        await comm.save(out_path)
        print(f"Saved {out_path} ({os.path.getsize(out_path)} bytes)")

if __name__ == "__main__":
    asyncio.run(generate())
