import html

def render_login_form(error_msg: str = None):
    err_html = f'<div class="err">{html.escape(error_msg)}</div>' if error_msg else ''
    return f'''<div class="card login-card">
        <h1>🔑 Вход в систему</h1>
        <p class="subtitle">Введите пароль администратора для доступа к загрузке и сверке.</p>
        {err_html}
        <form action="/login" method="post">
            <label>Пароль</label>
            <input name="password" type="password" placeholder="Введите пароль" autofocus required>
            <button class="btn" style="width:100%;text-align:center">Войти</button>
        </form>
        <div style="margin-top:16px;text-align:center">
            <a class="back-link" href="/">← На главную</a>
        </div>
    </div>'''

def render_rate_limit_page(retry_after: int):
    return f'''<div class="card">
        <h1>⏳ Слишком много запросов</h1>
        <div class="warn">
            Превышен лимит запросов. В целях безопасности подождите <b>{retry_after} сек.</b> и повторите попытку.
        </div>
        <a class="btn-outline btn" href="/">← Вернуться на главную</a>
    </div>'''

def render_throttled_page(retry_after: int):
    return f'''<div class="card">
        <h1>⏳ Запрос приостановлен (Throttling)</h1>
        <div class="warn">
            С вашего IP-адреса выполняется слишком много одновременных операций. Пожалуйста, подождите завершения предыдущего запроса ({retry_after} сек.).
        </div>
        <a class="btn-outline btn" href="/">← На главную</a>
    </div>'''

def render_404_page():
    return '''<div class="card">
        <h1>404 — Страница не найдена</h1>
        <p style="color:#64748b;margin:12px 0 20px">Запрашиваемый ресурс не существует или был перемещён.</p>
        <a class="btn-outline btn" href="/">← На главную</a>
    </div>'''

def render_forbidden_page():
    return '''<div class="card">
        <h1>⛔ Доступ запрещён</h1>
        <p style="color:#64748b;margin:12px 0 20px">Недействительная или устаревшая ссылка на квитанцию.</p>
        <a class="btn-outline btn" href="/">← На главную</a>
    </div>'''
