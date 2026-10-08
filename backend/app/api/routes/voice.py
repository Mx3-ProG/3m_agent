import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from backend.app.core.config import get_settings
from backend.app.security.auth import require_api_token

router = APIRouter(prefix="/voice", tags=["voice"], dependencies=[Depends(require_api_token)])


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1)


@router.post("/synthesize")
async def synthesize(payload: SpeechRequest) -> Response:
    settings = get_settings()
    if len(payload.text) > settings.max_tts_characters:
        raise HTTPException(status_code=413, detail="Texte trop long pour la synthèse vocale")
    key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not key or not voice_id:
        raise HTTPException(status_code=503, detail="ElevenLabs n’est pas configuré")
    model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": key, "Accept": "audio/mpeg"},
            json={"text": payload.text, "model_id": model_id},
        )
    if response.is_error:
        raise HTTPException(status_code=502, detail="La synthèse ElevenLabs a échoué")
    return Response(response.content, media_type="audio/mpeg")
