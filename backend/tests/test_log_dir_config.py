import importlib
import sys


def _reload_module(name: str):
    module = sys.modules.get(name)
    if module is not None:
        return importlib.reload(module)
    return importlib.import_module(name)


def test_replay_logger_uses_app_log_dir_env(tmp_path, monkeypatch):
    custom_log_dir = tmp_path / "render-logs"
    monkeypatch.setenv("APP_LOG_DIR", str(custom_log_dir))

    replay_logger = _reload_module("app.services.replay_logger")

    assert replay_logger.LOG_DIR == str(custom_log_dir)
    assert replay_logger.REPLAY_LOG_DIR == str(custom_log_dir / "replay")
    assert (custom_log_dir / "replay").is_dir()


def test_ml_logger_uses_app_log_dir_env(tmp_path, monkeypatch):
    custom_log_dir = tmp_path / "render-logs"
    monkeypatch.setenv("APP_LOG_DIR", str(custom_log_dir))

    ml_logger = _reload_module("app.services.ml_logger")

    assert ml_logger.LOG_DIR == str(custom_log_dir)
    assert ml_logger.GAME_LOG_DIR == str(custom_log_dir / "games")
    assert (custom_log_dir / "games").is_dir()
