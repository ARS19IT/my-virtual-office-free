# Отчёт бухгалтера: цикл распределения задач

Дата: 7 августа 2026, GMT+7
Проект: SmartSlimWay Virtual Office Free Fork
Порт: 8092

## Краткий итог

Реализован адресный dispatch родительской задачи в worker и сохранение связей parent/child/run/session. Полный цикл `Кентик → worker → дочерние агенты` не включён в production: Gateway штатно отклонил изменение защищённых политик делегации. Worker сейчас запускается как leaf на глубине 1 и не имеет права создавать дочерние subagent-сессии.

## Реализовано

- `POST /api/projects/{projectId}/tasks/{taskId}/workflow/dispatch`
- обязательное подтверждение `confirm: true`;
- запуск только явно указанной задачи;
- поддержка `parentTaskId` и дочерних задач;
- сохранение `workflowStatus`, `workerSessionKey`, `workerRunId`, `childRunLinks`;
- извлечение фактических `sessions_spawn` linkage-полей из session JSONL;
- отсутствие подтверждённого child spawn переводит задачу в `blocked`, а не в ложный `completed`;
- legacy `/workflow/start` сохранён.

## Фактические проверки

- `python3 -m py_compile app/server.py` — OK.
- `node --check app/chat.js` — OK.
- `node --check app/game.js` — OK.
- `node --check app/projects.js` — OK.
- `git diff --check` — OK.
- `GET http://127.0.0.1:8092/health` — `{"ok":true,"status":"running"}`.
- Тестовая worker-сессия создана: `agent:worker:subagent:865a6d28-5bb6-4ad3-ba27-dd6cf127b41a`.
- Её фактический статус: leaf, `spawnDepth: 1`.
- Реальный worker → child smoke-test не завершён: `sessions_spawn` недоступен из-за ограничения глубины.

## Политика Gateway

Текущая конфигурация содержит `maxConcurrent: 8`, но `maxSpawnDepth` не задан и действует default `1`.

Gateway отклонил штатный patch следующих защищённых путей:

- `agents.defaults.subagents.maxSpawnDepth`;
- `agents.defaults.subagents.maxChildrenPerAgent`;
- `agents.list[].subagents.allowAgents`.

Обход защищённой политики не выполнялся.

## Требуемое изменение для полного цикла

Нужна явная административная настройка Gateway:

- `agents.defaults.subagents.maxSpawnDepth = 2`;
- `agents.list[worker].subagents.allowAgents = [team, 2, designer, memory, dising]`;
- разрешить worker session-tools согласно policy.

После этого провести smoke-test с одним дочерним агентом `team` и проверить фактические `runId`, `sessionKey`, ACK и завершение без активных детей.

## Ограничения

- Общая панель не менялась по запросу.
- Telegram-доставка невозможна без конкретного Telegram target, которого в текущем WebChat-сеансе нет.
- PDF из этого отчёта должен быть сформирован после подтверждения доступного канала доставки.
