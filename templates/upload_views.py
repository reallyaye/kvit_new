# -*- coding: utf-8 -*-
from templates.admin_cms_views import _admin_nav_bar
from templates.icons import icon


def render_upload_form(message=None, csrf_token='', active_job_id='', role='admin', username='admin'):
    msg_html = message if message else ''
    csrf_input = f'<input type="hidden" name="csrf_token" value="{csrf_token}">' if csrf_token else ''

    return f'''
    {_admin_nav_bar('upload', role=role, username=username)}
    <div class="card">
        <h1>Загрузка квитанций и реестров</h1>
        <p class="subtitle">Загрузите пачку PDF-квитанций, обновите базу абонентов (Excel) или запустите импорт из локальной папки.</p>
        {msg_html}

        <div class="mode-tabs">
            <button type="button" class="mode-tab active" id="tabBrowserBtn" onclick="switchTab('browser')">{icon('upload', 15)} Квитанции (PDF)</button>
            <button type="button" class="mode-tab" id="tabAccountsBtn" onclick="switchTab('accounts')">{icon('file_text', 15)} Реестр абонентов (Excel / CSV)</button>
            <button type="button" class="mode-tab" id="tabLocalBtn" onclick="switchTab('local')">{icon('hard_drive', 15)} Импорт из папки</button>
        </div>

        <!-- Вкладка 1: Загрузка PDF-квитанций через браузер -->
        <div id="tabBrowser">
            <div class="upload-zone" id="dropzone">
                <div class="icon" style="color:#3b82f6;display:flex;justify-content:center;margin-bottom:12px">{icon('upload_cloud_large', 54, '#3b82f6')}</div>
                <div id="dropLabel"><b>Выберите PDF-файлы или папку с квитанциями</b> или перетащите сюда</div>
                <div style="margin-top:8px;font-size:13px;color:#94a3b8">Файлы принимаются мгновенно и обрабатываются в изолированном фоновом воркере</div>
                <input type="file" id="fileInput" accept=".pdf" multiple style="display:none">
                <input type="file" id="folderInput" webkitdirectory directory multiple style="display:none">
            </div>

            <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
                <button type="button" class="btn btn-outline" id="btnChooseFiles" style="flex:1;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px">{icon('files', 15)} Выбрать PDF-файлы</button>
                <button type="button" class="btn btn-outline" id="btnChooseFolder" style="flex:1;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px">{icon('folder', 15)} Выбрать папку</button>
            </div>

            <div id="progressArea" style="display:none;margin-top:20px">
                <div class="progress-wrap">
                    <div class="progress-fill" id="progressFill"></div>
                    <div class="progress-text" id="progressText">0%</div>
                </div>
                <div id="statusLabel" style="font-size:14px;color:#475569;font-weight:600;margin-top:6px">Фоновая обработка...</div>
                <div class="log-box" id="logBox"></div>
            </div>

            <div id="resultArea" style="margin-top:20px"></div>

            <button type="button" class="btn btn-green" id="btnStartUpload" style="margin-top:16px;width:100%;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px" disabled>
                {icon('upload', 16)} Загрузить в фоновую очередь
            </button>
        </div>

        <!-- Вкладка 2: Загрузка реестра абонентов (Excel / CSV) -->
        <div id="tabAccounts" style="display:none">
            <div class="upload-zone" id="accountsDropzone">
                <div class="icon" style="color:#16a34a;display:flex;justify-content:center;margin-bottom:12px">{icon('file_text', 54, '#16a34a')}</div>
                <div id="accountsDropLabel"><b>Выберите файл реестра абонентов (.xlsx, .xls, .csv)</b> или перетащите сюда</div>
                <div style="margin-top:8px;font-size:13px;color:#94a3b8">Автоматический импорт лицевых счетов, ФИО, адресов, улиц, домов и организаций</div>
                <input type="file" id="accountsFileInput" accept=".xlsx,.xls,.csv,.tsv,.txt" style="display:none">
            </div>

            <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
                <button type="button" class="btn btn-outline" id="btnChooseAccountsFile" style="flex:1;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px">{icon('file_text', 15)} Выбрать файл реестра</button>
            </div>

            <div style="margin-top:18px">
                <label style="font-weight:600;font-size:14px;color:#334155;margin-bottom:6px;display:block">Режим обновления базы счетов:</label>
                <select id="accountsModeSelect" style="width:100%;padding:10px 14px;border:1.5px solid #cbd5e1;border-radius:10px;font-size:14px">
                    <option value="upsert" selected>Обновить существующие и добавить новые счета (Рекомендуется)</option>
                    <option value="insert_only">Только добавить отсутствующие (не менять существующие адреса)</option>
                    <option value="replace">Полная замена базы (очистить и загрузить заново)</option>
                </select>
            </div>

            <div id="accountsProgressArea" style="display:none;margin-top:20px">
                <div class="progress-wrap">
                    <div class="progress-fill" id="accountsProgressFill" style="width:100%"></div>
                    <div class="progress-text" id="accountsProgressText">Обработка реестра на сервере...</div>
                </div>
                <div id="accountsStatusLabel" style="font-size:14px;color:#475569;font-weight:600;margin-top:6px">Импорт записей в базу данных...</div>
            </div>

            <div id="accountsResultArea" style="margin-top:20px"></div>

            <button type="button" class="btn btn-green" id="btnStartAccountsUpload" style="margin-top:16px;width:100%;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px" disabled>
                {icon('upload', 16)} Запустить импорт реестра
            </button>
        </div>

        <!-- Вкладка 3: Импорт напрямую из локальной папки на сервере -->
        <div id="tabLocal" style="display:none">
            <form action="/import-folder" method="post">
                {csrf_input}
                <label>Полный путь к папке с PDF на сервере</label>
                <input type="text" name="folder_path" placeholder="Например, /mnt/storage/receipts или C:\\\\квитанции" required>
                <p style="font-size:13px;color:#64748b;margin:6px 0 16px">Сервер мгновенно просканирует файлы и передаст задачу в фоновый воркер без блокировки API.</p>
                <button class="btn btn-green" style="width:100%;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px">{icon('hard_drive', 16)} Запустить фоновый импорт</button>
            </form>
        </div>
    </div>

    <script>
    function switchTab(mode) {{
        const tabB = document.getElementById('tabBrowser');
        const tabA = document.getElementById('tabAccounts');
        const tabL = document.getElementById('tabLocal');
        const btnB = document.getElementById('tabBrowserBtn');
        const btnA = document.getElementById('tabAccountsBtn');
        const btnL = document.getElementById('tabLocalBtn');

        tabB.style.display = (mode === 'browser') ? 'block' : 'none';
        tabA.style.display = (mode === 'accounts') ? 'block' : 'none';
        tabL.style.display = (mode === 'local') ? 'block' : 'none';

        btnB.classList.toggle('active', mode === 'browser');
        btnA.classList.toggle('active', mode === 'accounts');
        btnL.classList.toggle('active', mode === 'local');
    }}

    // ────────────────────── 1. Загрузка PDF квитанций ──────────────────────
    const dz = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const folderInput = document.getElementById('folderInput');
    const btnChooseFiles = document.getElementById('btnChooseFiles');
    const btnChooseFolder = document.getElementById('btnChooseFolder');
    const btnStartUpload = document.getElementById('btnStartUpload');
    const dropLabel = document.getElementById('dropLabel');
    const progressArea = document.getElementById('progressArea');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const statusLabel = document.getElementById('statusLabel');
    const logBox = document.getElementById('logBox');
    const resultArea = document.getElementById('resultArea');

    let selectedPdfFiles = [];
    let currentTaskData = null;

    function updateSelectedFiles(files) {{
        const filtered = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
        selectedPdfFiles = filtered;
        resultArea.innerHTML = '';
        progressArea.style.display = 'none';

        if (selectedPdfFiles.length === 0) {{
            dropLabel.innerHTML = '<b>Выберите PDF-файлы или папку</b> или перетащите сюда';
            btnStartUpload.disabled = true;
        }} else {{
            dropLabel.innerHTML = '<b>Выбрано PDF-файлов: ' + selectedPdfFiles.length + '</b>';
            btnStartUpload.disabled = false;
            btnStartUpload.innerHTML = `{icon('upload', 16)} Загрузить в фоновую очередь (` + selectedPdfFiles.length + ' файлов)';
        }}
    }}

    btnChooseFiles.addEventListener('click', () => fileInput.click());
    btnChooseFolder.addEventListener('click', () => folderInput.click());

    fileInput.addEventListener('change', () => updateSelectedFiles(fileInput.files));
    folderInput.addEventListener('change', () => updateSelectedFiles(folderInput.files));

    dz.addEventListener('dragover', e => {{ e.preventDefault(); dz.classList.add('drag'); }});
    dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
    dz.addEventListener('drop', e => {{
        e.preventDefault();
        dz.classList.remove('drag');
        const items = e.dataTransfer.items;
        if (items) {{
            const promises = [];
            const collected = [];
            for (let i = 0; i < items.length; i++) {{
                const entry = items[i].webkitGetAsEntry && items[i].webkitGetAsEntry();
                if (entry) {{
                    promises.push(scanEntry(entry, collected));
                }} else if (items[i].kind === 'file') {{
                    const f = items[i].getAsFile();
                    if (f && f.name.toLowerCase().endsWith('.pdf')) collected.push(f);
                }}
            }}
            Promise.all(promises).then(() => updateSelectedFiles(collected));
        }} else {{
            updateSelectedFiles(e.dataTransfer.files);
        }}
    }});

    function scanEntry(entry, collected) {{
        return new Promise(resolve => {{
            if (entry.isFile) {{
                entry.file(f => {{
                    if (f.name.toLowerCase().endsWith('.pdf')) collected.push(f);
                    resolve();
                }}, () => resolve());
            }} else if (entry.isDirectory) {{
                const reader = entry.createReader();
                const readEntries = () => {{
                    reader.readEntries(entries => {{
                        if (entries.length === 0) {{
                            resolve();
                        }} else {{
                            Promise.all(entries.map(e => scanEntry(e, collected))).then(readEntries);
                        }}
                    }}, () => resolve());
                }};
                readEntries();
            }} else {{
                resolve();
            }}
        }});
    }}

    function log(text) {{
        logBox.textContent += text + '\\n';
        logBox.scrollTop = logBox.scrollHeight;
    }}

    // Функция экспорта отчета в Excel (CSV с UTF-8 BOM)
    window.exportJobReportToCsv = function() {{
        if (!currentTaskData) return;
        const t = currentTaskData;
        const rows = [
            ['Отчет по фоновой обработке квитанций', ''],
            ['ID задачи', t.job_id || '—'],
            ['Всего файлов', t.total_files || 0],
            ['Привязано к счетам', t.added || 0],
            ['Счетов нет в базе (сироты)', t.orphan || 0],
            ['Дубликатов пропущено', t.duplicates || 0],
            ['Не распознано / ошибок', t.skipped || 0],
            ['Скорость обработки (файл/сек)', t.speed_files_per_sec || 0],
            ['', ''],
            ['№', 'Детализация обработки страницы / файла']
        ];

        if (t.details && t.details.length > 0) {{
            t.details.forEach((d, idx) => {{
                rows.push([idx + 1, d]);
            }});
        }}

        const csvContent = '\\uFEFF' + rows.map(r => r.map(cell => '"' + String(cell).replace(/"/g, '""') + '"').join(';')).join('\\r\\n');
        const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'Отчет_обработки_квитанций_' + (t.job_id ? t.job_id.substring(0, 8) : 'export') + '.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }};

    async function trackJob(jobId) {{
        progressArea.style.display = 'block';
        btnStartUpload.disabled = true;
        btnChooseFiles.disabled = true;
        btnChooseFolder.disabled = true;
        log('Отслеживание задачи ' + jobId + '...');

        const pollInterval = 600;
        const maxPolls = 1000;
        let polls = 0;
        let lastDetailCount = 0;

        while (polls < maxPolls) {{
            polls++;
            try {{
                const res = await fetch('/api/tasks/' + jobId);
                if (res.ok) {{
                    const t = await res.json();
                    currentTaskData = t;
                    const pct = t.progress_pct || 0;
                    progressFill.style.width = pct + '%';

                    const speedText = t.speed_files_per_sec > 0 ? (' • ' + t.speed_files_per_sec + ' файл/сек') : '';
                    const etaText = (t.eta_seconds !== null && t.eta_seconds > 0) ? (' • осталось ~' + t.eta_seconds + ' сек') : '';
                    const retryText = t.retry_count > 0 ? (' • Повтор ' + t.retry_count + '/' + t.max_retries) : '';

                    progressText.textContent = pct + '% (' + (t.processed_files || 0) + '/' + (t.total_files || 0) + speedText + etaText + retryText + ')';

                    if (t.current_file) {{
                        statusLabel.textContent = 'Обработка: ' + t.current_file + speedText + etaText;
                    }}

                    if (t.details && t.details.length > lastDetailCount) {{
                        for (let i = lastDetailCount; i < t.details.length; i++) {{
                            log(t.details[i]);
                        }}
                        lastDetailCount = t.details.length;
                    }}

                    if (t.status === 'COMPLETED') {{
                        statusLabel.innerHTML = '<span style="color:#16a34a;display:inline-flex;align-items:center;gap:6px">{icon("check_circle", 16, "#16a34a")} Фоновая обработка успешно завершена! (' + (t.speed_files_per_sec || 0) + ' файл/сек)</span>';
                        btnStartUpload.disabled = false;
                        btnChooseFiles.disabled = false;
                        btnChooseFolder.disabled = false;

                        const cls = (t.orphan === 0 && t.skipped === 0 && t.duplicates === 0) ? 'ok' : 'warn';
                        const detailHtml = (t.details || []).map(d => htmlEscape(d)).join('<br>');
                        resultArea.innerHTML = `<div class="${{cls}}">
                            <b>Фоновая обработка завершена: ${{t.total_files}} файлов</b><br><br>
                            Привязано к счетам: <b>${{t.added}}</b><br>
                            Счёта нет в базе (сироты): <b>${{t.orphan}}</b><br>
                            Не удалось распознать: <b>${{t.skipped}}</b><br>
                            Дубликатов пропущено: <b>${{t.duplicates}}</b><br>
                            Скорость обработки: <b>${{t.speed_files_per_sec || 0}} файлов/сек</b><br><br>
                            <div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap">
                                <button type="button" class="btn btn-sm" onclick="exportJobReportToCsv()" style="display:inline-flex;align-items:center;gap:6px">{icon('download', 14)} 📥 Скачать отчёт в Excel (CSV)</button>
                            </div>
                            <details><summary>Подробности по файлам (${{t.details ? t.details.length : 0}})</summary><br>${{detailHtml}}</details>
                        </div>`;
                        break;
                    }} else if (t.status === 'FAILED') {{
                        statusLabel.innerHTML = '<span style="color:#dc2626;display:inline-flex;align-items:center;gap:6px">❌ Сбой фоновой обработки</span>';
                        btnStartUpload.disabled = false;
                        btnChooseFiles.disabled = false;
                        btnChooseFolder.disabled = false;
                        resultArea.innerHTML = `<div class="err"><b>Ошибка фоновой обработки:</b> ${{htmlEscape(t.error_message || 'Неизвестная ошибка')}}</div>`;
                        break;
                    }}
                }}
            }} catch (e) {{
                console.error('Polling error:', e);
            }}
            await new Promise(r => setTimeout(r, pollInterval));
        }}
    }}

    btnStartUpload.addEventListener('click', async () => {{
        if (selectedPdfFiles.length === 0) return;

        btnStartUpload.disabled = true;
        btnChooseFiles.disabled = true;
        btnChooseFolder.disabled = true;
        progressArea.style.display = 'block';
        logBox.textContent = '';
        resultArea.innerHTML = '';

        const formData = new FormData();
        selectedPdfFiles.forEach(f => formData.append('pdf', f, f.name));

        statusLabel.textContent = 'Отправка файлов на сервер...';
        log('Отправка ' + selectedPdfFiles.length + ' файлов в фоновую очередь...');

        try {{
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            const csrfVal = csrfMeta ? csrfMeta.content : '';
            const headers = csrfVal ? {{ 'X-CSRF-Token': csrfVal }} : {{}};

            const res = await fetch('/api/upload-batch', {{
                method: 'POST',
                headers: headers,
                body: formData
            }});

            if (!res.ok) {{
                const errData = await res.json().catch(() => ({{}}));
                log('[Ошибка] ' + (errData.error || res.statusText));
                statusLabel.innerHTML = '<span style="color:#dc2626">❌ Ошибка загрузки файлов</span>';
                btnStartUpload.disabled = false;
                btnChooseFiles.disabled = false;
                btnChooseFolder.disabled = false;
            }} else {{
                const data = await res.json();
                if (data.job_id) {{
                    log('Файлы успешно приняты сервером. Задача ID: ' + data.job_id);
                    trackJob(data.job_id);
                }} else {{
                    log('Загрузка завершена');
                }}
            }}
        }} catch (err) {{
            log('[Ошибка соединения] ' + err.message);
            btnStartUpload.disabled = false;
            btnChooseFiles.disabled = false;
            btnChooseFolder.disabled = false;
        }}
    }});

    // ────────────────────── 2. Загрузка реестра абонентов (Excel/CSV) ──────────────────────
    const accountsDz = document.getElementById('accountsDropzone');
    const accountsFileInput = document.getElementById('accountsFileInput');
    const btnChooseAccountsFile = document.getElementById('btnChooseAccountsFile');
    const btnStartAccountsUpload = document.getElementById('btnStartAccountsUpload');
    const accountsDropLabel = document.getElementById('accountsDropLabel');
    const accountsModeSelect = document.getElementById('accountsModeSelect');
    const accountsProgressArea = document.getElementById('accountsProgressArea');
    const accountsResultArea = document.getElementById('accountsResultArea');
    const accountsStatusLabel = document.getElementById('accountsStatusLabel');

    let selectedAccountsFile = null;

    function updateSelectedAccountsFile(file) {{
        selectedAccountsFile = file;
        accountsResultArea.innerHTML = '';
        accountsProgressArea.style.display = 'none';

        if (!file) {{
            accountsDropLabel.innerHTML = '<b>Выберите файл реестра абонентов (.xlsx, .xls, .csv)</b> или перетащите сюда';
            btnStartAccountsUpload.disabled = true;
        }} else {{
            accountsDropLabel.innerHTML = '<b>Выбран файл: ' + htmlEscape(file.name) + ' (' + (Math.round(file.size / 1024)) + ' KB)</b>';
            btnStartAccountsUpload.disabled = false;
            btnStartAccountsUpload.innerHTML = `{icon('upload', 16)} Запустить импорт реестра (` + htmlEscape(file.name) + ')';
        }}
    }}

    btnChooseAccountsFile.addEventListener('click', () => accountsFileInput.click());
    accountsFileInput.addEventListener('change', () => {{
        if (accountsFileInput.files.length > 0) {{
            updateSelectedAccountsFile(accountsFileInput.files[0]);
        }}
    }});

    accountsDz.addEventListener('dragover', e => {{ e.preventDefault(); accountsDz.classList.add('drag'); }});
    accountsDz.addEventListener('dragleave', () => accountsDz.classList.remove('drag'));
    accountsDz.addEventListener('drop', e => {{
        e.preventDefault();
        accountsDz.classList.remove('drag');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {{
            updateSelectedAccountsFile(e.dataTransfer.files[0]);
        }}
    }});

    btnStartAccountsUpload.addEventListener('click', async () => {{
        if (!selectedAccountsFile) return;

        btnStartAccountsUpload.disabled = true;
        btnChooseAccountsFile.disabled = true;
        accountsProgressArea.style.display = 'block';
        accountsResultArea.innerHTML = '';
        accountsStatusLabel.textContent = 'Загрузка и обработка реестра на сервере...';

        const formData = new FormData();
        formData.append('file', selectedAccountsFile, selectedAccountsFile.name);
        formData.append('mode', accountsModeSelect.value);

        try {{
            const csrfMeta = document.querySelector('meta[name="csrf-token"]');
            const csrfVal = csrfMeta ? csrfMeta.content : '';
            const headers = csrfVal ? {{ 'X-CSRF-Token': csrfVal }} : {{}};

            const res = await fetch('/api/upload-accounts', {{
                method: 'POST',
                headers: headers,
                body: formData
            }});

            const data = await res.json();
            accountsProgressArea.style.display = 'none';
            btnStartAccountsUpload.disabled = false;
            btnChooseAccountsFile.disabled = false;

            if (res.ok && data.success) {{
                accountsResultArea.innerHTML = `<div class="ok">
                    <b>✅ Реестр абонентов успешно импортирован!</b><br><br>
                    Файл: <b>${{htmlEscape(data.file_name || 'реестр')}}</b><br>
                    Обработано / обновлено счетов: <b>${{data.imported ? data.imported.toLocaleString('ru-RU') : 0}}</b><br>
                    Всего лицевых счетов в базе: <b>${{data.total_in_db ? data.total_in_db.toLocaleString('ru-RU') : '—'}}</b><br>
                    Время выполнения: <b>${{data.elapsed_seconds || 0}} сек</b>
                </div>`;
            }} else {{
                accountsResultArea.innerHTML = `<div class="err">
                    <b>❌ Ошибка импорта реестра:</b><br>${{htmlEscape(data.error || 'Неизвестная ошибка')}}
                </div>`;
            }}
        }} catch (err) {{
            accountsProgressArea.style.display = 'none';
            btnStartAccountsUpload.disabled = false;
            btnChooseAccountsFile.disabled = false;
            accountsResultArea.innerHTML = `<div class="err"><b>❌ Ошибка сети:</b> ${{htmlEscape(err.message)}}</div>`;
        }}
    }});

    const activeJob = '{active_job_id}';
    if (activeJob) {{
        trackJob(activeJob);
    }}

    function htmlEscape(str) {{
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }}
    </script>'''

