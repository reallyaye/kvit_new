import os

from templates.i18n import translate_html
from templates.icons import icon
from templates.locale import get_locale, localized_path
from templates.portal_cookies import (
    render_cookie_consent_html,
    render_portal_scripts,
)


def _asset_v(rel_path: str) -> str:
    """Автоматический cache-buster: возвращает timestamp изменения файла."""
    try:
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', rel_path.lstrip('/'))
        return str(int(os.path.getmtime(full_path)))
    except Exception:
        return '20260914'


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
        for key, href, label, _protected, icon_name in nav_items:
            cls = ' active' if key == active else ''
            nav_html += f'<a class="nav-link{cls}" href="{href}">{icon(icon_name, 15)} {label}</a>'
        nav_html += f'<a class="nav-link nav-auth" href="/logout">{icon("logout", 15)} Выход</a>'
        ws_indicator_html = '<span class="ws-indicator" id="wsIndicator" title="WebSocket статус соединения"><span class="ws-dot"></span><span id="wsLabel">WS Offline</span></span>'

    csrf_meta = f'<meta name="csrf-token" content="{csrf_token}">\n' if csrf_token else ''

    locale = get_locale()
    html_lang = 'kk' if locale == 'kk' else 'ru'
    ru_kvit = localized_path('/kvit/', 'ru')
    kk_kvit = localized_path('/kvit/', 'kk')
    kvit_layout_v = _asset_v('css/kvit_layout.css')
    cookie_v = _asset_v('css/cookie_consent.css')

    cookie_banner = render_cookie_consent_html()
    cookie_scripts = render_portal_scripts('kvit')

    return translate_html(f'''<!doctype html><html lang="{html_lang}"><head><meta charset="utf-8">
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
<link rel="stylesheet" href="/css/heroui.css?v=20260901">
<link rel="stylesheet" href="/css/kvit_layout.css?v={kvit_layout_v}">
<link rel="stylesheet" href="/css/cookie_consent.css?v={cookie_v}">
<link rel="alternate" hreflang="ru" href="https://krec.kz{ru_kvit}">
<link rel="alternate" hreflang="kk" href="https://krec.kz{kk_kvit}">
{csrf_meta}<title>КРЭК | Квитанции</title>
</head><body>
<div class="topbar">
    <a href="/" style="text-decoration:none;display:inline-flex;align-items:center;gap:12px;">
        <img src="/images/logo.png?v=8" alt="ТОО КРЭК" style="height:36px;width:auto;object-fit:contain;filter:drop-shadow(0 0 8px rgba(56,189,248,0.45));">
        <span class="logo">ТОО &laquo;КРЭК&raquo;</span>
        <span class="logo-sub">Квитанции</span>
    </a>
    {ws_indicator_html}
    <a class="nav-link nav-back" href="/">{icon('arrow_left', 14)} На главную сайта</a>
    <span style="display:inline-flex;gap:6px;align-items:center;margin-left:auto;font-size:12px;">
        <a href="{ru_kvit}" lang="ru" style="color:{'#38bdf8' if locale == 'ru' else '#94a3b8'};font-weight:700;text-decoration:none;">Рус</a>
        <span style="color:#475569;">/</span>
        <a href="{kk_kvit}" lang="kk" style="color:{'#38bdf8' if locale == 'kk' else '#94a3b8'};font-weight:700;text-decoration:none;">Қаз</a>
    </span>
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

    // 5. Динамическое обновление выпадающих списков периодов
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

<footer class="krec-sub-footer" style="margin-top:40px; padding:24px 20px; background:#0f172a; color:#94a3b8; font-size:13px; text-align:center; border-top:1px solid #1e293b;">
    <div style="max-width:900px; margin:0 auto; display:flex; flex-direction:column; gap:10px; align-items:center;">
        <div style="color:#e2e8f0; font-weight:600; font-size:14px;">ТОО «Карагандинская Региональная Энергетическая Компания» (ТОО «КРЭК»)</div>
        <div>БИН: 031140001297 &bull; 100000, Республика Казахстан, Карагандинская обл., г. Караганда, р-н им. Казыбек би, 108 уч. квартал, стр. 7</div>
        <div style="display:flex; flex-wrap:wrap; justify-content:center; gap:16px; margin-top:4px;">
            <a href="/privacy" style="color:#38bdf8; text-decoration:none;">Политика конфиденциальности</a>
            <span style="color:#475569;">&bull;</span>
            <a href="/terms" style="color:#38bdf8; text-decoration:none;">Условия использования</a>
            <span style="color:#475569;">&bull;</span>
            <a href="javascript:void(0)" onclick="krecOpenCookieModal()" style="color:#38bdf8; text-decoration:none;">Настройки файлов cookie</a>
            <span style="color:#475569;">&bull;</span>
            <a href="mailto:dpo@krec.kz" style="color:#94a3b8; text-decoration:none;">dpo@krec.kz</a>
        </div>
        <div style="color:#64748b; font-size:12px; margin-top:4px;">&copy; 2026 ТОО «КРЭК». Все права защищены. Сервис электронных квитанций.</div>
    </div>
</footer>

{cookie_banner}
{cookie_scripts}
</body></html>''')
