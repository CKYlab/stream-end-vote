"""Validated display presets shared by config, GUI and release defaults."""
import re

DISPLAY_DEFAULTS = {
    "vote_panel_position": "bottom-right",
    "countdown_position": "center",
    "vote_panel_x": 0,
    "vote_panel_y": 0,
    "countdown_x": 0,
    "countdown_y": 0,
}
PANEL_POSITIONS = {"右下": "bottom-right", "左下": "bottom-left", "右上": "top-right", "左上": "top-left"}
COUNTDOWN_POSITIONS = {"中央": "center", "上寄せ": "top", "下寄せ": "bottom"}


def validate_display_settings(values):
    result = {}
    for key, default in DISPLAY_DEFAULTS.items():
        value = values.get(key, default)
        if key.endswith("position"):
            choices = PANEL_POSITIONS if key == "vote_panel_position" else COUNTDOWN_POSITIONS
            if value not in choices.values():
                raise ValueError("表示位置を一覧から選択してください。")
            result[key] = value
        else:
            text = str(value)
            if not re.fullmatch(r"[+-]?[0-9]+", text) or not -500 <= int(text) <= 500:
                raise ValueError("X/Y微調整は-500〜+500pxの整数で入力してください。")
            result[key] = int(text)
    return result
