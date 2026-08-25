# -*- coding: utf-8 -*-
import html

from templates.icons import icon


def render_login_form(error_msg: str = None):
    err_html = f'<div class="err">{html.escape(error_msg)}</div>' if error_msg else ''
    return f'''<div class="card login-card">
        <h1><span style="display:inline-flex;align-items:center;gap:8px">{icon('lock', 22, '#3b82f6')} Вход в систему</span></h1>
        <p class="subtitle">Введите пароль администратора для доступа к загрузке и сверке.</p>
        {err_html}
        <form action="/login" method="post">
            <label>Пароль</label>
            <input name="password" type="password" placeholder="Введите пароль" autofocus required>
            <button class="btn" style="width:100%;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px">{icon('login', 16)} Войти</button>
        </form>
        <div style="margin-top:16px;text-align:center">
            <a class="back-link" href="/kvit/" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} На главную</a>
        </div>
    </div>'''

def render_rate_limit_page(retry_after: int):
    return f'''<div class="card">
        <h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:8px">{icon('clock', 22, '#d97706')} Слишком много запросов</span></h1>
        <div class="warn">
            Превышен лимит запросов. В целях безопасности подождите <b>{retry_after} сек.</b> и повторите попытку.
        </div>
        <a class="btn-outline btn" href="/kvit/" style="display:inline-flex;align-items:center;gap:6px">{icon('arrow_left', 14)} Вернуться на главную</a>
    </div>'''

def render_throttled_page(retry_after: int):
    return f'''<div class="card">
        <h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:8px">{icon('clock', 22, '#d97706')} Запрос приостановлен (Throttling)</span></h1>
        <div class="warn">
            С вашего IP-адреса выполняется слишком много одновременных операций. Пожалуйста, подождите завершения предыдущего запроса ({retry_after} сек.).
        </div>
        <a class="btn-outline btn" href="/kvit/" style="display:inline-flex;align-items:center;gap:6px">{icon('arrow_left', 14)} На главную</a>
    </div>'''

def render_404_page():
    return f'''<div class="card">
        <h1><span style="color:#64748b;display:inline-flex;align-items:center;gap:8px">{icon('alert_circle', 22, '#64748b')} 404 — Страница не найдена</span></h1>
        <p style="color:#64748b;margin:12px 0 20px">Запрашиваемый ресурс не существует или был перемещён.</p>
        <a class="btn-outline btn" href="/kvit/" style="display:inline-flex;align-items:center;gap:6px">{icon('arrow_left', 14)} На главную</a>
    </div>'''

def render_forbidden_page(message: str = 'Недействительная или устаревшая ссылка на квитанцию.'):
    return f'''<div class="card">
        <h1><span style="color:#dc2626;display:inline-flex;align-items:center;gap:8px">{icon('shield_alert', 22, '#dc2626')} Доступ запрещён</span></h1>
        <p style="color:#64748b;margin:12px 0 20px">{html.escape(message)}</p>
        <a class="btn-outline btn" href="/kvit/" style="display:inline-flex;align-items:center;gap:6px">{icon('arrow_left', 14)} На главную</a>
    </div>'''
