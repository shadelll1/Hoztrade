# Перенос в бой

Сайт разворачивается на Linux-сервере в Docker: PostgreSQL, сайт (gunicorn) и Caddy, который сам получает
HTTPS-сертификат. 1С остаётся в офисе и, как и раньше, сама обращается к сайту — открывать её в интернет не нужно.

```
Покупатели ──HTTPS──▶ Caddy ──▶ сайт (gunicorn) ──▶ PostgreSQL
                       │  └─ /media/* фото с диска
1С в офисе ──HTTPS─────┘  (API обмена по токену)
```

## Что нужно

- Сервер (VPS) с Ubuntu 22.04/24.04 или Debian 12: 2 ядра, 2 ГБ памяти, 20 ГБ диска — с запасом для каталога в
  несколько тысяч товаров. Открытые порты 80 и 443.
- Домен, A-запись которого указывает на IP сервера. Кириллический домен в настройках — в punycode
  (`хозтрейд.рф` = `xn--d1abfjwnnv.xn--p1ai`).
- Почтовый ящик для отправки писем (SMTP), например в Яндекс 360 или Mail.ru для бизнеса.

## Установка

```bash
# Docker и git
curl -fsSL https://get.docker.com | sh
sudo apt-get install -y git

# Проект
git clone https://github.com/shadelll1/Hoztrade.git /opt/hoztrade
cd /opt/hoztrade/deploy
cp .env.example .env
nano .env            # домен, SECRET_KEY, EXCHANGE_TOKEN, POSTGRES_PASSWORD, почта
docker compose up -d --build
```

Первый запуск: миграции применяются сами при старте контейнера `web`, Caddy получает сертификат за минуту.
Затем — администратор и (по желанию) демо-контент:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py load_demo_content     # бренды, акции, советы — заменить своими
```

Каталог, цены, остатки и тарифы доставки на сайт присылает 1С — демо-каталог на боевом сайте не нужен.

## Подключить 1С

1. В 1С: «Сайт» → «Настройки обмена с сайтом» → адрес сайта `https://<домен>`.
2. «Задать токен обмена» — значение `EXCHANGE_TOKEN` из `deploy/.env`.
3. «Проверить связь», затем «Выгрузить каталог на сайт» — первая полная выгрузка с фото.
4. Дальше обмен идёт по расписанию каждые 5 минут. В клиент-серверной базе регламентное задание выполняет
   сервер 1С; в файловой — открытый клиент.

## Проверка

- `https://<домен>/healthz/` — `{"status": "ok", "db": true, "exchange": {"status": "ok", …}}`. Код 503 — не
  отвечает база. `exchange.status`: `stale` — 1С не выходила на связь дольше 30 минут (`EXCHANGE_STALE_MINUTES`),
  `never` — ни разу. Этот адрес удобно поставить в мониторинг (UptimeRobot, Яндекс Мониторинг и т. п.).
- Ошибки сайта приходят письмом на `ADMIN_EMAILS`, журнал — `docker compose exec web tail -f /app/logs/site.log`.
- Заказы — в админке `https://<домен>/admin/` и в 1С.

## Регулярные задачи (cron на сервере)

```cron
# Резервная копия базы и фото — каждую ночь, хранится 14 копий
30 3 * * *  cd /opt/hoztrade/deploy && docker compose exec -T web python manage.py backup --keep 14
# Обезличивание старых выполненных заказов и заявок (152-ФЗ), срок — 3 года
0 4 * * *   cd /opt/hoztrade/deploy && docker compose exec -T web python manage.py purge_personal_data --days 1095
```

Копии лежат в томе `backups` (`/app/backups` в контейнере): `db.dump` (PostgreSQL, формат pg_dump custom) и
`media.zip`. Хранить копии только на том же сервере нельзя — забирайте их на другой диск или в облако
(`docker compose cp web:/app/backups ./backups`, затем rsync/rclone).

### Восстановление

```bash
docker compose cp ./backups/20261010-033000 web:/tmp/restore
docker compose exec web sh -c 'pg_restore --clean --no-owner -d "$DATABASE_URL" /tmp/restore/db.dump'
docker compose exec web python -m zipfile -e /tmp/restore/media.zip /app/media
```

## Обновление

```bash
cd /opt/hoztrade && git pull
cd deploy && docker compose up -d --build     # миграции применятся при старте
```

## Без Docker (Windows, как в демо)

`site\run-prod.bat` — waitress на `127.0.0.1:8000`, база SQLite или PostgreSQL через `DATABASE_URL`. Перед ним
нужен обратный прокси с HTTPS (IIS, Caddy для Windows, nginx), в `site\.env`: `HTTPS=True`, `ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS`, `SITE_URL`, `SERVE_MEDIA=True` (если прокси не раздаёт `media/products`, `brands`, `posts`
сам; `media/leads` раздавать нельзя).

### Сайт в интернете с этого компьютера (Caddy для Windows)

Готовый вариант того же: `site\run-public.bat` + `deploy\windows\run-caddy.bat`.

1. Нужны белый IP у провайдера, проброс портов 80 и 443 на роутере на этот компьютер, разрешение входящих
   80/443 в брандмауэре Windows; VPN не должен перехватывать входящие соединения. Компьютер не засыпает.
2. `site\.env.public` из `site\.env.public.example`: домен (punycode), почта. Остальное (`SECRET_KEY`, токен
   обмена, база) берётся из `site\.env` — сайт работает с той же базой, что и при разработке.
3. `caddy.exe` (сборка `windows_amd64` с github.com/caddyserver/caddy/releases) — в `deploy\windows\`.
4. Запуск: `site\run-public.bat`, затем `deploy\windows\run-caddy.bat`. `run-dev.bat` при этом не запускать —
   тот же порт 8000. 1С обменивается по-прежнему с `http://localhost:8000` (API не перенаправляется на HTTPS).
5. A-запись домена — на внешний IP компьютера. Caddy получит сертификат при первом запросе.
6. Перед открытием: администратор `manage.py createsuperuser`, демо-покупатели из
   `load_demo_accounts` отключены (их пароль опубликован в README).

## Чек-лист перед запуском

- [ ] Домен, сертификат, `https://<домен>/healthz/` отвечает `ok`
- [ ] Письма доходят: оформить тестовый заказ со своей почтой
- [ ] 1С: связь проверена, каталог выгружен, тестовый заказ пришёл в 1С и вернул статус
- [ ] Тексты «Политика ПДн» и «Cookie» утверждены юристом, реквизиты оператора на месте
- [ ] Тарифы доставки, акции и бренды — реальные
- [ ] Cron: резервные копии и обезличивание, копии уходят за пределы сервера
- [ ] Через неделю без проблем с HTTPS: `SECURE_HSTS_SECONDS=31536000` в `deploy/.env`, `docker compose up -d`
