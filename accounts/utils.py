import re
from datetime import datetime

_TRANSLIT = {
 'а':"a",'А':"A",'б':"b",'Б':"B",'в':"v",'В':"V",'г':"g",'Г':"G",'д':"d",'Д':"D",
 'е':"e",'Е':"E",'ё':"yo",'Ё':"Yo",'ж':"zh",'Ж':"Zh",'з':"z",'З':"Z",'и':"i",'И':"I",
 'й':"y",'Й':"y",'к':"k",'К':"K",'л':"l",'Л':"L",'м':"m",'М':"M",'н':"n",'Н':"N",
 'о':"o",'О':"O",'п':"p",'П':"P",'р':"r",'Р':"R",'с':"s",'С':"S",'т':"t",'Т':"T",
 'у':"u",'У':"U",'ф':"f",'Ф':"F",'х':"h",'Х':"H",'ц':"ts",'Ц':"Ts",'ч':"ch",'Ч':"Ch",
 'ш':"sh",'Ш':"Sh",'щ':"sch",'Щ':"Sch",'ъ':"",'Ъ':"",'ы':"y",'Ы':"Y",'ь':"",'Ь':"",
 'э':"e",'Э':"E",'ю':"yu",'Ю':"Yu",'я':"ya",'Я':"Ya",
}

def translit(s: str) -> str:
    return "".join(_TRANSLIT.get(ch,ch) for ch in s)

def normalize_login(first_name: str, last_name: str) -> str:
    f = re.sub(r'[^a-zA-Z0-9]', '', translit(first_name))
    l = re.sub(r'[^a-zA-Z0-9]', '', translit(last_name))
    if not f or not l:
        raise ValueError("Нельзя сформировать логин: пустое имя/фамилия после транслитерации.")
    return (f[0] + l).lower()


def normalize_birth_date(input_str: str) -> str | None:
    """
    Формат ввода в UI: ДД.ММ.0004 (можно оставить пустым).
    Разрешаем "ДД.ММ" или "ДД.ММ.ГГГГ", но год принудительно сохраняем как 0004.
    """
    if not input_str:
        return None
    s = input_str.strip()
    if not s:
        return None

    # Разрешаем "ДД.ММ" или "ДД.ММ.ГГГГ"
    if not re.match(r'^\d{2}\.\d{2}(?:\.\d{4})?$', s):
        raise ValueError("Введите дату рождения в формате ДД.ММ.0004. Оставьте пустым, если не указана")

    parts = s.split(".")
    day, month = parts[0], parts[1]

    # Принудительно выставляем год = 0004
    test = f"{day}.{month}.0004"
    try:
        dt = datetime.strptime(test, "%d.%m.%Y")
    except ValueError:
        raise ValueError("Введённые значения не образуют реальную дату.")
    return dt.strftime("%d.%m.%Y")
