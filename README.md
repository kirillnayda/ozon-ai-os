# Ozon AI OS — Foundation 0.1.0

Первая серверная основа проекта Ozon AI Team.

## Что работает

- Telegram-бот 24/7 через long polling
- команды `/start`, `/status`, `/ozon_test`, `/settings`
- проверка доступа к Ozon Seller API
- SQLite-база для событий и настроек
- автозапуск и перезапуск через systemd
- секреты хранятся только в `.env`
- безопасный режим: никаких изменений в кабинете Ozon

## Установка на Ubuntu 24.04

```bash
sudo bash install.sh
```

Установщик запросит:

- Telegram Bot Token
- Telegram Chat ID
- Ozon Client ID
- Ozon API Key

После установки:

```bash
systemctl status ozon-ai-os
journalctl -u ozon-ai-os -n 100 --no-pager
```

## Команды Telegram

- `/start` — проверить бота
- `/status` — статус системы
- `/ozon_test` — проверить Seller API
- `/settings` — показать бизнес-правила без секретов

## Безопасность

Файл `.env` исключён из Git и доступен только системному пользователю.
Текущая версия работает только на чтение.
