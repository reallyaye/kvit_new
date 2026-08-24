from templates.icons import icon


def layout(body, active='search', is_admin=False, csrf_token=''):
    nav_items = [
        ('search',  '/',          'Поиск квитанции', False, 'search'),
        ('upload',  '/upload',    'Загрузка PDF', True, 'upload'),
        ('reconcile', '/reconcile', 'Сверка', True, 'reconcile'),
    ]
    nav_html = ''
    for key, href, label, protected, icon_name in nav_items:
        cls = ' active' if key == active else ''
        sec_icon = f"{icon('lock', 13)} " if protected and not is_admin else f"{icon(icon_name, 15)} "
        nav_html += f'<a class="nav-link{cls}" href="{href}">{sec_icon}{label}</a>'

    # Кнопка входа/выхода
    if is_admin:
        nav_html += f'<a class="nav-link nav-auth" href="/logout">{icon("logout", 15)} Выход</a>'
    else:
        nav_html += f'<a class="nav-link nav-auth" href="/login">{icon("login", 15)} Вход</a>'

    csrf_meta = f'<meta name="csrf-token" content="{csrf_token}">\n' if csrf_token else ''

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{csrf_meta}<title>Квитанции</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#1a1a2e}}
.topbar{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:0 24px;display:flex;align-items:center;gap:32px;height:56px;box-shadow:0 2px 8px #00000030;flex-wrap:wrap}}
.topbar .logo{{color:#e2e8f0;font-weight:700;font-size:18px;white-space:nowrap}}
.nav-link{{color:#94a3b8;text-decoration:none;font-size:15px;padding:16px 4px;border-bottom:3px solid transparent;transition:.2s;display:inline-flex;align-items:center;gap:6px}}
.nav-link:hover{{color:#e2e8f0}}
.nav-link.active{{color:#fff;border-bottom-color:#3b82f6}}
.nav-auth{{margin-left:auto}}
.wrap{{max-width:900px;margin:32px auto;padding:0 20px}}
.card{{background:#fff;border-radius:14px;padding:28px 32px;box-shadow:0 1px 4px #0001,0 4px 16px #0001;margin-bottom:24px}}
h1{{margin:0 0 8px;font-size:22px;color:#1a1a2e}}
.subtitle{{color:#64748b;margin:0 0 24px;font-size:15px}}
label{{display:block;font-weight:600;margin:16px 0 6px;font-size:14px;color:#334155}}
input[type=text],input[type=search],input[type=password]{{width:100%;padding:12px 16px;border:1.5px solid #cbd5e1;border-radius:10px;font-size:16px;transition:.2s;outline:none}}
.login-card{{max-width:400px;margin:80px auto}}
input:focus{{border-color:#3b82f6;box-shadow:0 0 0 3px #3b82f620}}
.btn{{display:inline-block;margin-top:12px;padding:12px 24px;border:0;border-radius:10px;background:#3b82f6;color:white;cursor:pointer;font-size:15px;font-weight:600;text-decoration:none;transition:.15s}}
.btn:hover{{background:#2563eb}}
.btn-green{{background:#16a34a}}.btn-green:hover{{background:#15803d}}
.btn-outline{{background:transparent;color:#3b82f6;border:1.5px solid #3b82f6}}.btn-outline:hover{{background:#eff6ff}}
.ok{{padding:16px 20px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;margin:16px 0;color:#166534}}
.err{{padding:16px 20px;background:#fef2f2;border:1px solid #fecaca;border-radius:10px;margin:16px 0;color:#991b1b}}
.warn{{padding:16px 20px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px;margin:16px 0;color:#92400e}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin:20px 0}}
.stat-box{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:20px;text-align:center}}
.stat-num{{font-size:32px;font-weight:700;color:#1e293b}}
.stat-label{{font-size:13px;color:#64748b;margin-top:4px}}
.stat-box.green .stat-num{{color:#16a34a}}
.stat-box.red .stat-num{{color:#dc2626}}
.stat-box.blue .stat-num{{color:#2563eb}}
table{{width:100%;border-collapse:collapse;margin-top:16px;font-size:14px}}
th{{text-align:left;padding:10px 12px;background:#f8fafc;border-bottom:2px solid #e2e8f0;color:#475569;font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.5px}}
td{{padding:10px 12px;border-bottom:1px solid #f1f5f9}}
tr:hover td{{background:#f8fafc}}
.upload-zone{{border:2px dashed #cbd5e1;border-radius:14px;padding:48px 24px;text-align:center;color:#64748b;transition:.2s;cursor:pointer;position:relative}}
.upload-zone:hover,.upload-zone.drag{{border-color:#3b82f6;background:#eff6ff;color:#3b82f6}}
.upload-zone input[type=file]{{position:absolute;inset:0;opacity:0;cursor:pointer}}
.upload-zone .icon{{font-size:48px;margin-bottom:12px}}
.tag{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}}
.tag-ok{{background:#dcfce7;color:#166534}}.tag-err{{background:#fee2e2;color:#991b1b}}.tag-warn{{background:#fef3c7;color:#92400e}}
.pagination{{display:flex;gap:8px;margin-top:16px;align-items:center;justify-content:center}}
.pagination a,.pagination span{{padding:8px 14px;border-radius:8px;text-decoration:none;font-size:14px}}
.pagination a{{color:#3b82f6;border:1px solid #e2e8f0}}.pagination a:hover{{background:#eff6ff}}
.pagination span.current{{background:#3b82f6;color:#fff;border:1px solid #3b82f6}}
.back-link{{color:#3b82f6;text-decoration:none;font-size:14px}}
.back-link:hover{{text-decoration:underline}}
.filter-tab{{padding:8px 18px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;color:#475569;background:#f1f5f9;border:1.5px solid transparent;transition:.15s}}
.filter-tab:hover{{background:#e2e8f0}}
.filter-tab.active{{background:#3b82f6;color:#fff;border-color:#3b82f6}}
select{{width:100%;padding:12px 16px;border:1.5px solid #cbd5e1;border-radius:10px;font-size:16px;transition:.2s;outline:none;background:#fff;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23475569' d='M6 8L1 3h10z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 14px center;cursor:pointer}}
select:focus{{border-color:#3b82f6;box-shadow:0 0 0 3px #3b82f620}}
.period-card{{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border:1.5px solid #e2e8f0;border-radius:12px;margin-bottom:10px;transition:.2s;background:#f8fafc}}
.period-card:hover{{border-color:#3b82f6;background:#eff6ff;transform:translateY(-1px);box-shadow:0 2px 8px #3b82f615}}
.period-card .period-name{{font-weight:600;font-size:16px;color:#1e293b}}
.period-card .period-actions{{display:flex;gap:8px}}
.period-card .period-actions a{{padding:8px 16px;font-size:13px;border-radius:8px;font-weight:600;text-decoration:none;transition:.15s}}
.btn-sm{{padding:8px 16px!important;font-size:13px!important;margin-top:0!important}}
.period-filter{{display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
.period-filter label{{margin:0;font-size:14px;white-space:nowrap}}
.period-filter select{{width:auto;min-width:200px}}
.progress-wrap{{background:#e2e8f0;border-radius:10px;height:26px;overflow:hidden;margin:16px 0;position:relative}}
.progress-fill{{background:linear-gradient(90deg,#3b82f6,#16a34a);height:100%;width:0%;transition:width .2s ease;border-radius:10px}}
.progress-text{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;color:#1e293b}}
.log-box{{background:#0f172a;color:#f8fafc;padding:16px;border-radius:10px;font-family:Consolas,monospace;font-size:13px;max-height:220px;overflow-y:auto;margin-top:16px;white-space:pre-wrap;line-height:1.5}}
.mode-tabs{{display:flex;gap:10px;margin-bottom:20px;border-bottom:2px solid #e2e8f0;padding-bottom:12px}}
.mode-tab{{background:transparent;border:0;padding:10px 18px;font-size:15px;font-weight:600;color:#64748b;cursor:pointer;border-radius:8px;transition:.15s}}
.mode-tab:hover{{color:#1e293b;background:#f1f5f9}}
.mode-tab.active{{color:#fff;background:#3b82f6}}
.search-tabs{{margin-bottom:24px;border-bottom:1.5px solid #e2e8f0}}
.address-list{{display:flex;flex-direction:column;gap:10px;margin-top:16px}}
.address-item{{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 20px;background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:12px;transition:.2s}}
.address-item:hover{{border-color:#3b82f6;background:#eff6ff;box-shadow:0 2px 8px #3b82f615;transform:translateY(-1px)}}
.address-info{{display:flex;flex-direction:column;gap:4px}}
.address-text{{font-size:15px;font-weight:600;color:#1e293b}}
.address-acc{{font-size:13px;color:#64748b}}
.ws-indicator{{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;background:#0f172a;color:#94a3b8;border:1px solid #334155;margin-left:auto}}
.ws-dot{{width:8px;height:8px;border-radius:50%;background:#ef4444;transition:.3s;display:inline-block}}
.ws-indicator.online .ws-dot{{background:#22c55e;box-shadow:0 0 8px #22c55e}}
.ws-indicator.online{{color:#e2e8f0;border-color:#166534}}

.pulse-dot{{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e;display:inline-block;animation:livePulse 2s infinite ease-in-out}}
@keyframes livePulse{{0%,100%{{opacity:1;transform:scale(1);box-shadow:0 0 8px #22c55e}}50%{{opacity:.35;transform:scale(0.85);box-shadow:0 0 2px #22c55e}}}}
.live-pulse-glow{{animation:highlightChange 1.2s ease-out}}
@keyframes highlightChange{{0%{{transform:scale(1.1);color:#3b82f6;text-shadow:0 0 10px rgba(59,130,246,0.7)}}50%{{transform:scale(1.05);color:#16a34a;text-shadow:0 0 6px rgba(22,163,74,0.5)}}100%{{transform:scale(1)}}}}
.live-sync-pulse{{background:#16a34a26!important;border-color:#22c55e!important}}
.live-val{{display:inline-block;transition:all .3s ease}}

@media(max-width:768px){{.topbar{{height:auto;padding:12px 16px;gap:12px}}.ws-indicator{{order:2;margin-left:auto}}}}
@media(max-width:600px){{.wrap{{margin:16px auto;padding:0 12px}}.card{{padding:20px 18px}}.stats{{grid-template-columns:1fr 1fr}}.period-card{{flex-direction:column;align-items:flex-start;gap:12px}}.period-card .period-actions{{width:100%}}.period-card .period-actions a{{flex:1;text-align:center}}.address-item{{flex-direction:column;align-items:flex-start;gap:12px}}.address-item .btn{{width:100%;text-align:center}}}}
</style></head><body>
<div class="topbar">
    <span class="logo">Квитанции</span>
    <span class="ws-indicator" id="wsIndicator" title="WebSocket статус соединения"><span class="ws-dot"></span><span id="wsLabel">WS Offline</span></span>
    {nav_html}
</div>
<div class="wrap">{body}</div>

<script>
let appWS = null;
let lastStatsState = null;
let pollIntervalId = null;

function formatNumber(num) {{
    if (num === null || num === undefined) return '0';
    return num.toString().replace(/\\B(?=(\\d{3})+(?!\\d))/g, " ");
}}

function flashElement(el) {{
    if (!el) return;
    el.classList.remove('live-pulse-glow');
    void el.offsetWidth;
    el.classList.add('live-pulse-glow');
}}

async function pollDatabaseStats() {{
    try {{
        const params = new URLSearchParams(window.location.search);
        const currentPeriod = params.get('period') || '';
        const url = '/api/stats' + (currentPeriod ? '?period=' + encodeURIComponent(currentPeriod) : '');
        const res = await fetch(url, {{ headers: {{ 'Accept': 'application/json' }}, cache: 'no-store' }});
        if (!res.ok) return;
        const data = await res.json();
        if (data.status !== 'ok') return;

        applyLiveStats(data);
    }} catch (e) {{}}
}}

function applyLiveStats(data) {{
    const isFirst = (lastStatsState === null);
    const prev = lastStatsState || {{}};

    // 1. Верхний бар
    const hAcc = document.getElementById('liveAccHeader');
    const hRec = document.getElementById('liveRecHeader');
    if (hAcc && hAcc.textContent !== formatNumber(data.total_accounts)) {{
        hAcc.textContent = formatNumber(data.total_accounts);
        if (!isFirst) flashElement(hAcc);
    }}
    if (hRec && hRec.textContent !== formatNumber(data.total_receipts)) {{
        hRec.textContent = formatNumber(data.total_receipts);
        if (!isFirst) flashElement(hRec);
    }}

    // 2. Виджеты главной страницы (Поиск)
    const stAcc = document.getElementById('statTotalAccounts');
    if (stAcc && stAcc.textContent !== formatNumber(data.total_accounts)) {{
        stAcc.textContent = formatNumber(data.total_accounts);
        if (!isFirst) flashElement(stAcc);
    }}
    const stRec = document.getElementById('statTotalReceipts');
    if (stRec && stRec.textContent !== formatNumber(data.total_receipts)) {{
        stRec.textContent = formatNumber(data.total_receipts);
        if (!isFirst) flashElement(stRec);
    }}
    const stPer = document.getElementById('statPeriodsCount');
    if (stPer && stPer.textContent !== formatNumber(data.periods_count)) {{
        stPer.textContent = formatNumber(data.periods_count);
        if (!isFirst) flashElement(stPer);
    }}
    const stCov = document.getElementById('statCoveragePct');
    if (stCov && stCov.textContent !== (data.coverage_pct + '%')) {{
        stCov.textContent = data.coverage_pct + '%';
        if (!isFirst) flashElement(stCov);
    }}

    // 3. Карточки страницы сверки (/reconcile)
    const rAcc = document.getElementById('recTotalAccounts');
    if (rAcc && rAcc.textContent !== formatNumber(data.total_accounts)) {{
        rAcc.textContent = formatNumber(data.total_accounts);
        if (!isFirst) flashElement(rAcc);
    }}
    const rMatch = document.getElementById('recMatched');
    if (rMatch && rMatch.textContent !== formatNumber(data.matched)) {{
        rMatch.textContent = formatNumber(data.matched);
        if (!isFirst) flashElement(rMatch);
    }}
    const rUnmatch = document.getElementById('recUnmatched');
    if (rUnmatch && rUnmatch.textContent !== formatNumber(data.unmatched)) {{
        rUnmatch.textContent = formatNumber(data.unmatched);
        if (!isFirst) flashElement(rUnmatch);
    }}
    const rRec = document.getElementById('recTotalReceipts');
    if (rRec && rRec.textContent !== formatNumber(data.total_receipts)) {{
        rRec.textContent = formatNumber(data.total_receipts);
        if (!isFirst) flashElement(rRec);
    }}
    const rOrph = document.getElementById('recOrphans');
    if (rOrph && rOrph.textContent !== formatNumber(data.orphans)) {{
        rOrph.textContent = formatNumber(data.orphans);
        if (!isFirst) flashElement(rOrph);
    }}
    const rCov = document.getElementById('recCoverageSubtitle');
    if (rCov && rCov.textContent !== (data.coverage_pct + '%')) {{
        rCov.textContent = data.coverage_pct + '%';
        if (!isFirst) flashElement(rCov);
    }}

    // 4. Счетчики табов сверки
    const tabAll = document.getElementById('tabCountAll');
    if (tabAll) tabAll.textContent = formatNumber(data.total_accounts);
    const tabWith = document.getElementById('tabCountWith');
    if (tabWith) tabWith.textContent = formatNumber(data.matched);
    const tabWithout = document.getElementById('tabCountWithout');
    if (tabWithout) tabWithout.textContent = formatNumber(data.unmatched);
    const tabOrphans = document.getElementById('tabCountOrphans');
    if (tabOrphans) tabOrphans.textContent = formatNumber(data.orphans);

    // 5. Динамическое обновление выпадающих списков периодов (если появились новые периоды)
    if (data.periods && (!prev.periods || JSON.stringify(prev.periods) !== JSON.stringify(data.periods))) {{
        document.querySelectorAll('select[name="period"], #period-select').forEach(sel => {{
            const currentVal = sel.value;
            const hasAll = sel.options.length > 0 && sel.options[0].value === '';
            let html = hasAll ? '<option value="">Все периоды</option>' : '';
            data.periods.forEach(p => {{
                const s = (p === currentVal) ? ' selected' : '';
                html += `<option value="${{p}}"${{s}}>${{p}}</option>`;
            }});
            sel.innerHTML = html;
            if (currentVal) sel.value = currentVal;
        }});
    }}

    // Индикация пульсации при изменении значений
    const badge = document.getElementById('liveSyncStatus');
    if (badge && !isFirst && (prev.total_receipts !== data.total_receipts || prev.total_accounts !== data.total_accounts)) {{
        badge.classList.add('live-sync-pulse');
        setTimeout(() => badge.classList.remove('live-sync-pulse'), 1200);
    }}

    lastStatsState = data;
}}

function initAppWebSocket() {{
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = protocol + '//' + location.host + '/ws';
    try {{
        appWS = new WebSocket(wsUrl);
        appWS.onopen = function() {{
            const ind = document.getElementById('wsIndicator');
            const lbl = document.getElementById('wsLabel');
            if (ind) ind.classList.add('online');
            if (lbl) lbl.textContent = 'WS Live';
            pollDatabaseStats();
        }};
        appWS.onclose = function() {{
            const ind = document.getElementById('wsIndicator');
            const lbl = document.getElementById('wsLabel');
            if (ind) ind.classList.remove('online');
            if (lbl) lbl.textContent = 'WS Offline';
            setTimeout(initAppWebSocket, 3000);
        }};
        appWS.onerror = function() {{
            try {{ appWS.close(); }} catch(e) {{}}
        }};
        appWS.onmessage = function(e) {{
            try {{
                const msg = JSON.parse(e.data);
                window.dispatchEvent(new CustomEvent('app-ws-message', {{ detail: msg }}));
                pollDatabaseStats();
            }} catch(err) {{}}
        }};
    }} catch(e) {{
        setTimeout(initAppWebSocket, 4000);
    }}
}}

document.addEventListener('DOMContentLoaded', function() {{
    initAppWebSocket();
    pollDatabaseStats();
    if (pollIntervalId) clearInterval(pollIntervalId);
    pollIntervalId = setInterval(pollDatabaseStats, 3000);
}});
</script>
</body></html>'''
