"""
Speech-to-text (Whisper) via the Hugging Face Inference API.
Pure-Python dependency (huggingface_hub), so it installs fine on Python 3.14.

    pip install huggingface_hub
"""
import os

import config

STT_MODEL = os.getenv("STT_MODEL", "openai/whisper-large-v3")


def transcribe(audio_path: str) -> str:
    """Return the text spoken in an audio file (wav/mp3/flac...). Hindi, Marathi, English etc. are auto-detected."""
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if config.MOCK_LLM:                       # offline wiring test: no API call
        return "[mock transcript] मुझे सुबह से सिरदर्द है"

    if not config.HF_TOKEN:
        raise RuntimeError("HF_TOKEN is not set. Run: set HF_TOKEN=hf_...  (Windows)  or  export HF_TOKEN=hf_...")

    from huggingface_hub import InferenceClient
    client = InferenceClient(provider="hf-inference", api_key=config.HF_TOKEN)
    result = client.automatic_speech_recognition(audio_path, model=STT_MODEL)
    return (getattr(result, "text", None) or str(result)).strip()
