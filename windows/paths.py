"""Repository-relative paths and ignored, machine-local executable settings."""

import json
from pathlib import Path

WINDOWS = Path(__file__).resolve().parent
REPO = WINDOWS.parent
LOCAL_ROOT = REPO / ".windows-local"
SETTINGS_PATH = LOCAL_ROOT / "settings.json"
RUNTIME_HOME = LOCAL_ROOT / "runtime-home"
PLAYER_CWD = LOCAL_ROOT / "player-sandbox"
PREFERENCES_JAR = LOCAL_ROOT / "support/isolated-preferences.jar"


def settings():
    if not SETTINGS_PATH.is_file():
        raise RuntimeError("Run windows/Setup.ps1 before using the Windows launchers")
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))


def common_java_arguments():
    return [
        "--add-opens=java.base/java.io=ALL-UNNAMED",
        "-Dfile.encoding=UTF-8",
        f"-Duser.home={RUNTIME_HOME.as_posix()}",
        f"-Xbootclasspath/a:{PREFERENCES_JAR.as_posix()}",
        "-Djava.util.prefs.PreferencesFactory=experiment.IsolatedPreferencesFactory",
    ]
