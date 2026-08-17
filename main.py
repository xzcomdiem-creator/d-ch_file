import os
import shutil
import tempfile
import uuid

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from services.document_processor import translate_document, _ext
from services.video_dubber import dub_video

app = FastAPI(title="Translate & Dub Tool")

# Khi deploy thật: nên thay ["*"] bằng domain frontend cụ thể của bạn, vd:
# allow_origins=["https://ten-web-cua-ban.vercel.app"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WORK_DIR = os.path.join(tempfile.gettempdir(), "translate-dub-tool")
os.makedirs(WORK_DIR, exist_ok=True)


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/api/translate-document")
async def api_translate_document(file: UploadFile = File(...), target_lang: str = Form(...)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".txt", ".docx", ".pdf"):
        raise HTTPException(400, f"Định dạng {ext} chưa được hỗ trợ. Chỉ hỗ trợ .txt, .docx, .pdf")

    job_id = str(uuid.uuid4())
    input_path = os.path.join(WORK_DIR, f"{job_id}_input{ext}")
    output_path = os.path.join(WORK_DIR, f"{job_id}_output{ext}")

    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        translate_document(input_path, output_path, target_lang)
    except Exception as e:
        raise HTTPException(500, f"Lỗi khi dịch file: {e}")
    finally:
        os.remove(input_path)

    filename = f"translated_{file.filename}"
    return FileResponse(output_path, filename=filename, media_type="application/octet-stream")


@app.post("/api/dub-video")
async def api_dub_video(
    video: UploadFile = File(...),
    subtitle: UploadFile = File(...),
    target_lang: str = Form(...),
    voice_id: str = Form(None),
):
    video_ext = os.path.splitext(video.filename)[1].lower()
    sub_ext = os.path.splitext(subtitle.filename)[1].lower()
    if sub_ext not in (".srt", ".vtt"):
        raise HTTPException(400, "File phụ đề phải là .srt hoặc .vtt")

    job_id = str(uuid.uuid4())
    video_path = os.path.join(WORK_DIR, f"{job_id}_video{video_ext}")
    sub_path = os.path.join(WORK_DIR, f"{job_id}_sub{sub_ext}")
    output_path = os.path.join(WORK_DIR, f"{job_id}_dubbed{video_ext}")

    with open(video_path, "wb") as f:
        shutil.copyfileobj(video.file, f)
    with open(sub_path, "wb") as f:
        shutil.copyfileobj(subtitle.file, f)

    try:
        dub_video(video_path, sub_path, target_lang, output_path, voice_id=voice_id or None)
    except Exception as e:
        raise HTTPException(500, f"Lỗi khi lồng tiếng video: {e}")
    finally:
        os.remove(video_path)
        os.remove(sub_path)

    filename = f"dubbed_{video.filename}"
    return FileResponse(output_path, filename=filename, media_type="video/mp4")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
