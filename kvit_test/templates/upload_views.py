# -*- coding: utf-8 -*-
from templates.icons import icon


def render_upload_form(message=None, csrf_token='', active_job_id=''):
    msg_html = message if message else ''
    csrf_input = f'<input type="hidden" name="csrf_token" value="{csrf_token}">' if csrf_token else ''

    return f'''<div class="card">
        <h1>Загрузка квитанций</h1>
        <p class="subtitle">Загрузите отдельные PDF-файлы, целую папку с квитанциями или укажите путь к папке на компьютере.</p>
        {msg_html}

        <div class="mode-tabs">
            <button type="button" class="mode-tab active" id="tabBrowserBtn" onclick="switchTab('browser')">{icon('upload', 15)} Загрузка через браузер</button>
            <button type="button" class="mode-tab" id="tabLocalBtn" onclick="switchTab('local')">{icon('hard_drive', 15)} Импорт из папки на диске</button>
        </div>

        <!-- Вкладка 1: Загрузка файлов/папки через браузер -->
        <div id="tabBrowser">
            <div class="upload-zone" id="dropzone">
                <div class="icon" style="color:#3b82f6;display:flex;justify-content:center;margin-bottom:12px">{icon('upload_cloud_large', 54, '#3b82f6')}</div>
                <div id="dropLabel"><b>Выберите PDF-файлы или папку</b> или перетащите сюда</div>
                <div style="margin-top:8px;font-size:13px;color:#94a3b8">Файлы принимаются мгновенно и обрабатываются в изолированном фоновом воркере</div>
                <input type="file" id="fileInput" accept=".pdf" multiple style="display:none">
                <input type="file" id="folderInput" webkitdirectory directory multiple style="display:none">
            </div>

            <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
                <button type="button" class="btn btn-outline" id="btnChooseFiles" style="flex:1;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px">{icon('files', 15)} Выбрать файлы</button>
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

        <!-- Вкладка 2: Импорт напрямую из локальной папки -->
        <div id="tabLocal" style="display:none">
            <form action="/import-folder" method="post">
                {csrf_input}
                <label>Полный путь к папке с PDF на компьютере</label>
                <input type="text" name="folder_path" placeholder="Например, C:\\\\Users\\\\zhunis\\\\Desktop\\\\квитанции" required>
                <p style="font-size:13px;color:#64748b;margin:6px 0 16px">Сервер мгновенно просканирует файлы и передаст задачу в фоновый воркер без блокировки API.</p>
                <button class="btn btn-green" style="width:100%;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px">{icon('hard_drive', 16)} Запустить фоновый импорт</button>
            </form>
        </div>
    </div>

    <script>
    function switchTab(mode) {{
        const tabB = document.getElementById('tabBrowser');
        const tabL = document.getElementById('tabLocal');
        const btnB = document.getElementById('tabBrowserBtn');
        const btnL = document.getElementById('tabLocalBtn');
        if (mode === 'browser') {{
            tabB.style.display = 'block';
            tabL.style.display = 'none';
            btnB.classList.add('active');
            btnL.classList.remove('active');
        }} else {{
            tabB.style.display = 'none';
            tabL.style.display = 'block';
            btnL.classList.add('active');
            btnB.classList.remove('active');
        }}
    }}

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
                            Счёта нет в базе: <b>${{t.orphan}}</b><br>
                            Не удалось распознать: <b>${{t.skipped}}</b><br>
                            Дубликатов пропущено: <b>${{t.duplicates}}</b><br>
                            Скорость обработки: <b>${{t.speed_files_per_sec || 0}} файлов/сек</b><br><br>
                            <details><summary>Подробности по файлам</summary><br>${{detailHtml}}</details>
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

    const activeJob = '{active_job_id}';
    if (activeJob) {{
        trackJob(activeJob);
    }}

    function htmlEscape(str) {{
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }}
    </script>'''

