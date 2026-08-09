"""Tests for OpenSubtitles result mapping and ranking."""

from app.services.opensubtitles import map_subtitles


def test_subtitle_mapping_prefers_srt_then_rating_and_downloads() -> None:
    payload = {
        "data": [
            {
                "attributes": {
                    "files": [{"file_id": 2, "file_name": "film.ass"}],
                    "release": "BluRay",
                    "download_count": 100,
                }
            },
            {
                "attributes": {
                    "files": [{"file_id": 1, "file_name": "film.srt"}],
                    "release": "WEBRip 1080p",
                    "hearing_impaired": True,
                    "download_count": 20,
                    "ratings": 8.5,
                    "uploader": {"name": "trusted-uploader"},
                }
            },
        ]
    }

    results = map_subtitles(payload)

    assert [result.file_id for result in results] == [1, 2]
    assert results[0].format == "srt"
    assert results[0].hearing_impaired is True
    assert results[0].uploader == "trusted-uploader"
