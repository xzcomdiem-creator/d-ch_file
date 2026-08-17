"""
Quy trình lồng tiếng video:
1. Đọc file phụ đề (.srt/.vtt) có sẵn -> lấy timestamp + text gốc
2. Dịch từng dòng phụ đề sang ngôn ngữ đích
3. Với mỗi dòng, tạo audio bằng TTS
4. Co giãn tốc độ audio (ffmpeg atempo) để khớp đúng khoảng thời gian của dòng phụ đề gốc
5. Ghép tất cả đoạn audio vào đúng vị trí trên 1 track audio dài bằng độ dài video
6. Dùng ffmpeg thay track audio của video gốc bằng track audio mới
"""
import os
import subprocess
import tempfile
import srt
from pydub import AudioSegment

from .translator import translate_batch
from .tts_service import synthesize_speech


def _parse_subtitle(path: str) -> list[srt.Subtitle]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # thư viện srt cũng đọc được vtt đơn giản nếu convert dấu thời gian, nhưng để chắc chắn
    # ta chỉ hỗ trợ .srt trực tiếp ở bản này. .vtt nên convert sang .srt trước (ffmpeg làm được).
    return list(srt.parse(content))


def _convert_vtt_to_srt(vtt_path: str, srt_path: str):
    subprocess.run(
        ["ffmpeg", "-y", "-i", vtt_path, srt_path],
        check=True, capture_output=True,
    )


def _adjust_audio_duration(audio_path: str, target_ms: int, out_path: str):
    """Co giãn tốc độ audio để khớp target_ms bằng ffmpeg atempo (0.5x - 2x mỗi lần, ghép nhiều lần nếu cần)."""
    audio = AudioSegment.from_file(audio_path)
    current_ms = len(audio)
    if current_ms <= 0:
        audio.export(out_path, format="mp3")
        return

    speed = current_ms / max(target_ms, 1)  # >1 nghĩa là audio đang dài hơn -> cần tăng tốc
    speed = max(0.5, min(speed, 2.0))  # giới hạn hợp lý để giọng không bị méo quá

    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.3f}")
    filter_str = ",".join(filters)

    subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-filter:a", filter_str, out_path],
        check=True, capture_output=True,
    )


def dub_video(video_path: str, subtitle_path: str, target_lang: str, output_path: str,
              voice_id: str | None = None) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        # 1. Chuẩn hoá phụ đề về .srt nếu là .vtt
        if subtitle_path.lower().endswith(".vtt"):
            srt_path = os.path.join(tmp, "subs.srt")
            _convert_vtt_to_srt(subtitle_path, srt_path)
        else:
            srt_path = subtitle_path

        subs = _parse_subtitle(srt_path)
        if not subs:
            raise ValueError("Không đọc được dòng phụ đề nào trong file.")

        # 2. Dịch toàn bộ
        original_texts = [s.content.replace("\n", " ") for s in subs]
        translated_texts = translate_batch(
            original_texts, target_lang,
            context="Đây là lời thoại lồng tiếng video, dịch tự nhiên như văn nói, câu ngắn gọn."
        )

        # 3+4. Tạo audio từng dòng và co giãn cho khớp timing
        segment_files = []
        for i, (sub, text) in enumerate(zip(subs, translated_texts)):
            raw_audio = os.path.join(tmp, f"raw_{i}.mp3")
            kwargs = {"voice_id": voice_id} if voice_id else {}
            synthesize_speech(text, raw_audio, **kwargs)

            duration_ms = int((sub.end - sub.start).total_seconds() * 1000)
            fitted_audio = os.path.join(tmp, f"fit_{i}.mp3")
            _adjust_audio_duration(raw_audio, duration_ms, fitted_audio)
            segment_files.append((sub.start.total_seconds(), fitted_audio))

        # 5. Ghép các đoạn vào 1 track audio dài bằng video, đặt đúng vị trí thời gian
        # Lấy tổng thời lượng video để tạo track nền im lặng
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            check=True, capture_output=True, text=True,
        )
        total_duration_ms = int(float(probe.stdout.strip()) * 1000)

        master_track = AudioSegment.silent(duration=total_duration_ms)
        for start_sec, seg_path in segment_files:
            seg_audio = AudioSegment.from_file(seg_path)
            start_ms = int(start_sec * 1000)
            master_track = master_track.overlay(seg_audio, position=start_ms)

        master_audio_path = os.path.join(tmp, "master_audio.mp3")
        master_track.export(master_audio_path, format="mp3")

        # 6. Thay track audio trong video gốc bằng track mới
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", master_audio_path,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest",
                output_path,
            ],
            check=True, capture_output=True,
        )

    return output_path
