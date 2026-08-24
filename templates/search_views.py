import html

def render_search_form(periods, active_tab='account', default_account='', default_address='', default_period=''):
    period_options = '<option value="">Все периоды</option>'
    for p in periods:
        p_val = p['period']
        selected = ' selected' if p_val == default_period else ''
        period_options += f'<option value="{html.escape(p_val)}"{selected}>{html.escape(p_val)}</option>'

    is_addr = active_tab == 'address'
    tab_acc_cls = ' active' if not is_addr else ''
    tab_addr_cls = ' active' if is_addr else ''
    form_acc_style = '' if not is_addr else 'display:none'
    form_addr_style = '' if is_addr else 'display:none'

    return f'''<div class="card">
        <h1>Получение квитанции</h1>
        <p class="subtitle">Найдите квитанцию по номеру лицевого счёта или по адресу объекта.</p>

        <div class="mode-tabs search-tabs">
            <button type="button" class="mode-tab{tab_acc_cls}" id="tabBtnAccount" onclick="switchSearchTab('account')">🔢 По лицевому счёту</button>
            <button type="button" class="mode-tab{tab_addr_cls}" id="tabBtnAddress" onclick="switchSearchTab('address')">📍 По адресу</button>
        </div>

        <form id="searchAccountForm" action="/search" method="get" style="{form_acc_style}">
            <label>Лицевой счёт</label>
            <input name="account" type="search" inputmode="numeric" placeholder="Например, 800146" value="{html.escape(default_account)}" required>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button class="btn">Найти квитанцию</button>
        </form>

        <form id="searchAddressForm" action="/search" method="get" style="{form_addr_style}">
            <label>Точный адрес объекта</label>
            <input name="address" type="search" placeholder="Например: станц. Шокай, ул. Автобаза, дом 1" value="{html.escape(default_address)}" required>
            <p style="color:#64748b;font-size:12px;margin:-4px 0 12px">🔒 Укажите улицу, номер дома и квартиру. В целях безопасности поиск открывает квитанцию только при указании конкретного адреса.</p>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button class="btn">Найти по адресу</button>
        </form>
    </div>


    <script>
    function switchSearchTab(tab) {{
        var fAcc = document.getElementById('searchAccountForm');
        var fAddr = document.getElementById('searchAddressForm');
        var bAcc = document.getElementById('tabBtnAccount');
        var bAddr = document.getElementById('tabBtnAddress');
        if (!fAcc || !fAddr) return;

        if (tab === 'address') {{
            fAcc.style.display = 'none';
            fAddr.style.display = 'block';
            bAcc.classList.remove('active');
            bAddr.classList.add('active');
            var inp = fAddr.querySelector('input[name="address"]');
            if (inp) inp.focus();
        }} else {{
            fAddr.style.display = 'none';
            fAcc.style.display = 'block';
            bAddr.classList.remove('active');
            bAcc.classList.add('active');
            var inp = fAcc.querySelector('input[name="account"]');
            if (inp) inp.focus();
        }}
    }}
    </script>'''

def render_search_result(account: str, period_filter: str, account_row, receipts):
    if not account_row:
        return f'''<div class="card">
            <h1>❌ Лицевой счёт не найден</h1>
            <div class="err">
                <b>Лицевой счёт <span style="font-size:18px">{html.escape(account)}</span> отсутствует в базе данных.</b><br><br>
                Возможные причины:<br>
                • Номер лицевого счёта введён неверно<br>
                • Данный лицевой счёт не зарегистрирован в системе
            </div>
            <p style="color:#64748b;font-size:14px">Проверьте правильность введённого номера или попробуйте найти квитанцию по адресу.</p>
            <div style="display:flex;gap:10px;flex-wrap:wrap">
                <a class="btn-outline btn" href="/">← Поиск по номеру</a>
                <a class="btn-outline btn" href="/?tab=address" style="border-color:#64748b;color:#64748b">📍 Поиск по адресу</a>
            </div>
        </div>'''

    acct = html.escape(str(account_row['account_number']))
    addr = html.escape(account_row['address'] or '—')

    if not receipts:
        if period_filter:
            return f'''<div class="card">
                <h1>⚠️ Квитанция за период не найдена</h1>
                <div class="ok" style="background:#f0fdf4;border-color:#bbf7d0">
                    <b>✅ Лицевой счёт найден в базе</b><br><br>
                    <b>Лицевой счёт:</b> {acct}<br>
                    <b>Адрес:</b> {addr}
                </div>
                <div class="warn">
                    <b>Квитанция за период «{html.escape(period_filter)}» для данного счёта отсутствует.</b><br><br>
                    Лицевой счёт зарегистрирован в системе, но квитанция за указанный период ещё не загружена.
                </div>
                <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">
                    <a class="btn-outline btn" href="/search?account={acct}">📋 Показать все периоды</a>
                    <a class="btn-outline btn" href="/" style="border-color:#64748b;color:#64748b">← Новый поиск</a>
                </div>
            </div>'''
        else:
            return f'''<div class="card">
                <h1>⚠️ Квитанции не загружены</h1>
                <div class="ok" style="background:#f0fdf4;border-color:#bbf7d0">
                    <b>✅ Лицевой счёт найден в базе</b><br><br>
                    <b>Лицевой счёт:</b> {acct}<br>
                    <b>Адрес:</b> {addr}
                </div>
                <div class="warn">
                    <b>Для данного лицевого счёта квитанции ещё не загружены.</b><br><br>
                    Лицевой счёт зарегистрирован в системе, но ни одной квитанции пока не было добавлено.
                </div>
                <a class="btn-outline btn" href="/">← Новый поиск</a>
            </div>'''

    if len(receipts) == 1:
        r = receipts[0]
        period_esc = html.escape(r['period'])
        token = r['access_token']
        return f'''<div class="card">
            <h1>Квитанция найдена</h1>
            <div class="ok">
                <b>Лицевой счёт:</b> {acct}<br>
                <b>Период:</b> {period_esc}<br>
                <b>Адрес:</b> {addr}
            </div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:16px">
                <a class="btn" href="/receipt?token={token}" target="_blank">Открыть PDF</a>
                <a class="btn btn-green" href="/download?token={token}">Скачать PDF</a>
            </div>
            <br>
            <a class="back-link" href="/">← Новый поиск</a>
        </div>'''
    else:
        periods_html = ''
        for r in receipts:
            period_esc = html.escape(r['period'])
            token = r['access_token']
            periods_html += f'''<div class="period-card">
                <span class="period-name">📄 {period_esc}</span>
                <div class="period-actions">
                    <a class="btn btn-sm" href="/receipt?token={token}" target="_blank">Открыть</a>
                    <a class="btn btn-green btn-sm" href="/download?token={token}">Скачать</a>
                </div>
            </div>'''

        return f'''<div class="card">
            <h1>Квитанции найдены</h1>
            <div class="ok">
                <b>Лицевой счёт:</b> {acct}<br>
                <b>Адрес:</b> {addr}<br>
                <b>Доступно квитанций:</b> {len(receipts)}
            </div>
            <h2 style="font-size:17px;margin:24px 0 12px;color:#334155">Выберите период:</h2>
            {periods_html}
            <br>
            <a class="back-link" href="/">← Новый поиск</a>
        </div>'''

def render_address_clarification_prompt(address_query: str, period_filter: str, message: str, periods=None):
    q_esc = html.escape(address_query)
    period_options = '<option value="">Все периоды</option>'
    if periods:
        for p in periods:
            p_val = p['period']
            selected = ' selected' if p_val == period_filter else ''
            period_options += f'<option value="{html.escape(p_val)}"{selected}>{html.escape(p_val)}</option>'

    return f'''<div class="card">
        <h1>📍 Требуется уточнить адрес</h1>
        <div class="warn">
            <b>{html.escape(message)}</b><br><br>
            🔒 <b>Конфиденциальность:</b> список чужих адресов и лицевых счетов соседей не отображается. Для получения квитанции укажите конкретный номер дома (и квартиру при наличии).
        </div>

        <form action="/search" method="get" style="margin-top:16px">
            <label>Уточните адрес (улица, номер дома, квартира):</label>
            <input name="address" type="search" value="{q_esc}" placeholder="Например: станц. Шокай, ул. Автобаза, дом 1" required autofocus>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button class="btn">Найти квитанцию</button>
        </form>

        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
            <a class="btn-outline btn" href="/" style="border-color:#64748b;color:#64748b">🔢 Поиск по номеру счёта</a>
        </div>
    </div>'''

def render_address_not_found(address_query: str, period_filter: str, message: str, periods=None):
    q_esc = html.escape(address_query)
    period_options = '<option value="">Все периоды</option>'
    if periods:
        for p in periods:
            p_val = p['period']
            selected = ' selected' if p_val == period_filter else ''
            period_options += f'<option value="{html.escape(p_val)}"{selected}>{html.escape(p_val)}</option>'

    return f'''<div class="card">
        <h1>❌ Квитанция не найдена</h1>
        <div class="err">
            <b>{html.escape(message)}</b><br><br>
            Рекомендации:<br>
            • Проверьте правильность написания названия улицы или населенного пункта<br>
            • Укажите точный номер дома и квартиры (например: <i>ул. Автобаза, дом 1</i> или <i>ул. Каблукова 38</i>)<br>
            • Попробуйте выполнить поиск по номеру лицевого счёта
        </div>

        <form action="/search" method="get" style="margin-top:16px">
            <label>Попробуйте ввести адрес ещё раз:</label>
            <input name="address" type="search" value="{q_esc}" placeholder="Например: станц. Шокай, ул. Автобаза, дом 1" required autofocus>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button class="btn">Искать снова</button>
        </form>

        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
            <a class="btn-outline btn" href="/" style="border-color:#64748b;color:#64748b">🔢 Поиск по лицевому счёту</a>
        </div>
    </div>'''

def render_address_search_results(address_query: str, period_filter: str, accounts: list):
    """Обратная совместимость: если передан 1 счет — рендерит перенаправление, иначе форму уточнения."""
    if accounts and len(accounts) == 1:
        return render_address_clarification_prompt(address_query, period_filter, "Найдена 1 запись.")
    return render_address_clarification_prompt(address_query, period_filter, "Пожалуйста, укажите точный номер дома и квартиры.")
