from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

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


def _build_prompt(text_sample: str) -> str:
    return (
        "You are an academic study assistant.\n"
        "Analyze the provided text and return only valid JSON with this exact schema:\n"
        "{\n"
        '  "key_concepts": ["..."],\n'
        '  "important_definitions": [{"term": "...", "definition": "..."}],\n'
        '  "possible_exam_questions": ["..."],\n'
        '  "quick_revision_points": ["..."]\n'
        "}\n"
        "Rules:\n"
        "1) Do not include markdown, code fences, or extra text.\n"
        "2) Keep responses concise and useful for study.\n"
        "3) Ensure strict JSON output.\n\n"
        "Text to analyze:\n"
        f"{text_sample}"
    )


def _generate_structured_summary(text_sample: str) -> dict[str, object]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY environment variable.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You produce structured study notes in strict JSON."},
            {"role": "user", "content": _build_prompt(text_sample)},
        ],
        "temperature": 0.2,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "study_summary",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "key_concepts": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "important_definitions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "term": {"type": "string"},
                                    "definition": {"type": "string"},
                                },
                                "required": ["term", "definition"],
                                "additionalProperties": False,
                            },
                        },
                        "possible_exam_questions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "quick_revision_points": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "key_concepts",
                        "important_definitions",
                        "possible_exam_questions",
                        "quick_revision_points",
                    ],
                    "additionalProperties": False,
                },
            },
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8")
        except Exception:  # noqa: BLE001
            error_body = ""
        raise HTTPException(
            status_code=502,
            detail=f"AI provider returned an error: {error_body or str(exc)}",
        ) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail="Failed to reach AI provider.") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Unexpected AI request failure.") from exc

    try:
        content = response_data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Invalid AI response format.") from exc


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, object]:
    _ensure_pdf(file)

    try:
        reader = PdfReader(file.file)
        raw_text = _extract_text(reader)
        cleaned_text = _clean_text(raw_text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Failed to read PDF.") from exc

    text_sample = cleaned_text[:3000]
    if not text_sample:
        raise HTTPException(status_code=400, detail="No extractable text found in the PDF.")

    structured_summary = _generate_structured_summary(text_sample)

    return {
        "total_characters": len(cleaned_text),
        "structured_summary": structured_summary,
    }
