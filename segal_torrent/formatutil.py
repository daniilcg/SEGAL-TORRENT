from __future__ import annotations


def format_size(num: int, lang: str) -> str:
    if num < 0:
        num = 0
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ") if lang == "ru" else ("B", "KB", "MB", "GB", "TB")
    value = float(num)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    if index == 0:
        text = str(int(value))
    elif value >= 100:
        text = f"{value:.0f}"
    elif value >= 10:
        text = f"{value:.1f}"
    else:
        text = f"{value:.2f}"
    return f"{text} {units[index]}"


def format_speed(num: int, lang: str) -> str:
    suffix = "/с" if lang == "ru" else "/s"
    return format_size(num, lang) + suffix


def format_percent(progress: float) -> str:
    if progress >= 1:
        return "100%"
    if progress <= 0:
        return "0%"
    pct = int(progress * 100)
    if pct <= 0:
        return "<1%"
    if pct >= 100:
        return "99%"
    return f"{pct}%"


def format_eta(seconds: int, lang: str) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if lang == "ru":
        if hours:
            return f"{hours} ч {minutes:02d} мин"
        if minutes:
            return f"{minutes} мин {secs:02d} с"
        return f"{secs} с"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_eta_value(eta: int, lang: str) -> str:
    if eta == -2:
        return "∞"
    if eta < 0:
        return "—"
    return format_eta(eta, lang)


def torrent_count(count: int, lang: str) -> str:
    if lang != "ru":
        word = "torrent" if count == 1 else "torrents"
        return f"{count} {word}"
    mod100 = abs(count) % 100
    mod10 = mod100 % 10
    if 11 <= mod100 <= 14:
        word = "торрентов"
    elif mod10 == 1:
        word = "торрент"
    elif 2 <= mod10 <= 4:
        word = "торрента"
    else:
        word = "торрентов"
    return f"{count} {word}"
