import os
from typing import Optional


def validate_safe_path(path: str, base_dir: Optional[str] = None) -> str:
    """
    Каноникализирует и проверяет путь на отсутствие path traversal / injection атак.
    Предотвращает выход за пределы разрешённого базового каталога (защита по правилу Sonar pythonsecurity:S8707).

    Порядок проверки:
    1. Каноникализация базового каталога через os.path.realpath.
    2. Каноникализация целевого пути через os.path.realpath (разрешение символических ссылок и ..).
    3. Проверка вхождения пути в базовый каталог с обязательным разделителем (base_dir + os.sep)
       для исключения частичного обхода путей (partial path traversal).
    """
    if not path:
        raise ValueError("Путь не может быть пустым")

    if base_dir is None:
        resolved_base = os.path.realpath(os.getcwd())
    else:
        resolved_base = os.path.realpath(base_dir)

    resolved_path = os.path.realpath(path)

    # Проверка на совпадение с базовым каталогом или нахождение строго внутри него
    if resolved_path != resolved_base and not resolved_path.startswith(resolved_base + os.sep):
        raise ValueError(f"Путь {path!r} выходит за пределы разрешённого каталога {resolved_base!r}")

    return resolved_path
