"""
Service Text-to-Speech. Mặc định dùng ElevenLabs (chất lượng giọng tự nhiên, hỗ trợ
đa ngôn ngữ tốt). Có thể tự thêm provider khác (Google Cloud TTS, Azure TTS...)
bằng cách viết thêm hàm và đổi TTS_PROVIDER trong .env.
"""
import os
import requests

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

# Giọng mặc định đa ngôn ngữ của ElevenLabs (model eleven_multilingual_v2).
# Bạn có thể đổi voice_id theo giọng mình thích trong tài khoản ElevenLabs.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" - giọng nữ mặc định


def synthesize_speech(text: str, output_path: str, voice_id: str = DEFAULT_VOICE_ID) -> str:
    """Gọi ElevenLabs API để tạo file audio (mp3) từ văn bản, lưu vào output_path."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("Thiếu ELEVENLABS_API_KEY. Hãy set biến môi trường này (xem .env.example).")

    if not text.strip():
        # Tạo file audio im lặng ngắn nếu không có text (tránh lỗi pipeline)
        text = " "

    resp = requests.post(
        ELEVENLABS_TTS_URL.format(voice_id=voice_id),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=60,
    )
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(resp.content)

    return output_path
