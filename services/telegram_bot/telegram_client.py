import json
import os
import ssl
import urllib.request
import urllib.parse
import urllib.error
import mimetypes
import secrets
from typing import Optional, Dict, Any, List, Union
from logger import logger

class TelegramAPIError(Exception):
    """Исключение при ошибке ответа Telegram Bot API."""
    def __init__(self, description: str, error_code: int = None):
        super().__init__(f"Telegram API Error ({error_code}): {description}")
        self.description = description
        self.error_code = error_code

class TelegramClient:
    """
    Легковесный клиент Telegram Bot API на базе стандартной библиотеки urllib.
    Не требует сторонних зависимостей, устойчив к сетевым сбоям и таймаутам.
    """

    def __init__(self, token: str, timeout: int = 35):
        self.token = (token or '').strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.file_base_url = f"https://api.telegram.org/file/bot{self.token}"
        self.timeout = timeout
        self.ssl_ctx = ssl.create_default_context()

    def _make_request(self, method: str, data: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None) -> Dict[str, Any]:
        if not self.token:
            raise TelegramAPIError("TELEGRAM_BOT_TOKEN не задан")

        url = f"{self.base_url}/{method}"
        req_timeout = timeout if timeout is not None else self.timeout

        headers = {'User-Agent': 'KvitApp-TelegramBot/1.0'}
        req_data = None

        if data is not None:
            json_bytes = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json; charset=utf-8'
            req_data = json_bytes

        req = urllib.request.Request(url, data=req_data, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=req_timeout, context=self.ssl_ctx) as resp:
                resp_bytes = resp.read()
                result = json.loads(resp_bytes.decode('utf-8'))
                if not result.get('ok'):
                    raise TelegramAPIError(result.get('description', 'Unknown error'), result.get('error_code'))
                return result.get('result')
        except urllib.error.HTTPError as e:
            try:
                err_payload = json.loads(e.read().decode('utf-8'))
                desc = err_payload.get('description', str(e))
                code = err_payload.get('error_code', e.code)
            except Exception:
                desc = str(e)
                code = e.code
            raise TelegramAPIError(desc, code)
        except urllib.error.URLError as e:
            raise TelegramAPIError(f"Сетевая ошибка: {e.reason}")
        except TimeoutError:
            raise TelegramAPIError("Превышен таймаут сетевого запроса")

    def get_me(self) -> Dict[str, Any]:
        """Возвращает информацию о боте."""
        return self._make_request('getMe')

    def get_updates(self, offset: int = 0, timeout: int = 30, limit: int = 50) -> List[Dict[str, Any]]:
        """Получает новые обновления через long polling."""
        payload = {
            'offset': offset,
            'timeout': timeout,
            'limit': limit,
            'allowed_updates': ['message', 'callback_query']
        }
        # Таймаут urllib сокета делаем чуть больше long-polling таймаута Telegram
        return self._make_request('getUpdates', payload, timeout=timeout + 10)

    def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        parse_mode: str = 'HTML',
        reply_markup: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Отправляет текстовое сообщение в чат."""
        payload: Dict[str, Any] = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup
        if reply_to_message_id:
            payload['reply_to_message_id'] = reply_to_message_id

        return self._make_request('sendMessage', payload)

    def get_file(self, file_id: str) -> Dict[str, Any]:
        """Получает метаданные файла и путь для скачивания."""
        return self._make_request('getFile', {'file_id': file_id})

    def download_file(self, file_path: str, dest_path: str) -> bool:
        """Скачивает файл с серверов Telegram и сохраняет на диск."""
        if not file_path:
            return False

        url = f"{self.file_base_url}/{file_path}"
        req = urllib.request.Request(url, headers={'User-Agent': 'KvitApp-TelegramBot/1.0'})

        try:
            with urllib.request.urlopen(req, timeout=60, context=self.ssl_ctx) as resp:
                with open(dest_path, 'wb') as f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"[Telegram] Ошибка скачивания файла {file_path}: {e}")
            return False

    def send_document(
        self,
        chat_id: Union[int, str],
        file_path: str,
        caption: str = '',
        parse_mode: str = 'HTML',
        visible_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Отправляет файл (например, PDF квитанцию) как документ через multipart/form-data."""
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        boundary = f"----WebKitFormBoundary{secrets.token_hex(16)}"
        delimiter = f"--{boundary}\r\n".encode('utf-8')
        end_delimiter = f"--{boundary}--\r\n".encode('utf-8')

        filename = visible_filename or os.path.basename(file_path)
        mime_type = mimetypes.guess_type(filename)[0] or 'application/pdf'

        body_parts = []

        # Поле chat_id
        body_parts.append(delimiter)
        body_parts.append(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n')
        body_parts.append(str(chat_id).encode('utf-8'))
        body_parts.append(b'\r\n')

        # Поле caption
        if caption:
            body_parts.append(delimiter)
            body_parts.append(b'Content-Disposition: form-data; name="caption"\r\n\r\n')
            body_parts.append(caption.encode('utf-8'))
            body_parts.append(b'\r\n')

            body_parts.append(delimiter)
            body_parts.append(b'Content-Disposition: form-data; name="parse_mode"\r\n\r\n')
            body_parts.append(parse_mode.encode('utf-8'))
            body_parts.append(b'\r\n')

        # Поле document (файл)
        body_parts.append(delimiter)
        header_file = f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\nContent-Type: {mime_type}\r\n\r\n'
        body_parts.append(header_file.encode('utf-8'))

        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        body_parts.append(file_bytes)
        body_parts.append(b'\r\n')
        body_parts.append(end_delimiter)

        full_body = b''.join(body_parts)

        url = f"{self.base_url}/sendDocument"
        headers = {
            'User-Agent': 'KvitApp-TelegramBot/1.0',
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(len(full_body))
        }

        req = urllib.request.Request(url, data=full_body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_ctx) as resp:
                resp_bytes = resp.read()
                result = json.loads(resp_bytes.decode('utf-8'))
                if not result.get('ok'):
                    raise TelegramAPIError(result.get('description', 'Unknown error'), result.get('error_code'))
                return result.get('result')
        except Exception as e:
            logger.error(f"[Telegram] Ошибка отправки документа в {chat_id}: {e}")
            raise

    def set_my_commands(self, commands: List[Dict[str, str]]) -> bool:
        """Устанавливает список команд в меню Telegram."""
        try:
            self._make_request('setMyCommands', {'commands': commands})
            return True
        except Exception as e:
            logger.warning(f"[Telegram] Не удалось установить команды меню: {e}")
            return False
