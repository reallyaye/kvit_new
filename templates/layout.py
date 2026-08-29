from templates.icons import icon


def layout(body, active='search', is_admin=False, csrf_token=''):
    nav_html = ''
    ws_indicator_html = ''
    
    if is_admin:
        nav_items = [
            ('pages',     '/admin/pages', 'Страницы сайта', True, 'edit'),
            ('media',     '/admin/media', 'Медиа и файлы', True, 'image'),
            ('upload',    '/upload',      'Загрузка PDF', True, 'upload'),
            ('reconcile', '/reconcile',   'Сверка', True, 'reconcile'),
            ('search',    '/kvit/',       'Поиск квитанций', False, 'search'),
        ]
        for key, href, label, protected, icon_name in nav_items:
            cls = ' active' if key == active else ''
            nav_html += f'<a class="nav-link{cls}" href="{href}">{icon(icon_name, 15)} {label}</a>'
        nav_html += f'<a class="nav-link nav-auth" href="/logout">{icon("logout", 15)} Выход</a>'
        ws_indicator_html = '<span class="ws-indicator" id="wsIndicator" title="WebSocket статус соединения"><span class="ws-dot"></span><span id="wsLabel">WS Offline</span></span>'

    csrf_meta = f'<meta name="csrf-token" content="{csrf_token}">\n' if csrf_token else ''

    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, viewport-fit=cover">
<meta name="theme-color" content="#0f172a">
<link rel="manifest" href="/manifest.json">
<script>
if ('serviceWorker' in navigator) {{
    window.addEventListener('load', function() {{
        navigator.serviceWorker.register('/sw.js').catch(function() {{}});
    }});
}}
</script>
<link rel="stylesheet" href="/static/css/heroui.css?v=1">
{csrf_meta}<title>КРЭК | Квитанции</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Segoe UI',Arial,sans-serif;background:#f0f2f5;color:#1a1a2e}}
.topbar{{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:0 24px;display:flex;align-items:center;gap:24px;height:56px;box-shadow:0 2px 8px #00000030;flex-wrap:wrap}}
.topbar .logo{{color:#e2e8f0;font-weight:700;font-size:18px;white-space:nowrap}}
.topbar .logo-sub{{color:#64748b;font-size:13px;white-space:nowrap;margin-left:-16px;font-weight:400}}
.nav-link{{color:#94a3b8;text-decoration:none;font-size:15px;padding:16px 4px;border-bottom:3px solid transparent;transition:.2s;display:inline-flex;align-items:center;gap:6px}}
.nav-link:hover{{color:#e2e8f0}}
.nav-link.active{{color:#fff;border-bottom-color:#3b82f6}}
.nav-back{{color:#60a5fa!important;font-size:13px;padding:10px 12px;border:1px solid #334155;border-radius:8px;border-bottom:1px solid #334155!important;margin-right:8px;transition:background .15s,color .15s}}
.nav-back:hover{{background:#0f172a;color:#fff!important}}
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

.sub-tabs{{display:flex;gap:8px;margin-bottom:16px;background:#f1f5f9;padding:4px;border-radius:10px}}
.sub-tab{{flex:1;background:transparent;border:0;padding:8px 12px;font-size:13px;font-weight:600;color:#64748b;cursor:pointer;border-radius:8px;transition:.15s;text-align:center}}
.sub-tab:hover{{color:#1e293b}}
.sub-tab.active{{background:#fff;color:#1e293b;box-shadow:0 1px 3px #00000015}}
.grid-fields{{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin-bottom:8px}}
.typo-badge{{background:#fef3c7;border:1px solid #fde68a;color:#92400e;border-radius:10px;padding:10px 14px;font-size:13px;margin:12px 0;display:flex;align-items:center;gap:8px}}
.search-loading-box{{display:flex;align-items:center;justify-content:center;gap:10px;padding:24px;color:#64748b;font-size:14px;font-weight:600}}
.spinner{{width:20px;height:20px;border:2.5px solid #cbd5e1;border-top-color:#3b82f6;border-radius:50%;animation:spin .8s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.receipt-card-anim{{animation:fadeInUp .25s ease-out}}
@keyframes fadeInUp{{from{{opacity:0;transform:translateY(8px)}}to{{opacity:1;transform:translateY(0)}}}}

/* Modal PDF Viewer */
.modal-backdrop{{position:fixed;inset:0;background:rgba(15,23,42,0.75);backdrop-filter:blur(4px);z-index:9999;display:none;align-items:center;justify-content:center;padding:16px}}
.modal-backdrop.active{{display:flex}}
.modal-window{{background:#fff;border-radius:16px;width:100%;max-width:960px;height:90vh;display:flex;flex-direction:column;box-shadow:0 25px 50px -12px rgba(0,0,0,0.35);overflow:hidden;animation:modalZoomIn .2s ease-out}}
@keyframes modalZoomIn{{from{{opacity:0;transform:scale(0.95)}}to{{opacity:1;transform:scale(1)}}}}
.modal-header{{padding:14px 20px;background:#1e293b;color:#fff;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #334155}}
.modal-title{{font-size:16px;font-weight:600;display:flex;align-items:center;gap:8px}}
.modal-actions{{display:flex;align-items:center;gap:8px}}
.modal-btn{{background:#334155;color:#e2e8f0;border:0;padding:6px 12px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:5px;transition:.15s}}
.modal-btn:hover{{background:#475569;color:#fff}}
.modal-btn-close{{background:#ef4444;color:#fff}}
.modal-btn-close:hover{{background:#dc2626}}
.modal-body{{flex:1;background:#f8fafc;position:relative}}
.modal-body iframe{{width:100%;height:100%;border:0}}

/* Modern Admin Top Navigation Bar */
.admin-top-nav-card{{background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;padding:10px 16px;margin-bottom:24px;box-shadow:0 4px 20px -2px rgba(15,23,42,0.06),0 2px 6px -1px rgba(15,23,42,0.04);display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}}
.admin-brand-badge{{display:flex;align-items:center;gap:10px;padding-right:14px;border-right:1.5px solid #f1f5f9}}
.admin-brand-icon{{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#2563eb 0%,#1d4ed8 100%);display:flex;align-items:center;justify-content:center;box-shadow:0 4px 10px rgba(37,99,235,0.28)}}
.admin-brand-text{{display:flex;flex-direction:column}}
.admin-brand-title{{font-weight:700;font-size:13.5px;color:#0f172a;line-height:1.2}}
.admin-brand-sub{{font-size:10.5px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.5px}}
.admin-tabs-list{{display:flex;align-items:center;gap:4px;flex-wrap:wrap;background:#f8fafc;padding:4px;border-radius:12px;border:1px solid #e2e8f0}}
.admin-tab-item{{display:inline-flex;align-items:center;gap:7px;padding:7px 13px;border-radius:8px;font-size:13.5px;font-weight:600;color:#475569;text-decoration:none;transition:all .18s cubic-bezier(0.4,0,0.2,1)}}
.admin-tab-item:hover{{background:#ffffff;color:#1e293b;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
.admin-tab-item.active{{background:linear-gradient(135deg,#2563eb 0%,#1d4ed8 100%);color:#ffffff!important;box-shadow:0 4px 12px rgba(37,99,235,0.32)}}
.admin-nav-actions{{display:flex;align-items:center;gap:8px;margin-left:auto}}
.admin-btn-portal{{display:inline-flex;align-items:center;gap:6px;padding:7px 13px;border-radius:8px;background:#eff6ff;color:#2563eb;font-size:13px;font-weight:600;text-decoration:none;border:1px solid #bfdbfe;transition:all .15s}}
.admin-btn-portal:hover{{background:#dbeafe;color:#1d4ed8;transform:translateY(-1px)}}
.admin-btn-logout{{display:inline-flex;align-items:center;gap:6px;padding:7px 12px;border-radius:8px;background:#fff1f2;color:#e11d48;font-size:13px;font-weight:600;text-decoration:none;border:1px solid #fecdd3;transition:all .15s}}
.admin-btn-logout:hover{{background:#ffe4e6;color:#be123c;transform:translateY(-1px)}}

@media(max-width:900px){{.admin-brand-badge{{border-right:0;width:100%;justify-content:space-between}}.admin-nav-actions{{margin-left:0;width:100%;justify-content:flex-end}}.admin-tabs-list{{width:100%}}}}
@media(max-width:768px){{.topbar{{height:auto;padding:12px 16px;gap:12px}}.ws-indicator{{order:2;margin-left:auto}}.grid-fields{{grid-template-columns:1fr 1fr}}.grid-fields > div:first-child{{grid-column:1/-1}}.modal-window{{height:95vh;max-width:100%}}}}
@media(max-width:600px){{.wrap{{margin:16px auto;padding:0 12px}}.card{{padding:20px 18px}}.stats{{grid-template-columns:1fr 1fr}}.period-card{{flex-direction:column;align-items:flex-start;gap:12px}}.period-card .period-actions{{width:100%}}.period-card .period-actions a,.period-card .period-actions button{{flex:1;text-align:center}}.address-item{{flex-direction:column;align-items:flex-start;gap:12px}}.address-item .btn{{width:100%;text-align:center}}.grid-fields{{grid-template-columns:1fr}}}}
</style></head><body>
<div class="topbar">
    <a href="/" style="text-decoration:none;display:inline-flex;align-items:center;gap:12px;">
        <img src="/images/logo.png?v=8" alt="ТОО КРЭК" style="height:36px;width:auto;object-fit:contain;filter:drop-shadow(0 0 8px rgba(56,189,248,0.45));">
        <span class="logo">ТОО &laquo;КРЭК&raquo;</span>
        <span class="logo-sub">Квитанции</span>
    </a>
    {ws_indicator_html}
    <a class="nav-link nav-back" href="/">{icon('arrow_left', 14)} На главную сайта</a>
    {nav_html}
</div>
<div class="wrap">{body}</div>

<!-- Modal PDF Viewer -->
<div id="pdfModal" class="modal-backdrop" onclick="handleModalBackdropClick(event)">
    <div class="modal-window">
        <div class="modal-header">
            <div class="modal-title" id="pdfModalTitle" style="display:flex;align-items:center;gap:6px">{icon('file_text', 16, '#3b82f6')} Просмотр квитанции</div>
            <div class="modal-actions">
                <a id="pdfModalDownload" class="modal-btn" href="#" download title="Скачать PDF" style="display:inline-flex;align-items:center;gap:5px">{icon('download', 14)} Скачать PDF</a>
                <button type="button" class="modal-btn modal-btn-close" onclick="closePdfModal()" title="Закрыть (Esc)">{icon('x', 16)}</button>
            </div>
        </div>
        <div class="modal-body">
            <iframe id="pdfModalFrame" src="about:blank"></iframe>
        </div>
    </div>
</div>

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

function openPdfModal(token, title) {{
    const modal = document.getElementById('pdfModal');
    const frame = document.getElementById('pdfModalFrame');
    const titleEl = document.getElementById('pdfModalTitle');
    const dlEl = document.getElementById('pdfModalDownload');
    if (!modal || !frame) return;

    const receiptUrl = '/receipt?token=' + encodeURIComponent(token);
    const downloadUrl = '/download?token=' + encodeURIComponent(token);

    if (titleEl) titleEl.innerHTML = title ? ('{icon('file_text', 16, '#3b82f6')} ' + title) : '{icon('file_text', 16, '#3b82f6')} Просмотр квитанции';
    if (dlEl) dlEl.href = downloadUrl;

    frame.src = receiptUrl;
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}}

function closePdfModal() {{
    const modal = document.getElementById('pdfModal');
    const frame = document.getElementById('pdfModalFrame');
    if (!modal) return;
    modal.classList.remove('active');
    if (frame) frame.src = 'about:blank';
    document.body.style.overflow = '';
}}

function handleModalBackdropClick(e) {{
    if (e.target && e.target.id === 'pdfModal') {{
        closePdfModal();
    }}
}}

window.switchSearchTab = function(tab) {{
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
}};

document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape' || e.key === 'Esc') {{
        closePdfModal();
    }}
}});

document.addEventListener('click', function(e) {{
    var target = e.target;
    var btn = target.closest('button, a');
    if (!btn) return;

    if (btn.id === 'tabBtnAddress') {{
        e.preventDefault();
        window.switchSearchTab('address');
    }} else if (btn.id === 'tabBtnAccount') {{
        e.preventDefault();
        window.switchSearchTab('account');
    }}
}});

document.addEventListener('DOMContentLoaded', function() {{
    initAppWebSocket();
    pollDatabaseStats();
    if (pollIntervalId) clearInterval(pollIntervalId);
    pollIntervalId = setInterval(pollDatabaseStats, 3000);
}});
</script>
</body></html>'''
