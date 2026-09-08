FROM nginx:1.25-alpine

# Устанавливаем logrotate, gzip и tzdata для ежедневной ротации журналов
RUN apk add --no-cache logrotate gzip tzdata

# Копируем конфигурацию logrotate и скрипт управления
COPY logrotate.d/nginx /etc/logrotate.d/nginx
RUN chmod 0644 /etc/logrotate.d/nginx

COPY rotate-logs.sh /usr/local/bin/rotate-logs.sh
RUN chmod 0755 /usr/local/bin/rotate-logs.sh
