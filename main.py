from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from pypdf import PdfReader

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to my API!"}



def _ensure_pdf(upload: UploadFile) -> None:
    content_type = (upload.content_type or "").lower()
    if content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Unsupported media type. Upload a PDF file.")


def _extract_text(reader: PdfReader) -> str:
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
    return "\n".join(parts)


def _clean_text(text: str) -> str:
    text = " ".join(text.split())
    text = text.replace(" \n ", "\n").replace(" \n", "\n").replace("\n ", "\n")
    while "\n\n" in text:
        text = text.replace("\n\n", "\n")
    return text.strip()


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, object]:
    _ensure_pdf(file)

    try:
        reader = PdfReader(file.file)
        raw_text = _extract_text(reader)
        cleaned_text = _clean_text(raw_text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Failed to read PDF.") from exc

    return {
        "total_characters": len(cleaned_text),
        "preview": cleaned_text[:1000],
    }


# requirements.txt
# fastapi
# uvicorn[standard]
# python-multipart
# pypdf
#h
