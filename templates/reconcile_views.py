import html

from templates.admin_cms_views import _admin_nav_bar
from templates.icons import icon


def render_reconcile_page(data: dict):
    filt = data['filt']
    period_filter = data['period_filter']
    all_periods = data['all_periods']
    total_accounts = data['total_accounts']
    total_receipts = data['total_receipts']
    matched = data['matched']
    unmatched_count = data['unmatched']
    orphans = data['orphans']
    list_count = data['list_count']
    rows = data['rows']
    page_num = data['page_num']
    per_page = data['per_page']

    period_param = f'&period={html.escape(period_filter)}' if period_filter else ''
    is_orphan_tab = (filt == 'orphans')

    # Пагинация
    total_pages = max(1, (list_count + per_page - 1) // per_page)
    pag = '<div class="pagination">'
    if page_num > 1:
        pag += f'<a href="/reconcile?filter={filt}{period_param}&page={page_num-1}">← Назад</a>'

    half_window = 5
    start_page = max(1, page_num - half_window)
    end_page = min(total_pages, page_num + half_window - 1)
    if end_page - start_page + 1 < 10:
        if start_page == 1:
            end_page = min(total_pages, start_page + 9)
        elif end_page == total_pages:
            start_page = max(1, end_page - 9)

    if start_page > 1:
        pag += f'<a href="/reconcile?filter={filt}{period_param}&page=1">1</a>'
        if start_page > 2:
            pag += '<span style="padding:8px 4px;color:#94a3b8">…</span>'

    for p in range(start_page, end_page + 1):
        if p == page_num:
            pag += f'<span class="current">{p}</span>'
        else:
            pag += f'<a href="/reconcile?filter={filt}{period_param}&page={p}">{p}</a>'

    if end_page < total_pages:
        if end_page < total_pages - 1:
            pag += '<span style="padding:8px 4px;color:#94a3b8">…</span>'
        pag += f'<a href="/reconcile?filter={filt}{period_param}&page={total_pages}">{total_pages}</a>'

    if page_num < total_pages:
        pag += f'<a href="/reconcile?filter={filt}{period_param}&page={page_num+1}">Далее →</a>'
    pag += '</div>'

    pct = round(matched / total_accounts * 100, 1) if total_accounts else 0

    period_options = '<option value="">Все периоды</option>'
    for p in all_periods:
        sel = ' selected' if p['period'] == period_filter else ''
        period_options += f'<option value="{html.escape(p["period"])}"{sel}>{html.escape(p["period"])}</option>'

    period_select_html = f'''<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:16px">
        <div class="period-filter" style="margin-bottom:0">
            <label for="period-select"><b>Период:</b></label>
            <select id="period-select" onchange="window.location.href='/reconcile?filter={filt}&period='+encodeURIComponent(this.value)">
                {period_options}
            </select>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
            <button type="button" class="btn btn-outline" id="btnSyncFs" onclick="syncWithFilesystem()" style="padding:7px 14px;font-size:13px;display:flex;align-items:center;gap:6px">
                {icon('refresh', 14)} Синхронизировать с диском
            </button>
            <button type="button" class="btn btn-outline" id="btnPurgeMissing" onclick="purgeMissingReceipts()" style="padding:7px 14px;font-size:13px;display:flex;align-items:center;gap:6px;color:#ef4444;border-color:#fca5a5">
                {icon('trash', 14)} Очистить отсутствующие
            </button>
        </div>
    </div>'''

    def tab_cls(key):
        return ' active' if filt == key else ''
    orphan_tab_style = 'background:#f59e0b;color:#fff;border-color:#f59e0b' if filt == 'orphans' else 'border-color:#f59e0b'
    tabs_html = f'''<div style="display:flex;gap:8px;margin:20px 0;flex-wrap:wrap">
        <a href="/reconcile?filter=all{period_param}" class="filter-tab{tab_cls('all')}">Все (<span id="tabCountAll">{total_accounts}</span>)</a>
        <a href="/reconcile?filter=with{period_param}" class="filter-tab{tab_cls('with')}">С квитанцией (<span id="tabCountWith">{matched}</span>)</a>
        <a href="/reconcile?filter=without{period_param}" class="filter-tab{tab_cls('without')}">Без квитанции (<span id="tabCountWithout">{unmatched_count}</span>)</a>
        <a href="/reconcile?filter=orphans{period_param}" class="filter-tab{tab_cls('orphans')}" style="{orphan_tab_style}">Без лицевого счёта (<span id="tabCountOrphans">{orphans}</span>)</a>
    </div>'''

    table_rows = ''
    if is_orphan_tab:
        for r in rows:
            table_rows += f'''<tr>
                <td>{html.escape(r["account_number"])}</td>
                <td>{html.escape(r["period"] or "—")}</td>
                <td>{html.escape(r["pdf_file"] or "—")}</td>
                <td><span class="tag tag-warn">Нет в базе</span></td>
            </tr>'''
        table_html = f'''<table>
            <tr><th>Лицевой счёт</th><th>Период</th><th>Файл</th><th>Статус</th></tr>
            {table_rows}
        </table>{pag}''' if rows else '<p style="color:#64748b">Нет квитанций-сирот. Все квитанции привязаны к лицевым счетам.</p>'
    else:
        for r in rows:
            has_receipt = r['pdf_file'] is not None
            status = '<span class="tag tag-ok">Есть</span>' if has_receipt else '<span class="tag tag-err">Нет</span>'
            period_text = html.escape(r['period'] or '') if has_receipt else '—'
            table_rows += f'''<tr>
                <td>{html.escape(r["account_number"])}</td>
                <td>{html.escape(r["customer_name"] or "—")}</td>
                <td>{html.escape(r["address"] or "—")}</td>
                <td>{period_text}</td>
                <td>{status}</td>
            </tr>'''
        table_html = f'''<table>
            <tr><th>Лицевой счёт</th><th>Контрагент</th><th>Адрес</th><th>Период</th><th>Квитанция</th></tr>
            {table_rows}
        </table>{pag}''' if rows else '<p style="color:#64748b">Нет записей для отображения.</p>'

    period_label = f' за {html.escape(period_filter)}' if period_filter else ''
    if filt == 'with':
        list_title = f'Список лицевых счетов с квитанцией{period_label}'
    elif filt == 'without':
        list_title = f'Список лицевых счетов без квитанции{period_label}'
    elif filt == 'orphans':
        list_title = f'Квитанции без лицевого счёта в базе{period_label}'
    else:
        list_title = f'Все лицевые счета{period_label}'

    role = data.get('role', 'admin')
    username = data.get('username', 'admin')

    return f'''
    {_admin_nav_bar('reconcile', role=role, username=username)}
    <div class="stats" style="grid-template-columns:repeat(auto-fit,minmax(180px,1fr))">
        <div class="card stat-card">
            <div class="num" id="statTotalAccounts">{total_accounts}</div>
            <div class="lbl">Всего лицевых счетов</div>
        </div>
        <div class="card stat-card">
            <div class="num" style="color:#16a34a" id="statMatched">{matched}</div>
            <div class="lbl">Счетов с квитанцией</div>
        </div>
        <div class="card stat-card">
            <div class="num" style="color:#ef4444" id="statUnmatched">{unmatched_count}</div>
            <div class="lbl">Счетов без квитанции</div>
        </div>
        <div class="card stat-card">
            <div class="num" id="statTotalReceipts">{total_receipts}</div>
            <div class="lbl">Всего квитанций</div>
        </div>
        <div class="card stat-card">
            <div class="num" style="color:#f59e0b" id="statOrphans">{orphans}</div>
            <div class="lbl">Квитанций без счёта</div>
        </div>
        <div class="card stat-card">
            <div class="num" style="color:#2563eb" id="statPercent">{pct}%</div>
            <div class="lbl">Процент покрытия</div>
        </div>
    </div>
    <div class="card">
        <h1>{list_title}</h1>
        {period_select_html}
        {tabs_html}
        {table_html}
    </div>
    <script>
    async function syncWithFilesystem() {{
        const btn = document.getElementById('btnSyncFs');
        if (!btn) return;
        if (!confirm('Выполнить безопасную синхронизацию с диском?\\n\\nСтатус отсутствующих файлов будет переведён в missing без удаления метаданных из БД.')) {{
            return;
        }}
        btn.disabled = true;
        btn.innerHTML = '{icon('clock', 14)} Проверка файлов...';
        try {{
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            const csrfVal = csrfMeta ? csrfMeta.content : '';
            const headers = csrfVal ? {{ 'X-CSRF-Token': csrfVal }} : {{}};

            const res = await fetch('/api/sync-receipts', {{
                method: 'POST',
                headers: headers
            }});
            const data = await res.json();
            if (data.success) {{
                alert(data.message);
                window.location.reload();
            }} else {{
                alert('Ошибка: ' + (data.error || 'Не удалось выполнить синхронизацию'));
                btn.disabled = false;
                btn.innerHTML = '{icon('refresh', 14)} Синхронизировать с диском';
            }}
        }} catch (e) {{
            alert('Ошибка сети: ' + e.message);
            btn.disabled = false;
            btn.innerHTML = '{icon('refresh', 14)} Синхронизировать с диском';
        }}
    }}

    async function purgeMissingReceipts() {{
        const btn = document.getElementById('btnPurgeMissing');
        if (!btn) return;
        if (!confirm('ВНИМАНИЕ: Вы действительно хотите безвозвратно удалить из базы все записи со статусом «missing»?\\n\\nЭту операцию следует выполнять только если файлы удалены с диска намеренно.')) {{
            return;
        }}
        btn.disabled = true;
        btn.innerHTML = '{icon('clock', 14)} Очистка...';
        try {{
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            const csrfVal = csrfMeta ? csrfMeta.content : '';
            const headers = csrfVal ? {{ 'X-CSRF-Token': csrfVal }} : {{}};

            const res = await fetch('/api/purge-missing-receipts', {{
                method: 'POST',
                headers: headers
            }});
            const data = await res.json();
            if (data.success) {{
                alert(data.message);
                window.location.reload();
            }} else {{
                alert('Ошибка: ' + (data.error || 'Не удалось выполнить очистку'));
                btn.disabled = false;
                btn.innerHTML = '{icon('trash', 14)} Очистить отсутствующие';
            }}
        }} catch (e) {{
            alert('Ошибка сети: ' + e.message);
            btn.disabled = false;
            btn.innerHTML = '{icon('trash', 14)} Очистить отсутствующие';
        }}
    }}
    </script>'''
