"""
Service dịch văn bản, dùng Claude API (Anthropic).
Có thể thay bằng Google Translate API nếu muốn rẻ hơn / nhanh hơn cho văn bản dài.
"""
import os
from anthropic import Anthropic

_client = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Thiếu ANTHROPIC_API_KEY. Hãy set biến môi trường này (xem file .env.example)."
            )
        _client = Anthropic(api_key=api_key)
    return _client


def translate_text(text: str, target_lang: str, source_lang: str = "auto", context: str = "") -> str:
    """
    Dịch một đoạn văn bản sang ngôn ngữ đích.
    target_lang: tên ngôn ngữ, vd "Tiếng Việt", "English", "Japanese"...
    context: gợi ý thêm về ngữ cảnh (vd "đây là phụ đề video, giữ câu ngắn gọn tự nhiên khi nói")
    """
    if not text.strip():
        return text

    system_prompt = (
        f"Bạn là một biên dịch viên chuyên nghiệp. Dịch văn bản người dùng đưa sang "
        f"{target_lang}. CHỈ trả về bản dịch, không thêm giải thích, không thêm ghi chú, "
        f"không lặp lại văn bản gốc. Giữ nguyên định dạng xuống dòng nếu có."
    )
    if context:
        system_prompt += f" Ngữ cảnh: {context}"

    client = get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": text}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


def translate_batch(texts: list[str], target_lang: str, context: str = "") -> list[str]:
    """
    Dịch nhiều đoạn cùng lúc bằng cách gộp thành 1 request có đánh số,
    giúp tiết kiệm số lần gọi API cho file dài / phụ đề nhiều dòng.
    """
    if not texts:
        return []

    # Gộp theo lô nhỏ để tránh vượt giới hạn token và giữ độ chính xác khớp số thứ tự
    BATCH_SIZE = 40
    results: list[str] = []

    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i:i + BATCH_SIZE]
        numbered = "\n".join(f"[{idx}] {t}" for idx, t in enumerate(chunk))

        system_prompt = (
            f"Bạn là biên dịch viên chuyên nghiệp. Dưới đây là danh sách các câu được đánh số "
            f"dạng [n]. Dịch TỪNG câu sang {target_lang}, giữ NGUYÊN định dạng [n] ở đầu mỗi dòng "
            f"kết quả, theo đúng thứ tự, không gộp không tách dòng, không thêm giải thích."
        )
        if context:
            system_prompt += f" Ngữ cảnh: {context}"

        client = get_client()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": numbered}],
        )
        raw = "".join(block.text for block in response.content if block.type == "text").strip()

        # Parse lại theo [n]
        parsed = {}
        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("[") and "]" in line:
                idx_str, _, rest = line.partition("]")
                try:
                    idx = int(idx_str[1:])
                    parsed[idx] = rest.strip()
                except ValueError:
                    continue

        for idx in range(len(chunk)):
            results.append(parsed.get(idx, chunk[idx]))  # fallback: giữ nguyên nếu parse lỗi

    return results
