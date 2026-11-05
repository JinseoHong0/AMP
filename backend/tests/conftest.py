import json
import re
import sqlite3
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import Settings
from backend.main import create_app
from backend.poster_schemas import VisionResult


@pytest.fixture
def vision_result():
    markdown = (Path(__file__).resolve().parents[2] / "docs/API.md").read_text()
    examples = [json.loads(value) for value in re.findall(r"```json\n(.*?)\n```", markdown, re.S)]
    example = next(item for item in examples if "extracted" in item)
    return VisionResult(
        extracted=example["extracted"],
        date_has_explicit_year=True,
        multiple_schedules=False,
        warnings=[],
    )


@pytest.fixture
def image_bytes():
    # Encoding a tiny test image exercises the actual decoder. No runtime demo assets.
    def make(format_name="PNG"):
        stream = BytesIO()
        Image.new("RGB", (24, 24), "white").save(stream, format=format_name)
        return stream.getvalue()

    return make


@pytest.fixture
def app(tmp_path, vision_result):
    db = tmp_path / "amp.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE venues (id INTEGER PRIMARY KEY, name TEXT, area TEXT)")
        connection.execute(
            "INSERT INTO venues VALUES (1, ?, 'sinchon')", (vision_result.extracted.venue_name,)
        )
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{db}",
        upload_dir=tmp_path / "uploads",
        local_demo=True,
        gemini_api_key="",
        gemini_model="",
    )
    application = create_app(settings)
    application.state.poster_client.extract = AsyncMock(return_value=vision_result)
    return application


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as client:
        yield client
