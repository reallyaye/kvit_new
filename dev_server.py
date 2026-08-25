import http.server
import http.client
import os
import re
import json
import socketserver
import urllib.parse

PORT = 8080
KVIT_BACKEND_HOST = "127.0.0.1"
KVIT_BACKEND_PORT = 8000
DOC_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www", "krec")
DOCS_REGISTRY_PATH = os.path.join(DOC_ROOT, "data", "documents.json")

KVIT_ROUTES = {
    '/upload', '/reconcile', '/login', '/logout', 
    '/receipt', '/download', '/search', '/ws'
}

BLOCKED_PREFIXES = ('_archive', 'data', 'includes', '.git', '.env')
BLOCKED_EXTENSIONS = ('.sql', '.sqlite', '.sqlite3', '.env', '.bak', '.log', '.conf', '.ini', '.sh', '.py')

def load_documents_registry():
    if os.path.exists(DOCS_REGISTRY_PATH):
        try:
            with open(DOCS_REGISTRY_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Error loading documents registry: {e}")
    return {}

DOCUMENTS_REGISTRY = load_documents_registry()

class KrecHandler(http.server.SimpleHTTPRequestHandler):
    def send_security_headers(self):
        """Внедрение заголовков безопасности."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-XSS-Protection", "1; mode=block")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

    def is_path_safe(self, file_path):
        """Проверка на Path Traversal: путь обязан лежать внутри DOC_ROOT."""
        try:
            abs_path = os.path.abspath(file_path)
            abs_root = os.path.abspath(DOC_ROOT)
            return os.path.commonpath([abs_path, abs_root]) == abs_root
        except Exception:
            return False

    def translate_path(self, path):
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        rel_path = clean_path.lstrip('/')
        return os.path.join(DOC_ROOT, rel_path)

    def is_kvit_path(self, path):
        p = path.split('?', 1)[0]
        if p.startswith('/kvit') or p.startswith('/api/') or p.startswith('/ws'):
            return True
        if p in KVIT_ROUTES:
            return True
        return False

    def is_blocked_path(self, route):
        """Проверка на запрещенные служебные директории и расширения."""
        r_lower = route.lower()
        if any(r_lower.startswith(p) for p in BLOCKED_PREFIXES):
            return True
        if any(r_lower.endswith(ext) for ext in BLOCKED_EXTENSIONS):
            return True
        return False

    def do_GET(self):
        if self.is_kvit_path(self.path):
            self.proxy_request()
            return

        clean_path = self.path.split('?', 1)[0].split('#', 1)[0]
        route = clean_path.strip('/')

        # Блокировка скрытых файлов и служебных папок
        if self.is_blocked_path(route):
            self.send_404()
            return

        # 1. Главная страница
        if route in ('', 'index.php', 'index.html'):
            home_path = os.path.join(DOC_ROOT, 'pages', 'home.php')
            if os.path.isfile(home_path) and self.is_path_safe(home_path):
                self.render_php_file(home_path)
                return

        # 2. Прямые статические файлы (css, js, images, files, pdf, ico, txt, xml)
        file_path = self.translate_path(self.path)
        if not self.is_path_safe(file_path):
            self.send_404()
            return

        if os.path.isfile(file_path) and not file_path.endswith('.php'):
            self.send_static_file(file_path)
            return

        # 3. Страница из каталога pages/
        page_name = route
        if not page_name.endswith('.php'):
            page_name += '.php'
        
        page_path = os.path.join(DOC_ROOT, 'pages', page_name)
        if os.path.isfile(page_path) and self.is_path_safe(page_path):
            self.render_php_file(page_path)
            return

        # 4. Проверка в реестре документов (обратная совместимость всех 240+ отчетов/схем)
        doc_key = os.path.basename(page_name)
        if doc_key in DOCUMENTS_REGISTRY:
            doc = DOCUMENTS_REGISTRY[doc_key]
            self.render_document(doc)
            return

        # 5. Если запрошен существующий php-файл в корне
        if os.path.isfile(file_path) and self.is_path_safe(file_path):
            self.render_php_file(file_path)
            return

        # 6. 404
        self.send_404()

    def send_404(self):
        page_404 = os.path.join(DOC_ROOT, 'pages', '404.php')
        if os.path.isfile(page_404):
            self.render_php_file(page_404, status_code=404)
        else:
            self.send_response(404)
            self.send_security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h1>404 Страница не найдена</h1>".encode('utf-8'))

    def do_POST(self):
        if self.is_kvit_path(self.path):
            self.proxy_request()
        else:
            self.send_error(405, "Method Not Allowed")

    def send_static_file(self, file_path):
        """Отдача статического файла с заголовками безопасности."""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()

            content_type = self.guess_type(file_path)
            self.send_response(200)
            self.send_security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, f"Ошибка чтения файла: {str(e)}")

    def resolve_include(self, inc_name, base_dir):
        inc_clean = inc_name.strip("'\" ")
        candidates = [
            os.path.join(base_dir, inc_clean),
            os.path.join(DOC_ROOT, inc_clean),
            os.path.join(DOC_ROOT, 'includes', inc_clean),
            os.path.join(DOC_ROOT, 'includes', os.path.basename(inc_clean))
        ]
        for c in candidates:
            if os.path.isfile(c) and self.is_path_safe(c):
                with open(c, 'r', encoding='utf-8', errors='ignore') as inc_f:
                    return inc_f.read()
        return f"<!-- Include {inc_clean} not found -->"

    def render_php_file(self, file_path, status_code=200):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            base_dir = os.path.dirname(file_path)

            def replace_include(match):
                return self.resolve_include(match.group(1), base_dir)

            pattern = re.compile(r'<\?php\s+(?:include|require|include_once|require_once)\s*\(?\s*[\'"]([^\'"]+)[\'"]\s*\)?\s*;\s*\?>', re.IGNORECASE)
            rendered = pattern.sub(replace_include, content)
            rendered = re.sub(r'<\?php.*?\?>', '', rendered, flags=re.DOTALL)

            data = rendered.encode('utf-8')
            self.send_response(status_code)
            self.send_security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, f"Ошибка обработки: {str(e)}")

    def render_document(self, doc):
        try:
            header_content = self.resolve_include('header.html', DOC_ROOT)
            footer_content = self.resolve_include('footer.html', DOC_ROOT)

            title = doc.get('title', 'ТОО КРЭК — Документ')
            h1 = doc.get('h1', title)
            desc = doc.get('description', '')
            date_text = doc.get('date_text', '')
            files = doc.get('files', [])
            iframes = doc.get('iframes', [])

            body_html = []
            body_html.append(f'<h1>{h1}</h1>')
            if date_text:
                body_html.append(f'<p style="font-weight:600; color:#475569; margin:10px 0 20px;">{date_text}</p>')
            body_html.append('<div class="line"></div>')

            if iframes:
                body_html.append('<div class="iframes-container" style="display:flex; flex-direction:column; gap:30px; margin:20px 0;">')
                for ifr in iframes:
                    fname = os.path.basename(ifr)
                    clean_src = '/files/' + urllib.parse.quote(fname)
                    body_html.append(f'''
                    <div class="iframe-box" style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px;">
                        <div style="margin-bottom:8px; font-weight:500; color:#1e293b; display:flex; justify-content:space-between; align-items:center;">
                            <span>{fname}</span>
                            <a href="{clean_src}" target="_blank" style="font-size:13px; color:#2563eb; text-decoration:underline;">Открыть в новой вкладке ↗</a>
                        </div>
                        <iframe src="{clean_src}" width="100%" height="800" style="border:none; border-radius:4px; background:#fff;"></iframe>
                    </div>''')
                body_html.append('</div>')
            elif files:
                body_html.append('<div class="doc-actions" style="margin:20px 0; display:flex; flex-wrap:wrap; gap:12px;">')
                for f in files:
                    fname = os.path.basename(f)
                    file_url = '/files/' + urllib.parse.quote(fname)
                    body_html.append(f'''
                    <div class="buttom">
                        <a href="{file_url}" target="_blank" rel="noopener noreferrer">Посмотреть документ ({fname})</a>
                    </div>''')
                body_html.append('</div>')
            else:
                body_html.append('<p>Документ временно недоступен.</p>')

            full_html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="description" content="{desc}"/>
<title>{title}</title>
{header_content}
{''.join(body_html)}
{footer_content}'''

            data = full_html.encode('utf-8')
            self.send_response(200)
            self.send_security_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, "Internal Server Error")

    def proxy_request(self):
        target_path = self.path
        if target_path.startswith('/kvit/'):
            target_path = '/' + target_path[6:]
        elif target_path == '/kvit':
            target_path = '/'

        body = None
        if 'Content-Length' in self.headers:
            body = self.rfile.read(int(self.headers['Content-Length']))

        headers = {}
        for k, v in self.headers.items():
            if k.lower() != 'host':
                headers[k] = v
        headers['Host'] = f"{KVIT_BACKEND_HOST}:{KVIT_BACKEND_PORT}"
        headers['X-Forwarded-For'] = self.client_address[0]
        headers['X-Forwarded-Proto'] = 'http'

        try:
            conn = http.client.HTTPConnection(KVIT_BACKEND_HOST, KVIT_BACKEND_PORT, timeout=60)
            conn.request(self.command, target_path, body=body, headers=headers)
            resp = conn.getresponse()

            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in ('transfer-encoding',):
                    self.send_header(k, v)
            self.send_security_headers()
            self.end_headers()

            resp_body = resp.read()
            self.wfile.write(resp_body)
            conn.close()
        except Exception as e:
            self.send_error(502, "Bad Gateway")

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

def run():
    print("=" * 60)
    print(f"[*] Local KREC dev-server running on http://localhost:{PORT}/")
    print(f"[*] Loaded {len(DOCUMENTS_REGISTRY)} dynamic document routes from data/documents.json")
    print(f"[*] Security headers & path-traversal protection: ACTIVE")
    print(f"[*] Proxying kvit routes to {KVIT_BACKEND_HOST}:{KVIT_BACKEND_PORT}")
    print("=" * 60)
    server = ThreadedHTTPServer(("0.0.0.0", PORT), KrecHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()

if __name__ == '__main__':
    run()
