"""Request-local locale helpers for canonical language URLs."""

from contextvars import ContextVar

_current_locale: ContextVar[str] = ContextVar("krec_locale", default="ru")


def set_locale(locale: str) -> str:
    value = "kk" if str(locale).lower() in {"kk", "kz"} else "ru"
    _current_locale.set(value)
    return value


def get_locale() -> str:
    return _current_locale.get()


def localized_path(path: str, locale: str | None = None) -> str:
    """Build a language-prefixed public URL while preserving the path."""
    selected = locale or get_locale()
    selected = "kk" if selected == "kk" else "ru"
    clean = "/" + str(path or "/").lstrip("/")
    if clean == "/":
        return f"/{selected}/"
    return f"/{selected}{clean}"
