# Отчёт: необходимые инструменты и доступы

Дата: 2026-08-07 (GMT+7)
Проект: SmartSlimWay Virtual Office Free

## 1. Для исправления моделей агентов

Нужен штатный административный доступ к защищённой конфигурации Gateway, чтобы изменить только подтверждённые поля:

- Main: оставить `a6api/gpt-5.6-luna`.
- Memory: назначить зарегистрированную модель из `a6api`, например `a6api/gpt-5.6-luna`, без Terra.
- Worker: назначить зарегистрированную модель из `a6api`, например `a6api/gpt-5.6-luna`, либо другой явно подтверждённый текстовый model ID.
- Designer: назначить текстовую рабочую модель из `a6api` и отдельно настроить image backend; image input не считать генерацией.
- Не добавлять несуществующие ссылки вида `a6api-memory/gpt-5.6-luna`, `a6api-designer/gpt-5.6-luna` или `a6api-worker/gpt-5.6-luna`, пока такие model IDs не зарегистрированы у provider.

Ключи API не нужны в отчёте и не должны передаваться в workspace или чат. Достаточно административной операции Gateway через штатный config API/CLI.

## 2. Для полноценной работы Worker

Worker нужен доступ к:

- `sessions_spawn` для запуска независимых дочерних веток;
- `sessions_list` и/или эквиваленту для контроля активных и завершённых runs;
- `sessions_history` или безопасному event stream для проверки результатов;
- `sessions_yield` для ожидания обязательных веток;
- read-only Gateway/task telemetry или локальному журналу workflow;
- инструментам `exec/read/process` для verification gate.

Доступ должен быть узким: Worker не получает права на удаление, Gateway restart, изменение OpenClaw config/scheduler/permissions, secret handling или внешние сообщения без явного подтверждения.

## 3. Для Designer и web/image workflow

Уже доступны:

- `web_search` и `web_fetch`;
- image capability-инструменты.

Нужно настроить ровно один безопасный image-generation provider через штатный секретный механизм Gateway. Подходят только provider с фактическими признаками `configured:true` и `selected:true`. Возможные backend-классы: Gemini image, GPT Image, Flux/Krea/fal, Grok Imagine, ComfyUI; конкретный выбор зависит от имеющегося ключа и тарифа.

Текущий DuckDuckGo search иногда возвращает bot-detection challenge; нужен надёжный configured search provider или fallback, а не выдача challenge за результат.

## 4. Для бухгалтерских отчётов

Нужен безопасный read-only источник worker telemetry с полями:

`task_id`, `parent_task_id`, `attempt`, `run_id`, `session_id`, `executor`, `provider`, `model`, `status`, `started_at`, `finished_at`, `input_tokens`, `output_tokens`, `total_tokens`, `retry_of`, `error_code`, `error_message`, `evidence_ref`.

Отчёт должен получать данные из первичных событий/логов/usage records и обозначать отсутствующие поля как `н/д`. Нельзя суммировать parent и child tokens, если parent total уже включает children.

## 5. Для Telegram-доставки

Gateway Telegram уже включён, но для первой доставки нужны:

- подтверждение пользователя на внешнюю отправку;
- целевой `chat_id` личного чата, группы или канала;
- подтверждение, что пользователь открыл диалог с ботом;
- для группы/канала: бот добавлен и имеет право отправлять документы/сообщения;
- правило доставки: после worker cycle, вручную или по расписанию;
- предпочтительный формат: два отдельных сообщения или два Markdown-файла.

Bot token уже находится в конфигурации Gateway и не должен дублироваться в сообщениях, отчётах или GitHub.

## Не требуется

- Не требуется расширять Gateway bind на `0.0.0.0`.
- Не требуется отключать auth или safeguards.
- Не требуется менять Tailscale routes до диагностики причины `502` на `/ws-gateway`.
