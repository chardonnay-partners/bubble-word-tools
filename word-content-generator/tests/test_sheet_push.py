import json

from wcg.commands import sheet_push
from wcg.core.sheet import SheetPushError

CSV = ("Key,English(en),Turkish(tr)\n"
       "planets,Planets,Gezegenler\n"
       "planets.mars,Mars,Mars\n")


def setup_dirs(tmp_path, with_config=True, with_csv=True):
    config = tmp_path / "config"
    config.mkdir()
    if with_config:
        (config / "sheet.json").write_text(json.dumps(
            {"webhook_url": "https://example.test/exec", "token": "tok"}),
            encoding="utf-8")
    csv_path = tmp_path / "localization.csv"
    if with_csv:
        csv_path.write_text(CSV, encoding="utf-8")
    return config, csv_path


def test_pushes_all_csv_rows(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_push(rows, url, token):
        calls.append((rows, url, token))
        return {"inserted": 1, "skipped": 1}

    monkeypatch.setattr("wcg.commands.sheet_push.push_rows", fake_push)
    config, csv_path = setup_dirs(tmp_path)
    assert sheet_push.run(config, csv_path) == 0
    rows, url, token = calls[0]
    assert rows == [["planets", "Planets", "Gezegenler"],
                    ["planets.mars", "Mars", "Mars"]]
    assert url == "https://example.test/exec"
    assert token == "tok"
    out = capsys.readouterr().out
    assert "1 inserted" in out
    assert "1 already in sheet" in out


def test_missing_config_returns_2(tmp_path, capsys):
    config, csv_path = setup_dirs(tmp_path, with_config=False)
    assert sheet_push.run(config, csv_path) == 2
    assert "sheet.json" in capsys.readouterr().out


def test_missing_csv_returns_2(tmp_path, capsys):
    config, csv_path = setup_dirs(tmp_path, with_csv=False)
    assert sheet_push.run(config, csv_path) == 2
    assert "localization.csv" in capsys.readouterr().out


def test_push_error_returns_1(tmp_path, monkeypatch, capsys):
    def fake_push(rows, url, token):
        raise SheetPushError("invalid token")

    monkeypatch.setattr("wcg.commands.sheet_push.push_rows", fake_push)
    config, csv_path = setup_dirs(tmp_path)
    assert sheet_push.run(config, csv_path) == 1
    assert "invalid token" in capsys.readouterr().out
