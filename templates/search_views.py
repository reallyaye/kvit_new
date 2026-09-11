# -*- coding: utf-8 -*-
import datetime
import html

import config
from templates.icons import icon
from templates.locale import localized_path


def render_search_form(periods, active_tab='account', default_account='', default_address='', default_period=''):
    search_path = localized_path('/search')
    api_search_path = localized_path('/api/search')
    appeals_path = localized_path('/appeals')
    download_path = localized_path('/download')
    period_options = '<option value="">Все периоды</option>'
    for p in periods:
        p_val = p['period']
        selected = ' selected' if p_val == default_period else ''
        period_options += f'<option value="{html.escape(p_val)}"{selected}>{html.escape(p_val)}</option>'

    enable_address = getattr(config, 'ENABLE_ADDRESS_SEARCH', False)
    is_addr = (active_tab == 'address') and enable_address
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

    subtitle_text = "Найдите квитанцию по номеру лицевого счёта или по адресу объекта." if enable_address else "Введите номер лицевого счёта для получения квитанции."

    tabs_html = f'''
        <div class="mode-tabs search-tabs">
            <button type="button" class="mode-tab{tab_acc_cls}" id="tabBtnAccount" onclick="switchSearchTab('account')">{icon('hash', 15)} По лицевому счёту</button>
            <button type="button" class="mode-tab{tab_addr_cls}" id="tabBtnAddress" onclick="switchSearchTab('address')">{icon('map_pin', 15)} По адресу</button>
        </div>''' if enable_address else ''

    address_form_html = f'''
        <!-- Поиск по адресу -->
        <form id="searchAddressForm" action="{search_path}" method="get" style="{form_addr_style}" onsubmit="handleAjaxSearch(event, this, 'address')">
            <label>Точный адрес объекта</label>
            <input name="address" class="ym-disable-keys" type="search" placeholder="Например: ул. Абая 10, кв 5 или Абая 10-5" value="{html.escape(default_address)}" autocomplete="off" required>
            <p style="color:#64748b;font-size:12px;margin:4px 0 12px;display:flex;align-items:center;gap:5px">{icon('shield', 13)} Укажите улицу, номер дома и квартиру (например: <i>ул. Абая 10, кв 5</i> или <i>Абая 10-5</i>).</p>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button type="submit" class="btn">{icon('search', 15)} Найти по адресу</button>
        </form>''' if enable_address else ''

    return f'''<div class="card">
        <h1>Получение квитанции</h1>
        <p class="subtitle">{subtitle_text}</p>
        {tabs_html}
        <!-- Поиск по лицевому счёту -->
        <form id="searchAccountForm" action="{search_path}" method="get" style="{form_acc_style}" onsubmit="handleAjaxSearch(event, this, 'account')">
            <label>Лицевой счёт</label>
            <input name="account" class="ym-disable-keys" type="search" inputmode="numeric" placeholder="Например: 800146" value="{html.escape(default_account)}" autocomplete="off" required>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button type="submit" class="btn">{icon('search', 15)} Найти квитанцию</button>
        </form>
        {address_form_html}
    </div>

    <!-- Контейнер для мгновенных AJAX-результатов -->
    <div id="liveSearchResults"></div>

    <section class="receipt-faq" aria-labelledby="receipt-faq-title" style="margin-top:24px;border-top:1px solid #e2e8f0;padding-top:20px">
        <h2 id="receipt-faq-title" style="font-size:18px;margin:0 0 12px;color:#1e293b">Частые вопросы</h2>
        <details style="padding:10px 0;border-bottom:1px solid #eef2f7">
            <summary style="cursor:pointer;font-weight:600">Что вводить в поле поиска?</summary>
            <p style="margin:8px 0 0;color:#64748b;font-size:14px">Введите только номер лицевого счёта. Адрес для получения квитанции не требуется.</p>
        </details>
        <details style="padding:10px 0;border-bottom:1px solid #eef2f7">
            <summary style="cursor:pointer;font-weight:600">Почему квитанция не найдена?</summary>
            <p style="margin:8px 0 0;color:#64748b;font-size:14px">Проверьте номер счёта и выбранный период. Если квитанция была загружена недавно, обратитесь в отдел по вопросам оплаты и квитанций.</p>
        </details>
        <details style="padding:10px 0;border-bottom:1px solid #eef2f7">
            <summary style="cursor:pointer;font-weight:600">Может быть доступно несколько квитанций?</summary>
            <p style="margin:8px 0 0;color:#64748b;font-size:14px">Да. Для одного лицевого счёта могут отображаться разные периоды. Выберите нужный период и скачайте официальный PDF.</p>
        </details>
        <details style="padding:10px 0">
            <summary style="cursor:pointer;font-weight:600">Куда обратиться по ошибке в начислениях?</summary>
            <p style="margin:8px 0 0;color:#64748b;font-size:14px">Подайте обращение через <a href="{appeals_path}" style="color:#2563eb">электронную приёмную</a> или позвоните по телефону, указанному на странице контактов.</p>
        </details>
    </section>

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
            var resp = await fetch('{api_search_path}?' + params.toString(), {{
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

    function formatReceiptDate(value) {{
        if (!value) return 'не определена';
        try {{
            return new Date(Number(value) * 1000).toLocaleString('ru-RU', {{ dateStyle: 'short', timeStyle: 'short' }});
        }} catch (e) {{ return 'не определена'; }}
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
                var uploadedAt = escapeHtml(formatReceiptDate(r.uploaded_at));
                var databaseUpdatedAt = escapeHtml(formatReceiptDate(data.database_updated_at));
                var singleHtml = '<div class="card receipt-card-anim">' +
                    '<h1><span style="display:inline-flex;align-items:center;gap:6px;color:#16a34a">{ico_ok} Квитанция найдена</span></h1>' +
                    typoHtml +
                    '<div class="ok">' +
                        '<b>Лицевой счёт:</b> ' + acct + '<br>' +
                        '<b>Период:</b> ' + periodEsc + '<br>' +
                        '<b>Адрес:</b> ' + addr +
                    '</div>' +
                    '<div style="margin-top:10px;color:#64748b;font-size:13px">Дата загрузки: ' + uploadedAt + ' · База обновлена: ' + databaseUpdatedAt + '</div>' +
                    '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:16px">' +
                        '<button type="button" class="btn" data-token="' + token + '" data-title="Квитанция: ' + acct + ' (' + periodEsc + ')" onclick="openPdfModal(this.getAttribute(\\'data-token\\'), this.getAttribute(\\'data-title\\'))">{ico_eye_btn} Быстрый просмотр</button>' +
                        '<a class="btn btn-green" href="{download_path}?token=' + token + '">{ico_dl_btn} Скачать PDF</a>' +
                    '</div>' +
                '</div>';
                resBox.innerHTML = singleHtml;
            }} else {{
                var listHtml = '';
                for (var i = 0; i < receipts.length; i++) {{
                    var rec = receipts[i];
                    var t = escapeHtml(rec.access_token);
                    var pEsc = escapeHtml(rec.period);
                    var uploadedAt = escapeHtml(formatReceiptDate(rec.uploaded_at));
                    listHtml += '<div class="period-card">' +
                        '<span class="period-name" style="display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap">{ico_file} <span>' + pEsc + '</span><small style="display:block;width:100%;font-size:12px;color:#64748b;font-weight:400">Загружена: ' + uploadedAt + '</small></span>' +
                        '<div class="period-actions">' +
                            '<button type="button" class="btn btn-sm" data-token="' + t + '" data-title="Квитанция: ' + acct + ' (' + pEsc + ')" onclick="openPdfModal(this.getAttribute(\\'data-token\\'), this.getAttribute(\\'data-title\\'))">{ico_eye_sm} Просмотр</button>' +
                            '<a class="btn btn-green btn-sm" href="{download_path}?token=' + t + '">{ico_dl_sm} Скачать</a>' +
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
                    '<div style="margin-top:10px;color:#64748b;font-size:13px">База обновлена: ' + escapeHtml(formatReceiptDate(data.database_updated_at)) + '</div>' +
                    listHtml +
                '</div>';
                resBox.innerHTML = multiHtml;
            }}
        }} else if (data.status === 'DISABLED') {{
            resBox.innerHTML = '<div class="card receipt-card-anim">' +
                '<h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:6px">{ico_warn} Поиск по адресу отключен</span></h1>' +
                '<div class="warn"><b>' + escapeHtml(data.message || 'Поиск по адресу временно отключен.') + '</b></div>' +
            '</div>';
        }} else if (data.status === 'NOT_FOUND') {{
            resBox.innerHTML = '<div class="card receipt-card-anim">' +
                '<h1><span style="color:#dc2626;display:inline-flex;align-items:center;gap:6px">{ico_err} Квитанция не найдена</span></h1>' +
                '<div class="err"><b>' + escapeHtml(data.message || 'Квитанция не найдена.') + '</b><br><br>Проверьте правильность написания номера лицевого счёта.</div>' +
            '</div>';
        }} else if (data.status === 'NEED_HOUSE' || data.status === 'CLARIFY_ADDRESS') {{
            resBox.innerHTML = '<div class="card receipt-card-anim">' +
                '<h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:6px">{ico_warn} Требуется уточнить адрес</span></h1>' +
                '<div class="warn"><b>' + escapeHtml(data.message || 'Пожалуйста, укажите точный номер дома и квартиры.') + '</b></div>' +
            '</div>';
        }} else {{
            resBox.innerHTML = '<div class="card receipt-card-anim">' +
                '<h1><span style="color:#d97706;display:inline-flex;align-items:center;gap:6px">{ico_warn} ' + escapeHtml(data.status === 'EMPTY' ? 'Введите данные для поиска' : 'Внимание') + '</span></h1>' +
                '<div class="warn"><b>' + escapeHtml(data.message || 'Пожалуйста, проверьте введённые данные.') + '</b></div>' +
            '</div>';
        }}

        resBox.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
    }}
    </script>'''

def _format_receipt_timestamp(value):
    if not value:
        return 'не определена'
    try:
        return datetime.datetime.fromtimestamp(float(value)).strftime('%d.%m.%Y %H:%M')
    except (TypeError, ValueError, OSError, OverflowError):
        return 'не определена'


def render_search_result(account: str, period_filter: str, account_row, receipts, is_verified: bool = True, verification_failed: bool = False, database_updated_at=None):
    acct = html.escape(account)
    addr = html.escape(account_row['address']) if account_row and account_row['address'] else '—'
    search_path = localized_path('/search')
    kvit_path = localized_path('/kvit/')
    download_path = localized_path('/download')
    receipt_path = localized_path('/receipt')

    if not is_verified and account_row:
        from services.receipts.receipt_service import mask_address
        masked_addr = html.escape(mask_address(account_row['address']))
        err_msg = f'<div class="err" style="margin-bottom:14px">{icon("alert_triangle", 15)} Неверный номер дома/квартиры. Пожалуйста, проверьте введённые данные.</div>' if verification_failed else ''
        return f'''<div class="card receipt-card-anim">
            <h1><span style="display:inline-flex;align-items:center;gap:6px">{icon('shield', 22, '#2563eb')} Подтверждение доступа к квитанции</span></h1>
            <div class="ok" style="background:#f8fafc;border-color:#e2e8f0;margin-bottom:16px">
                <b>Лицевой счёт:</b> {acct}<br>
                <b>Адрес:</b> {masked_addr}<br>
            </div>
            {err_msg}
            <div class="warn" style="margin-bottom:16px">
                <b>Защита персональных данных:</b> Для просмотра начислений и скачивания PDF подтвердите владение счетом, указав номер дома или квартиры.
            </div>
            <form method="GET" action="{search_path}" style="display:flex;gap:10px;flex-wrap:wrap">
                <input type="hidden" name="account" value="{acct}">
                <input type="hidden" name="period" value="{html.escape(period_filter)}">
                <input type="text" name="verify" class="input" placeholder="Номер дома или квартиры (например: 15 или 3)" required autofocus style="flex:1;min-width:220px">
                <button type="submit" class="btn btn-green">{icon('check', 14)} Подтвердить доступ</button>
            </form>
            <br>
            <a class="back-link" href="{kvit_path}" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Вернуться к поиску</a>
        </div>'''

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
                <a class="back-link" href="{kvit_path}" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Вернуться к поиску</a>
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
                <a class="back-link" href="{kvit_path}" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Вернуться к поиску</a>
            </div>'''

    if len(receipts) == 1:
        r = receipts[0]
        period_esc = html.escape(r['period'])
        token = r['access_token']
        uploaded_at = _format_receipt_timestamp(r.get('uploaded_at'))
        database_updated = _format_receipt_timestamp(database_updated_at)
        return f'''<div class="card">
            <h1><span style="display:inline-flex;align-items:center;gap:6px">{icon('check_circle', 22, '#16a34a')} Квитанция найдена</span></h1>
            <div class="ok">
                <b>Лицевой счёт:</b> {acct}<br>
                <b>Период:</b> {period_esc}<br>
                <b>Адрес:</b> {addr}<br>
                <b>Дата загрузки:</b> {uploaded_at}<br>
                <b>База обновлена:</b> {database_updated}
            </div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:16px">
                <button type="button" class="btn" onclick="openPdfModal('{token}', 'Квитанция: {acct} ({period_esc})')">{icon('eye', 15)} Быстрый просмотр</button>
                <a class="btn btn-green" href="{download_path}?token={token}">{icon('upload', 15)} Скачать PDF</a>
            </div>
            <br>
            <a class="back-link" href="{kvit_path}" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Новый поиск</a>
        </div>'''
    else:
        periods_html = ''
        for r in receipts:
            period_esc = html.escape(r['period'])
            token = r['access_token']
            uploaded_at = _format_receipt_timestamp(r.get('uploaded_at'))
            periods_html += f'''<div class="period-card">
                <span class="period-name" style="display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap">{icon('file_text', 16, '#3b82f6')} <span>{period_esc}</span><small style="display:block;width:100%;font-size:12px;color:#64748b;font-weight:400">Загружена: {uploaded_at}</small></span>
                <div class="period-actions">
                    <button type="button" class="btn btn-sm" onclick="openPdfModal('{token}', 'Квитанция: {acct} ({period_esc})')">{icon('eye', 13)} Просмотр</button>
                    <a class="btn-outline btn btn-sm" href="{receipt_path}?token={token}" target="_blank">Вкладка</a>
                    <a class="btn btn-green btn-sm" href="{download_path}?token={token}">Скачать</a>
                </div>
            </div>'''

        return f'''<div class="card">
            <h1><span style="display:inline-flex;align-items:center;gap:6px">{icon('check_circle', 22, '#16a34a')} Квитанции найдены</span></h1>
            <div class="ok">
                <b>Лицевой счёт:</b> {acct}<br>
                <b>Адрес:</b> {addr}<br>
                <b>Доступно квитанций:</b> {len(receipts)}
                <br><b>База обновлена:</b> {_format_receipt_timestamp(database_updated_at)}
            </div>
            <h2 style="font-size:17px;margin:24px 0 12px;color:#334155">Выберите период:</h2>
            {periods_html}
            <br>
            <a class="back-link" href="{kvit_path}" style="display:inline-flex;align-items:center;gap:4px">{icon('arrow_left', 13)} Новый поиск</a>
        </div>'''

def render_address_clarification_prompt(address_query: str, period_filter: str, message: str, periods=None):
    q_esc = html.escape(address_query)
    search_path = localized_path('/search')
    kvit_path = localized_path('/kvit/')
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

        <form action="{search_path}" method="get" style="margin-top:16px">
            <label>Уточните адрес (улица, номер дома, квартира):</label>
            <input name="address" type="search" value="{q_esc}" placeholder="Например: станц. Шокай, ул. Автобаза, дом 1" required autofocus>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button class="btn">{icon('search', 15)} Найти квитанцию</button>
        </form>

        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
            <a class="btn-outline btn" href="{kvit_path}" style="border-color:#64748b;color:#64748b">{icon('hash', 14)} Поиск по номеру счёта</a>
        </div>
    </div>'''

def render_address_not_found(address_query: str, period_filter: str, message: str, periods=None):
    q_esc = html.escape(address_query)
    search_path = localized_path('/search')
    kvit_path = localized_path('/kvit/')
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

        <form action="{search_path}" method="get" style="margin-top:16px">
            <label>Попробуйте ввести адрес ещё раз:</label>
            <input name="address" type="search" value="{q_esc}" placeholder="Например: станц. Шокай, ул. Автобаза, дом 1" required autofocus>
            <label>Период</label>
            <select name="period">
                {period_options}
            </select>
            <button class="btn">{icon('search', 15)} Искать снова</button>
        </form>

        <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px">
            <a class="btn-outline btn" href="{kvit_path}" style="border-color:#64748b;color:#64748b">{icon('hash', 14)} Поиск по лицевому счёту</a>
        </div>
    </div>'''

def render_address_search_results(address_query: str, period_filter: str, accounts: list):
    """Обратная совместимость: если передан 1 счет — рендерит перенаправление, иначе форму уточнения."""
    if accounts and len(accounts) == 1:
        return render_address_clarification_prompt(address_query, period_filter, "Найдена 1 запись.")
    return render_address_clarification_prompt(address_query, period_filter, "Пожалуйста, укажите точный номер дома и квартиры.")
