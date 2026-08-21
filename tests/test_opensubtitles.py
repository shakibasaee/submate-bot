"""OpenSubtitles normalization contract tests."""

from app.domain.languages import LanguageCode
from app.domain.models import MovieRef
from app.domain.subtitles import ProviderId, SubtitleQuery
from app.infrastructure.providers.opensubtitles import map_subtitles


def test_all_provider_files_are_normalized_with_provider_identity() -> None:
    payload: dict[str, object] = {
        "data": [
            {
                "attributes": {
                    "files": [
                        {"file_id": 1, "file_name": "film.srt"},
                        {"file_id": 2, "file_name": "film-forced.srt"},
                    ],
                    "release": "WEBRip",
                    "foreign_parts_only": True,
                    "hearing_impaired": False,
                    "download_count": 20,
                    "ratings": 8.5,
                    "uploader": {"name": "trusted"},
                }
            }
        ]
    }
    results = map_subtitles(
        payload,
        SubtitleQuery(MovieRef("27205", "Inception"), LanguageCode.ENGLISH),
    )
    assert [item.provider_file_ref for item in results] == ["1", "2"]
    assert all(item.provider_id == ProviderId("opensubtitles") for item in results)
    assert all(item.forced for item in results)
    assert results[0].uploader == "trusted"
