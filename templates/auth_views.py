# -*- coding: utf-8 -*-
import html

from templates.icons import icon


def render_login_form(error_msg: str = None):
    err_html = f'<div class="err" style="margin-bottom:16px">{html.escape(error_msg)}</div>' if error_msg else ''
    return f'''<div class="card login-card" style="max-width:440px;margin:40px auto;padding:36px 32px">
        <div style="display:flex;justify-content:center;margin-bottom:16px">
            <div style="width:48px;height:48px;border-radius:14px;background:linear-gradient(135deg,#006FEE 0%,#7828C8 100%);display:flex;align-items:center;justify-content:center;box-shadow:0 6px 16px rgba(0,111,238,0.3)">
                {icon('lock', 24, '#ffffff')}
            </div>
        </div>
        <h1 style="text-align:center;margin-bottom:6px">Вход в систему</h1>
        <p class="subtitle" style="text-align:center;margin-bottom:24px">Портал и сервис квитанций ТОО &laquo;КРЭК&raquo;</p>
        {err_html}
        <form action="/login" method="post">
            <label style="display:block;margin-bottom:6px;font-weight:600;font-size:13px;color:#334155">Логин или имя пользователя</label>
            <input name="username" type="text" placeholder="Например, admin или sbyt" autofocus required style="width:100%;margin-bottom:14px;padding:10px 14px;border:1.5px solid #cbd5e1;border-radius:10px">

            <label style="display:block;margin-bottom:6px;font-weight:600;font-size:13px;color:#334155">Пароль</label>
            <input name="password" type="password" placeholder="••••••••" required style="width:100%;margin-bottom:18px;padding:10px 14px;border:1.5px solid #cbd5e1;border-radius:10px">

            <button class="btn btn-green" style="width:100%;text-align:center;display:flex;align-items:center;justify-content:center;gap:8px;padding:12px;font-weight:600">
                {icon('login', 16)} Войти в систему
            </button>
        </form>
        <div style="margin-top:20px;text-align:center">
            <a class="btn-outline btn" href="/" style="display:inline-flex;align-items:center;gap:6px;font-size:13px;padding:8px 16px">{icon('arrow_left', 13)} На главную сайта</a>
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
