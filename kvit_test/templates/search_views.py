# -*- coding: utf-8 -*-
import html

from templates.icons import icon


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

    ico_clock = icon('clock', 15, '#ef4444')
    ico_bulb = icon('lightbulb', 15, '#d97706')
    ico_warn = icon('alert_triangle', 22, '#d97706')
    ico_ok = icon('check_circle', 22, '#16a34a')
    ico_eye_btn = icon('eye', 15)
    ico_eye_sm = icon('eye', 13)
    ico_dl_btn = icon('download', 15)
    ico_dl_sm = icon('download', 13)
    ico_file = icon('file_text', 16, '#3b82f6')
    ico_err = icon('x_circle', 22, '#dc2626')
    ico_shield = icon('shield', 14)

    return f'''<div class="card">
        <h1>Получение квитанции</h1>
        <p class="subtitle">Найдите квитанцию по номеру лицевого счёта или по адресу объекта.</p>

        <div class="mode-tabs search-tabs">
            <button type="button" class="mode-tab{tab_acc_cls}" id="tabBtnAccount" onclick="switchSearchTab('account')">{icon('hash', 15)} По лицевому счёту</button>
            <button type="button" class="mode-tab{tab_addr_cls}" id="tabBtnAddress" onclick="switchSearchTab('address')">{icon('map_pin', 15)} По адресу</button>
        </div>

        <!-- Поиск по лицевому счёту -->
        <form id="searchAccountForm" action="/search" method="get" style="{form_acc_style}" onsubmit="handleAjaxSearch(event, this, 'account')">
            <label>Лицевой счёт</label>
            <input name="account" type="search" inputmode="numeric" placeholder="Например: 800146" value="{html.escape(default_account)}" required>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button type="submit" class="btn">{icon('search', 15)} Найти квитанцию</button>
        </form>

        <!-- Поиск по адресу -->
        <form id="searchAddressForm" action="/search" method="get" style="{form_addr_style}" onsubmit="handleAjaxSearch(event, this, 'address')">
            <label>Точный адрес объекта</label>
            <input name="address" type="search" placeholder="Например: ул. Абая 10, кв 5 или Абая 10-5" value="{html.escape(default_address)}" required>
            <p style="color:#64748b;font-size:12px;margin:4px 0 12px;display:flex;align-items:center;gap:5px">{icon('shield', 13)} Укажите улицу, номер дома и квартиру (например: <i>ул. Абая 10, кв 5</i> или <i>Абая 10-5</i>).</p>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button type="submit" class="btn">{icon('search', 15)} Найти по адресу</button>
        </form>
    </div>

    <!-- Контейнер для мгновенных AJAX-результатов -->
    <div id="liveSearchResults"></div>

    <script>
    function switchSearchTab(tab) {{
        var fAcc = document.getElementById('searchAccountForm');
        var fAddr = document.getElementById('searchAddressForm');
        var bAcc = document.getElementById('tabBtnAccount');
        var bAddr = document.getElementById('tabBtnAddress');
        var resBox = document.getElementById('liveSearchResults');
        if (!fAcc || !fAddr) return;

        if (resBox) resBox.innerHTML = '';

        if (tab === 'address') {{
            fAcc.style.display = 'none';
            fAddr.style.display = 'block';
            if (bAcc) bAcc.classList.remove('active');
            if (bAddr) bAddr.classList.add('active');
            var inp = fAddr.querySelector('input[name="address"]');
            if (inp) inp.focus();
        }} else {{
            fAddr.style.display = 'none';
            fAcc.style.display = 'block';
            if (bAddr) bAddr.classList.remove('active');
            if (bAcc) bAcc.classList.add('active');
            var inp = fAcc.querySelector('input[name="account"]');
            if (inp) inp.focus();
        }}
    }}

    async function handleAjaxSearch(e, formEl, formType) {{
        e.preventDefault();
        var resBox = document.getElementById('liveSearchResults');
        if (!resBox) return;

        resBox.innerHTML = '<div class="card search-loading-box"><div class="spinner"></div><span>Поиск квитанции...</span></div>';

        var formData = new FormData(formEl);
        var params = new URLSearchParams();
        for (var pair of formData.entries()) {{
            if (pair[1] && pair[1].trim()) {{
                params.append(pair[0], pair[1].trim());
            }}
        }}

        try {{
            var resp = await fetch('/api/search?' + params.toString(), {{
                headers: {{ 'Accept': 'application/json' }},
                cache: 'no-store'
            }});
            if (!resp.ok) {{
                if (resp.status === 429) {{
                    resBox.innerHTML = '<div class="card receipt-card-anim"><div class="err" style="display:flex;align-items:center;gap:6px">{ico_clock} Слишком много запросов. Пожалуйста, подождите несколько секунд.</div></div>';
                    return;
                }}
                throw new Error('Server error ' + resp.status);
            }}

            var data = await resp.json();
            renderAjaxSearchResults(data, params.get('period') || '');
        }} catch(err) {{
            formEl.submit();
        }}
    }}

    function escapeHtml(str) {{
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }}

    function renderAjaxSearchResults(data, periodFilter) {{
        var resBox = document.getElementById('liveSearchResults');
        if (!resBox) return;

        if (data.status === 'EXACT_MATCH') {{
            var acct = escapeHtml(data.account || '');
            var addr = escapeHtml(data.address || '—');
            var receipts = data.receipts || [];

            var typoHtml = '';
            if (data.is_corrected && data.corrected_street) {{
                typoHtml = '<div class="typo-badge" style="display:flex;align-items:center;gap:6px">{ico_bulb} <span><b>Показаны результаты для:</b> «' + escapeHtml(data.corrected_street) + '» (исправлена опечатка в названии)</span></div>';
            }}

            if (!receipts || receipts.length === 0) {{
                var noRecHtml = '';
                if (periodFilter) {{
                    noRecHtml = '<div class="card receipt-card-anim">' +
                        '<h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:6px">{ico_warn} Квитанция за период не найдена</span></h1>' +
                        typoHtml +
                        '<div class="ok" style="background:#f0fdf4;border-color:#bbf7d0">' +
                            '<b>Лицевой счёт:</b> ' + acct + '<br><b>Адрес:</b> ' + addr +
                        '</div>' +
                        '<div class="warn"><b>Квитанция за период «' + escapeHtml(periodFilter) + '» для данного счёта отсутствует.</b></div>' +
                    '</div>';
                }} else {{
                    noRecHtml = '<div class="card receipt-card-anim">' +
                        '<h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:6px">{ico_warn} Квитанции не загружены</span></h1>' +
                        typoHtml +
                        '<div class="ok" style="background:#f0fdf4;border-color:#bbf7d0">' +
                            '<b>Лицевой счёт:</b> ' + acct + '<br><b>Адрес:</b> ' + addr +
                        '</div>' +
                        '<div class="warn">Для данного лицевого счёта квитанции пока не загружены.</div>' +
                    '</div>';
                }}
                resBox.innerHTML = noRecHtml;
                resBox.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
                return;
            }}

            if (receipts.length === 1) {{
                var r = receipts[0];
                var token = escapeHtml(r.access_token);
                var periodEsc = escapeHtml(r.period);
                var singleHtml = '<div class="card receipt-card-anim">' +
                    '<h1><span style="display:inline-flex;align-items:center;gap:6px;color:#16a34a">{ico_ok} Квитанция найдена</span></h1>' +
                    typoHtml +
                    '<div class="ok">' +
                        '<b>Лицевой счёт:</b> ' + acct + '<br>' +
                        '<b>Период:</b> ' + periodEsc + '<br>' +
                        '<b>Адрес:</b> ' + addr +
                    '</div>' +
                    '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:16px">' +
                        '<button type="button" class="btn" data-token="' + token + '" data-title="Квитанция: ' + acct + ' (' + periodEsc + ')" onclick="openPdfModal(this.getAttribute(\\'data-token\\'), this.getAttribute(\\'data-title\\'))">{ico_eye_btn} Быстрый просмотр</button>' +
                        '<a class="btn btn-green" href="/download?token=' + token + '">{ico_dl_btn} Скачать PDF</a>' +
                    '</div>' +
                '</div>';
                resBox.innerHTML = singleHtml;
            }} else {{
                var listHtml = '';
                for (var i = 0; i < receipts.length; i++) {{
                    var rec = receipts[i];
                    var t = escapeHtml(rec.access_token);
                    var pEsc = escapeHtml(rec.period);
                    listHtml += '<div class="period-card">' +
                        '<span class="period-name" style="display:inline-flex;align-items:center;gap:6px">{ico_file} ' + pEsc + '</span>' +
                        '<div class="period-actions">' +
                            '<button type="button" class="btn btn-sm" data-token="' + t + '" data-title="Квитанция: ' + acct + ' (' + pEsc + ')" onclick="openPdfModal(this.getAttribute(\\'data-token\\'), this.getAttribute(\\'data-title\\'))">{ico_eye_sm} Просмотр</button>' +
                            '<a class="btn btn-green btn-sm" href="/download?token=' + t + '">{ico_dl_sm} Скачать</a>' +
                        '</div>' +
                    '</div>';
                }}

                var multiHtml = '<div class="card receipt-card-anim">' +
                    '<h1><span style="display:inline-flex;align-items:center;gap:6px;color:#16a34a">{ico_ok} Квитанции найдены</span></h1>' +
                    typoHtml +
                    '<div class="ok">' +
                        '<b>Лицевой счёт:</b> ' + acct + '<br>' +
                        '<b>Адрес:</b> ' + addr + '<br>' +
                        '<b>Доступно квитанций:</b> ' + receipts.length +
                    '</div>' +
                    '<h2 style="font-size:17px;margin:24px 0 12px;color:#334155">Выберите период:</h2>' +
                    listHtml +
                '</div>';
                resBox.innerHTML = multiHtml;
            }}
        }} else if (data.status === 'NOT_FOUND') {{
            resBox.innerHTML = '<div class="card receipt-card-anim">' +
                '<h1><span style="color:#dc2626;display:inline-flex;align-items:center;gap:6px">{ico_err} Квитанция не найдена</span></h1>' +
                '<div class="err"><b>' + escapeHtml(data.message || 'Квитанция не найдена.') + '</b><br><br>Проверьте правильность написания улицы, номера дома и квартиры.</div>' +
            '</div>';
        }} else {{
            resBox.innerHTML = '<div class="card receipt-card-anim">' +
                '<h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:6px">{ico_warn} Требуется уточнить адрес</span></h1>' +
                '<div class="warn"><b>' + escapeHtml(data.message || 'Требуется уточнить адрес.') + '</b><br><br><span style="display:inline-flex;align-items:center;gap:5px">{ico_shield} <b>Конфиденциальность:</b></span> поиск открывает квитанцию только при указании конкретного номера дома и квартиры.</div>' +
            '</div>';
        }}

        resBox.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
    }}
    </script>'''

def render_search_result(account: str, period_filter: str, account_row, receipts):
    acct = html.escape(account)
    addr = html.escape(account_row['address']) if account_row and account_row['address'] else '—'

    if not receipts:
        if period_filter:
            return f'''<div class="card">
                <h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:6px">{icon('alert_triangle', 22, '#d97706')} Квитанция за период не найдена</span></h1>
                <div class="ok" style="background:#f0fdf4;border-color:#bbf7d0">
                    <b>Лицевой счёт:</b> {acct}<br>
                    <b>Адрес:</b> {addr}
                </div>
                <div class="warn">
                    <b>Квитанция за период «{html.escape(period_filter)}» для счёта № {acct} не найдена.</b>
                </div>
                <br>
                <a class="back-link" href="/kvit/" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Вернуться к поиску</a>
            </div>'''
        else:
            return f'''<div class="card">
                <h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:6px">{icon('alert_triangle', 22, '#d97706')} Квитанции не найдены</span></h1>
                <div class="ok" style="background:#f0fdf4;border-color:#bbf7d0">
                    <b>Лицевой счёт:</b> {acct}<br>
                    <b>Адрес:</b> {addr}
                </div>
                <div class="warn">
                    Для лицевого счёта № {acct} квитанции пока не загружены.
                </div>
                <br>
                <a class="back-link" href="/kvit/" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Вернуться к поиску</a>
            </div>'''

    if len(receipts) == 1:
        r = receipts[0]
        period_esc = html.escape(r['period'])
        token = r['access_token']
        return f'''<div class="card">
            <h1><span style="display:inline-flex;align-items:center;gap:6px">{icon('check_circle', 22, '#16a34a')} Квитанция найдена</span></h1>
            <div class="ok">
                <b>Лицевой счёт:</b> {acct}<br>
                <b>Период:</b> {period_esc}<br>
                <b>Адрес:</b> {addr}
            </div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:16px">
                <button type="button" class="btn" onclick="openPdfModal('{token}', 'Квитанция: {acct} ({period_esc})')">{icon('eye', 15)} Быстрый просмотр</button>
                <a class="btn btn-green" href="/download?token={token}">{icon('upload', 15)} Скачать PDF</a>
            </div>
            <br>
            <a class="back-link" href="/kvit/" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Новый поиск</a>
        </div>'''
    else:
        periods_html = ''
        for r in receipts:
            period_esc = html.escape(r['period'])
            token = r['access_token']
            periods_html += f'''<div class="period-card">
                <span class="period-name" style="display:inline-flex;align-items:center;gap:6px">{icon('file_text', 16, '#3b82f6')} {period_esc}</span>
                <div class="period-actions">
                    <button type="button" class="btn btn-sm" onclick="openPdfModal('{token}', 'Квитанция: {acct} ({period_esc})')">{icon('eye', 13)} Просмотр</button>
                    <a class="btn-outline btn btn-sm" href="/receipt?token={token}" target="_blank">Вкладка</a>
                    <a class="btn btn-green btn-sm" href="/download?token={token}">Скачать</a>
                </div>
            </div>'''

        return f'''<div class="card">
            <h1><span style="display:inline-flex;align-items:center;gap:6px">{icon('check_circle', 22, '#16a34a')} Квитанции найдены</span></h1>
            <div class="ok">
                <b>Лицевой счёт:</b> {acct}<br>
                <b>Адрес:</b> {addr}<br>
                <b>Доступно квитанций:</b> {len(receipts)}
            </div>
            <h2 style="font-size:17px;margin:24px 0 12px;color:#334155">Выберите период:</h2>
            {periods_html}
            <br>
            <a class="back-link" href="/kvit/" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Новый поиск</a>
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
        <h1><span style="display:inline-flex;align-items:center;gap:6px">{icon('map_pin', 22, '#3b82f6')} Требуется уточнить адрес</span></h1>
        <div class="warn">
            <b>{html.escape(message)}</b><br><br>
            <span style="display:inline-flex;align-items:center;gap:5px">{icon('shield', 14)} <b>Конфиденциальность:</b></span> список чужих адресов и лицевых счетов соседей не отображается. Для получения квитанции укажите конкретный номер дома (и квартиру при наличии).
        </div>

        <form action="/search" method="get" style="margin-top:16px">
            <label>Уточните адрес (улица, номер дома, квартира):</label>
            <input name="address" type="search" value="{q_esc}" placeholder="Например: станц. Шокай, ул. Автобаза, дом 1" required autofocus>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button class="btn">{icon('search', 15)} Найти квитанцию</button>
        </form>

        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
            <a class="btn-outline btn" href="/kvit/" style="border-color:#64748b;color:#64748b">{icon('hash', 14)} Поиск по номеру счёта</a>
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
        <h1><span style="color:#dc2626;display:inline-flex;align-items:center;gap:6px">{icon('x_circle', 22, '#dc2626')} Квитанция не найдена</span></h1>
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
            <button class="btn">{icon('search', 15)} Искать снова</button>
        </form>

        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
            <a class="btn-outline btn" href="/kvit/" style="border-color:#64748b;color:#64748b">{icon('hash', 14)} Поиск по лицевому счёту</a>
        </div>
    </div>'''

def render_address_search_results(address_query: str, period_filter: str, accounts: list):
    """Обратная совместимость: если передан 1 счет — рендерит перенаправление, иначе форму уточнения."""
    if accounts and len(accounts) == 1:
        return render_address_clarification_prompt(address_query, period_filter, "Найдена 1 запись.")
    return render_address_clarification_prompt(address_query, period_filter, "Пожалуйста, укажите точный номер дома и квартиры.")

