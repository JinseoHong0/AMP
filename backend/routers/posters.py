from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.poster_schemas import PosterExtraction
from backend.services.poster_parser import review_extraction
from backend.services.poster_uploads import MAX_FILE_BYTES, validate_image
from backend.services.venue_matcher import match_venue

router = APIRouter(prefix="/api/posters", tags=["posters"])


@router.post("/parse", response_model=PosterExtraction)
async def parse_poster(request: Request, file: Annotated[UploadFile, File()]):
    try:
        content = await file.read(MAX_FILE_BYTES + 1)
        image = await run_in_threadpool(validate_image, content, file.content_type)
    finally:
        await file.close()
    # Check DB readiness before spending an AI request; an absent DB is not "no matching venue".
    venues = await run_in_threadpool(request.app.state.venue_repository.list_venues)
    raw = await request.app.state.poster_client.extract(image.content, image.mime_type)
    extracted, needs_review, warnings = review_extraction(raw)
    venue_match = match_venue(extracted.venue_name, venues)
    if venue_match.status != "matched":
        needs_review.append("venue_id")
        warnings.append("기존 공연장을 자동 확정하지 못했습니다. 목록에서 직접 선택해 주세요.")
    # No event/venue/translation is created here. Only successful parses retain an upload.
    upload_id = await run_in_threadpool(request.app.state.upload_store.save, image)
    return PosterExtraction(
        upload_id=upload_id,
        extracted=extracted,
        venue_match=venue_match,
        needs_review=list(dict.fromkeys(needs_review)),
        warnings=warnings,
    )
