from __future__ import annotations

import sqlite3
from pathlib import Path

from ludiglot.core import text_builder


def _create_blob_db(db_path: Path, rows: list[tuple[int, bytes]]) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("CREATE TABLE gachaviewinfo (Id INT NOT NULL, BinData BLOB)")
    cur.executemany("INSERT INTO gachaviewinfo (Id, BinData) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def test_pick_text_from_blob_prefers_human_text() -> None:
    blob = (
        b"/Game/Aki/UI/UIResources/Common/Image/Luckdraw/T_Test.T_Test\x00"
        b"Text_SummaryTitle999_Text\x00"
        b"Wanderer Knows No Far and Near\x00"
    )
    picked = text_builder._pick_text_from_blob(blob)
    assert picked == "Wanderer Knows No Far and Near"


def test_load_sqlite_map_extracts_text_from_bindata(tmp_path: Path) -> None:
    db_path = tmp_path / "db_gacha.db"
    blob = (
        b"/Game/Aki/UI/UIResources/Common/Image/Luckdraw/T_Test.T_Test\x00"
        b"Text_SummaryTitle999_Text\x00"
        b"Wanderer Knows No Far and Near\x00"
    )
    _create_blob_db(db_path, [(1001, blob)])

    mapping = text_builder._load_sqlite_map(db_path)
    assert mapping.get("1001") == "Wanderer Knows No Far and Near"


def test_build_text_db_from_root_all_includes_root_gacha_db(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configdb = tmp_path / "ConfigDB"
    configdb.mkdir(parents=True, exist_ok=True)

    db_path = configdb / "db_gacha.db"
    title = "Wanderer Knows No Far and Near"
    blob = (
        b"/Game/Aki/UI/UIResources/Common/Image/Luckdraw/T_Test.T_Test\x00"
        b"Text_SummaryTitle999_Text\x00"
        + title.encode("ascii")
        + b"\x00"
    )
    _create_blob_db(db_path, [(1001, blob)])

    monkeypatch.setattr(
        text_builder,
        "build_voice_map_from_configdb",
        lambda *args, **kwargs: {},
    )

    db = text_builder.build_text_db_from_root_all(tmp_path)
    key = text_builder.normalize_en(title)

    assert key in db
    matches = db[key].get("matches", [])
    assert matches, "expected at least one match from root db_gacha.db"
    assert matches[0].get("official_en") == title
    assert matches[0].get("source_json") == "db_gacha.db"
