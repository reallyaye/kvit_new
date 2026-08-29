# LESSONS LEARNED (DenseCode)
@role: senior_rules
@strict_mode: true

## 1. DOCKER_FILE_SYNC
- err: `can't open file '/app/X': No such file` -> missing in `Dockerfile COPY` or old image
- rule: new_script/file => update `Dockerfile` + `docker compose up -d --build`

## 2. COMPOSE_DOLLAR_EXPANSION
- err: `WARN The "..." variable is not set` -> raw `$` in `docker-compose.yml` parsed as env var
- rule: never unescaped `$` in compose strings; use `$$` or default fallback in `config.py`

## 3. COOKIE_SECURE_HTTP
- err: login loops / session dropped on `http://localhost:8080`
- cause: browser rejects `; Secure` cookie over unencrypted HTTP
- rule: `Secure` flag ONLY when `_is_request_https() == True`; `SameSite=Strict` + `HttpOnly`

## 4. SQL_DIALECT_COMPAT
- err: `syntax error at or near "OR"` on Postgres
- cause: `INSERT OR REPLACE` is SQLite-only
- rule: `INSERT INTO ... ON CONFLICT (...) DO UPDATE SET ...` or `DO NOTHING`

## 5. ASCII_FILENAMES
- err: Cyrillic / spaces in filenames cause encoding issues between OS
- rule: strictly ASCII alphanumeric + `_` for all files, assets and scripts

## 6. POSTGRES_CASE_SENSITIVITY
- err: `WHERE status = 'READY'` returns 0 rows when DB stores `'ready'`
- cause: Postgres string comparison is case-sensitive
- rule: `UPPER(status) = 'READY' OR status IS NULL` + store all DB statuses in UPPERCASE (`READY`, `MISSING`, etc.)

## 7. DEDUP_DISK_INTEGRITY
- err: `duplicate (already in db), skipped` while PDF file is missing on disk => deadlock
- cause: dedup checked only SQL row existence without verifying physical file on disk
- rule: check `is_file_on_disk` before dedup skip => if missing on disk, always re-stage & restore `READY`
