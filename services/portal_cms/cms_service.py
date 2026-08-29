# -*- coding: utf-8 -*-
import datetime
import json
import os
import re
import tempfile
import threading
from typing import Any, Dict, List, Optional, Tuple

import config
from logger import logger

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif', '.ico'}
ALLOWED_DOC_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar', '.7z', '.tar', '.gz', '.txt', '.rtf', '.csv'
}
FORBIDDEN_EXTENSIONS = {
    '.py', '.php', '.exe', '.bat', '.cmd', '.sh', '.js', '.html',
    '.htm', '.jsp', '.asp', '.aspx', '.cgi', '.pl', '.vbs', '.ps1'
}

# Основные страницы меню портала для удобного визуального выделения в админке
MAIN_NAV_SLUGS = {
    'home': {'name': 'Главная', 'url': '/', 'icon': 'home'},
    'reports': {'name': 'Отчеты', 'url': '/reports', 'icon': 'bar_chart'},
    'load': {'name': 'Загрузка ПС', 'url': '/load', 'icon': 'zap'},
    'tarif': {'name': 'Тарифы', 'url': '/tarif', 'icon': 'circle_dollar'},
    'zakup': {'name': 'Закупки', 'url': '/zakup', 'icon': 'shopping_bag'},
    'tu': {'name': 'Тех. условия', 'url': '/tu', 'icon': 'file_text'},
    'consumers': {'name': 'Потребителям', 'url': '/consumers', 'icon': 'users'},
    'contacts': {'name': 'Контакты', 'url': '/contacts', 'icon': 'phone'},
}


class PortalCMSService:
    """Сервис управления страницами портала, реестром документов и медиа-файлами."""

    def __init__(self):
        self._lock = threading.RLock()
        self.base_dir = config.BASE
        self.pages_json_path = os.path.join(self.base_dir, 'data', 'extracted_portal_pages.json')
        self.docs_json_path = os.path.join(self.base_dir, 'data', 'documents.json')
        self.upload_files_dir = os.path.join(config.STATIC_DIR, 'files')
        self.upload_images_dir = os.path.join(config.STATIC_DIR, 'images', 'uploads')

        # Гарантируем существование необходимых папок
        os.makedirs(os.path.join(self.base_dir, 'data'), exist_ok=True)
        os.makedirs(self.upload_files_dir, exist_ok=True)
        os.makedirs(self.upload_images_dir, exist_ok=True)

    # ────────────────────── Вспомогательные методы ──────────────────────

    def _sync_in_memory_portal_views(self):
        """Мгновенно обновляет переменные в templates.portal_views без перезапуска сервера."""
        try:
            import templates.portal_views as pv
            pv.PORTAL_PAGES = self._load_json(self.pages_json_path, default={})
            pv.DOCUMENTS_REGISTRY = self._load_json(self.docs_json_path, default={})
        except Exception as e:
            logger.warning(f"[PortalCMS] Ошибка синхронизации in-memory представлений: {e}")

    def _load_json(self, file_path: str, default: Any) -> Any:
        if not os.path.isfile(file_path):
            return default
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[PortalCMS] Ошибка чтения {file_path}: {e}")
            return default

    def _atomic_save_json(self, file_path: str, data: Any):
        """Атомарная запись JSON через временный файл с защитой от повреждений."""
        dir_name = os.path.dirname(file_path)
        os.makedirs(dir_name, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix='cms_save_', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def sanitize_slug(self, raw_slug: str) -> str:
        """Очищает и нормализует slug страницы (URL-идентификатор)."""
        slug = (raw_slug or '').strip().lower().lstrip('/').removesuffix('.php').removesuffix('.html')
        slug = re.sub(r'[^a-z0-9_\-]', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug or 'page'

    def sanitize_filename(self, raw_name: str) -> str:
        """Очищает имя файла от спецсимволов и path traversal."""
        base_name = os.path.basename(raw_name).strip()
        name, ext = os.path.splitext(base_name)
        ext = ext.lower()
        clean_name = re.sub(r'[^a-zA-Z0-9_\-\.\u0400-\u04FF]', '_', name)
        clean_name = re.sub(r'_+', '_', clean_name).strip('._')
        if not clean_name:
            clean_name = f"file_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return f"{clean_name}{ext}"

    # ────────────────────── Управление страницами портала ──────────────────────

    def get_all_pages(self) -> List[Dict[str, Any]]:
        """Возвращает структурированный список всех страниц портала."""
        with self._lock:
            data = self._load_json(self.pages_json_path, default={})
            pages_list = []
            for slug, page in data.items():
                is_main = slug in MAIN_NAV_SLUGS
                nav_info = MAIN_NAV_SLUGS.get(slug, {})
                title = page.get('title', slug)
                html_content = page.get('html', '')
                pages_list.append({
                    'slug': slug,
                    'title': title,
                    'is_main_nav': is_main,
                    'nav_name': nav_info.get('name', title),
                    'nav_url': f"/{slug}" if slug != 'home' else '/',
                    'icon': nav_info.get('icon', 'file_text'),
                    'content_length': len(html_content),
                    'snippet': re.sub(r'<[^>]+>', ' ', html_content[:200]).strip()
                })

            # Сортировка: сначала основные разделы меню в фиксированном порядке, затем остальные
            main_slug_order = ['home', 'reports', 'load', 'tarif', 'zakup', 'tu', 'consumers', 'contacts']
            def sort_key(item):
                slug = item['slug']
                if slug in main_slug_order:
                    return (0, main_slug_order.index(slug))
                return (1, slug)

            pages_list.sort(key=sort_key)
            return pages_list

    def get_page(self, slug: str) -> Optional[Dict[str, Any]]:
        """Получает данные конкретной страницы по её slug."""
        clean_slug = self.sanitize_slug(slug)
        with self._lock:
            data = self._load_json(self.pages_json_path, default={})
            if clean_slug in data:
                page = data[clean_slug]
                return {
                    'slug': clean_slug,
                    'title': page.get('title', ''),
                    'html': page.get('html', ''),
                    'is_main_nav': clean_slug in MAIN_NAV_SLUGS,
                    'url': f"/{clean_slug}" if clean_slug != 'home' else '/'
                }
            return None

    def save_page(self, slug: str, title: str, html_content: str) -> Tuple[bool, str]:
        """Создает или обновляет страницу портала."""
        clean_slug = self.sanitize_slug(slug)
        clean_title = (title or '').strip()
        if not clean_title:
            clean_title = clean_slug.capitalize()

        with self._lock:
            data = self._load_json(self.pages_json_path, default={})
            data[clean_slug] = {
                'title': clean_title,
                'html': html_content or ''
            }
            self._atomic_save_json(self.pages_json_path, data)
            self._sync_in_memory_portal_views()
            logger.info(f"[PortalCMS] Сохранена страница: slug='{clean_slug}', title='{clean_title}'")
            return True, clean_slug

    def delete_page(self, slug: str) -> Tuple[bool, str]:
        """Удаляет страницу портала (запрещено удалять 404 и home)."""
        clean_slug = self.sanitize_slug(slug)
        if clean_slug in ('home', '404'):
            return False, "Системные страницы 'home' и '404' не могут быть удалены."

        with self._lock:
            data = self._load_json(self.pages_json_path, default={})
            if clean_slug in data:
                del data[clean_slug]
                self._atomic_save_json(self.pages_json_path, data)
                self._sync_in_memory_portal_views()
                logger.info(f"[PortalCMS] Удалена страница: slug='{clean_slug}'")
                return True, "Страница успешно удалена."
            return False, "Страница не найдена."

    # ────────────────────── Реестр документов и отчетов ──────────────────────

    def get_all_documents(self, category: str = None, search: str = None) -> List[Dict[str, Any]]:
        """Возвращает список документов/отчетов из реестра."""
        with self._lock:
            data = self._load_json(self.docs_json_path, default={})
            docs_list = []
            for doc_key, doc in data.items():
                cat = doc.get('category', 'other')
                title = doc.get('title', doc_key)
                h1 = doc.get('h1', title)
                if category and cat != category:
                    continue
                if search:
                    q = search.lower()
                    if q not in doc_key.lower() and q not in title.lower() and q not in h1.lower():
                        continue
                docs_list.append({
                    'key': doc_key,
                    'category': cat,
                    'title': title,
                    'h1': h1,
                    'description': doc.get('description', ''),
                    'date_text': doc.get('date_text', ''),
                    'files': doc.get('files', []),
                    'iframes': doc.get('iframes', []),
                    'has_custom_html': doc.get('has_custom_html', False),
                    'url': f"/{doc_key}"
                })
            docs_list.sort(key=lambda x: x['key'], reverse=True)
            return docs_list

    def get_document(self, doc_key: str) -> Optional[Dict[str, Any]]:
        """Возвращает конкретный документ из реестра."""
        key = os.path.basename(doc_key).strip('/')
        if not key.endswith('.php'):
            key += '.php'
        with self._lock:
            data = self._load_json(self.docs_json_path, default={})
            if key in data:
                doc = data[key].copy()
                doc['key'] = key
                return doc
            return None

    def save_document(self, doc_key: str, doc_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Сохраняет или обновляет документ в реестре."""
        key = os.path.basename(doc_key).strip('/')
        if not key.endswith('.php'):
            key += '.php'

        with self._lock:
            data = self._load_json(self.docs_json_path, default={})
            data[key] = {
                'category': doc_data.get('category', 'other'),
                'title': doc_data.get('title', key),
                'h1': doc_data.get('h1', doc_data.get('title', key)),
                'description': doc_data.get('description', 'ТОО КРЭК'),
                'date_text': doc_data.get('date_text', ''),
                'files': doc_data.get('files', []),
                'iframes': doc_data.get('iframes', []),
                'has_custom_html': doc_data.get('has_custom_html', False)
            }
            self._atomic_save_json(self.docs_json_path, data)
            self._sync_in_memory_portal_views()
            logger.info(f"[PortalCMS] Сохранен документ в реестре: key='{key}'")
            return True, key

    def delete_document(self, doc_key: str) -> Tuple[bool, str]:
        """Удаляет документ из реестра."""
        key = os.path.basename(doc_key).strip('/')
        if not key.endswith('.php'):
            key += '.php'
        with self._lock:
            data = self._load_json(self.docs_json_path, default={})
            if key in data:
                del data[key]
                self._atomic_save_json(self.docs_json_path, data)
                self._sync_in_memory_portal_views()
                logger.info(f"[PortalCMS] Удален документ из реестра: key='{key}'")
                return True, "Документ успешно удален."
            return False, "Документ не найден."

    # ────────────────────── Медиа и Файловый Менеджер ──────────────────────

    def list_media_files(self) -> List[Dict[str, Any]]:
        """Возвращает список всех загруженных файлов и изображений."""
        media_list = []

        # 1. Сканируем изображения (uploads)
        if os.path.isdir(self.upload_images_dir):
            for fname in os.listdir(self.upload_images_dir):
                full_path = os.path.join(self.upload_images_dir, fname)
                if os.path.isfile(full_path):
                    _, ext = os.path.splitext(fname)
                    if ext.lower() in ALLOWED_IMAGE_EXTENSIONS:
                        stat = os.stat(full_path)
                        media_list.append({
                            'filename': fname,
                            'type': 'image',
                            'ext': ext.lower().lstrip('.'),
                            'url': f"/images/uploads/{fname}",
                            'size_bytes': stat.st_size,
                            'size_formatted': self._format_size(stat.st_size),
                            'modified_ts': stat.st_mtime,
                            'modified_formatted': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%d.%m.%Y %H:%M')
                        })

        # 2. Сканируем файлы и документы (files)
        if os.path.isdir(self.upload_files_dir):
            for fname in os.listdir(self.upload_files_dir):
                full_path = os.path.join(self.upload_files_dir, fname)
                if os.path.isfile(full_path):
                    _, ext = os.path.splitext(fname)
                    ext_lower = ext.lower()
                    if ext_lower not in FORBIDDEN_EXTENSIONS:
                        stat = os.stat(full_path)
                        is_img = ext_lower in ALLOWED_IMAGE_EXTENSIONS
                        media_list.append({
                            'filename': fname,
                            'type': 'image' if is_img else 'doc',
                            'ext': ext_lower.lstrip('.'),
                            'url': f"/files/{fname}",
                            'size_bytes': stat.st_size,
                            'size_formatted': self._format_size(stat.st_size),
                            'modified_ts': stat.st_mtime,
                            'modified_formatted': datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%d.%m.%Y %H:%M')
                        })

        # Сортировка: самые свежие файлы вверху
        media_list.sort(key=lambda x: x['modified_ts'], reverse=True)
        return media_list

    def save_media_file(self, raw_filename: str, file_bytes: bytes, as_image: bool = False) -> Tuple[bool, Dict[str, Any], str]:
        """
        Сохраняет загруженный файл с валидацией расширения и защитой от перезаписи/инъекций.
        """
        if not file_bytes:
            return False, {}, "Файл пуст."

        clean_name = self.sanitize_filename(raw_filename)
        _, ext = os.path.splitext(clean_name)
        ext = ext.lower()

        if ext in FORBIDDEN_EXTENSIONS:
            return False, {}, f"Загрузка исполняемых файлов ({ext}) запрещена в целях безопасности."

        is_image = ext in ALLOWED_IMAGE_EXTENSIONS or as_image
        if not is_image and ext not in ALLOWED_DOC_EXTENSIONS:
            return False, {}, f"Неподдерживаемый тип файла: {ext}. Разрешены: PDF, DOC, DOCX, XLS, XLSX, ZIP, PNG, JPG, WEBP, SVG."

        target_dir = self.upload_images_dir if is_image else self.upload_files_dir
        os.makedirs(target_dir, exist_ok=True)

        target_path = os.path.join(target_dir, clean_name)

        # Если файл с таким именем уже есть, добавляем уникальный суффикс
        if os.path.exists(target_path):
            stem, f_ext = os.path.splitext(clean_name)
            suffix = datetime.datetime.now().strftime('%H%M%S')
            clean_name = f"{stem}_{suffix}{f_ext}"
            target_path = os.path.join(target_dir, clean_name)

        try:
            with open(target_path, 'wb') as f:
                f.write(file_bytes)

            stat = os.stat(target_path)
            rel_url = f"/images/uploads/{clean_name}" if is_image else f"/files/{clean_name}"
            logger.info(f"[PortalCMS] Загружен медиа-файл: '{clean_name}', размер {stat.st_size} байт, url='{rel_url}'")

            return True, {
                'filename': clean_name,
                'url': rel_url,
                'type': 'image' if is_image else 'doc',
                'size_formatted': self._format_size(stat.st_size)
            }, "Файл успешно загружен."
        except Exception as e:
            logger.error(f"[PortalCMS] Ошибка сохранения медиа-файла: {e}")
            return False, {}, f"Сбой сохранения файла: {e}"

    def delete_media_file(self, filename: str) -> Tuple[bool, str]:
        """Удаляет файл из каталога медиа."""
        clean_name = os.path.basename(filename).strip()
        deleted = False

        # Проверяем в upload_images_dir
        p1 = os.path.join(self.upload_images_dir, clean_name)
        if os.path.isfile(p1):
            os.remove(p1)
            deleted = True

        # Проверяем в upload_files_dir
        p2 = os.path.join(self.upload_files_dir, clean_name)
        if os.path.isfile(p2):
            os.remove(p2)
            deleted = True

        if deleted:
            logger.info(f"[PortalCMS] Удален медиа-файл: '{clean_name}'")
            return True, "Файл успешно удален."
        return False, "Файл не найден."

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} Б"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} КБ"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} МБ"


portal_cms = PortalCMSService()
