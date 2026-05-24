import re
from datetime import datetime

TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate_ru(value: str) -> str:
    result = []
    for char in (value or "").strip().lower():
        result.append(TRANSLIT.get(char, char))
    return "".join(result)


def normalize_login(value: str, last_name: str | None = None) -> str:
    if last_name is not None:
        first = transliterate_ru(value)
        last = transliterate_ru(last_name)
        value = f"{first[:1]}{last}" if first and last else f"{first}{last}"
    value = (value or "").strip().lower()
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[^a-z0-9_-]", "", value)
    return value


def normalize_login_candidates(first_name: str, last_name: str, numeric_limit: int = 99) -> list[str]:
    first = transliterate_ru(first_name)
    last = transliterate_ru(last_name)
    candidates: list[str] = []

    for index in range(1, len(first) + 1):
        candidate = normalize_login(f"{first[:index]}{last}")
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    # Если все варианты «буквы имени + фамилия» заняты, добавляем цифру
    # к варианту с полным именем: ivanivanov1, ivanivanov2, ...
    if first and last:
        base = normalize_login(f"{first}{last}")
        for number in range(1, numeric_limit + 1):
            candidate = normalize_login(f"{base}{number}")
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def normalize_birth_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    value = value.replace("/", ".").replace("-", ".")
    digits = re.sub(r"\D", "", value)
    candidates = []
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
        candidates.append(value)
    if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", value):
        candidates.append(f"{value[8:10]}.{value[5:7]}.{value[:4]}")
    if re.fullmatch(r"\d{8}", digits):
        candidates.append(f"{digits[:2]}.{digits[2:4]}.{digits[4:]}")
        candidates.append(f"{digits[6:8]}.{digits[4:6]}.{digits[:4]}")
    for candidate in candidates:
        try:
            parsed = datetime.strptime(candidate, "%d.%m.%Y")
            if parsed.year < 1900 or parsed.year > 2100:
                continue
            return parsed.strftime("%d.%m.%Y")
        except ValueError:
            continue
    return ""
