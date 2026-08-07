/* Russian UI layer for My Virtual Office. Keeps provider/model/file names intact. */
(function () {
  'use strict';
  var exact = {
    'SETTINGS':'НАСТРОЙКИ','OpenClaw Connection':'ПОДКЛЮЧЕНИЕ OPENCLAW','OpenClaw Path':'Путь OpenClaw','Gateway URL':'Адрес шлюза','Gateway Token':'Токен шлюза','Test Connection':'Проверить подключение','Office':'ОФИС','Office Name':'Название офиса','Weather Location':'Место для погоды','Display':'ЭКРАН','Show chat bubbles':'Показывать облачка чата','Show agent names':'Показывать имена агентов','API Usage':'ИСПОЛЬЗОВАНИЕ API','Show API Usage Panel':'Показывать панель API','PC Performance':'ПРОИЗВОДИТЕЛЬНОСТЬ ПК','Enable PC Performance Monitor':'Включить мониторинг ПК','Agent Browser':'БРАУЗЕР АГЕНТА','Weather':'ПОГОДА','Show weather effects':'Показывать эффекты погоды','Actions':'ДЕЙСТВИЯ','Help':'ПОМОЩЬ','Save Settings':'Сохранить настройки','Export Office Config':'Экспорт конфигурации офиса','Import Office Config':'Импорт конфигурации офиса','Full Reset':'Полный сброс','Run Setup Wizard':'Запустить мастер настройки','Navigation:':'Навигация:','Edit Office:':'Редактор офиса:','Resize office:':'Размер офиса:','Agents:':'Агенты:','Multi-select:':'Множественный выбор:','Move group:':'Перемещение группы:','Shortcuts:':'Горячие клавиши:','Menu':'Меню','Edit Office':'Редактировать офис','Save':'Сохранить','Undo':'Отменить','Agents':'Агенты','Expand All':'Развернуть всё','Minimize All':'Свернуть всё','Models':'Модели','Cron':'Расписание','Projects':'Проекты','Reset':'Сбросить','SMS':'СМС','Browser':'Браузер','DASHBOARD':'ЦЕНТР УПРАВЛЕНИЯ','Working':'Работают','Idle':'Свободны','Meeting':'На встрече','Break':'Перерыв','Lounge':'Комната отдыха','Online':'В сети','Task:':'Задача:','Branch':'Ветка','Updated:':'Обновлено:','Apply':'Применить','Cancel':'Отмена','Close':'Закрыть','Edit':'Изменить','Delete':'Удалить','Clear':'Очистить','Think':'Подумать','Say':'Сказать','Work':'Работа','Meet':'Встреча','Break':'Перерыв','Open Meetings':'Открыть встречи','Open Projects':'Открыть проекты','Open Skills Library':'Открыть библиотеку навыков','Active':'Активные','History':'История','Skills Library':'Библиотека навыков','Add Skill':'Добавить навык','Skill Name':'Название навыка','SKILL.md Content':'Содержимое SKILL.md','Summary':'Итоги','Resolution':'Решение','Action Items':'Пункты действий','End Meeting':'Завершить встречу','Inbox':'Входящие','Open':'Открыть','Select contact...':'Выберите контакт...','Agent':'Агент','Sessions':'Сессии','Offline':'Не в сети','Idle':'Свободен','Take Control':'Взять управление','Release to AI':'Вернуть управление ИИ','Open agent workspace':'Открыть рабочее пространство агента','Overview':'Обзор','Bulletin':'Объявления','Tasks':'Задачи','Files':'Файлы','Notes':'Заметки','Settings':'Настройки','Skills':'Навыки','Loading...':'Загрузка...','Loading agents...':'Загрузка агентов...','No agents. Click ➕ New Agent to create one.':'Нет агентов. Нажмите ➕ Новый агент, чтобы создать его.','New Agent':'Новый агент','Save Skill':'Сохранить навык','Save Settings':'Сохранить настройки','Current:':'Текущая модель:','Applying...':'Применение…','Error loading models':'Ошибка загрузки моделей','Failed':'Ошибка','Saved':'Сохранено','No skills configured':'Навыки не настроены','Loading skills...':'Загрузка навыков…','No skills in library':'В библиотеке нет навыков','Failed to load library':'Не удалось загрузить библиотеку','No active meetings':'Нет активных встреч','No skills in library. Click ➕ Add Skill to create one.':'В библиотеке нет навыков. Нажмите ➕ Добавить навык.','Agent failed before JST':'Агент завершился до запуска','file already exists':'файл уже существует','Workspace unavailable':'Рабочее пространство недоступно','Loading workspace...':'Загрузка рабочего пространства…','Untitled note':'Заметка без названия','General':'Общее','normal':'обычный','high':'высокий','low':'низкий','Due':'Срок','Details or instructions':'Подробности или инструкции','Write notes, lists, pages, or grouped context':'Напишите заметки, списки, страницы или общий контекст','Search files':'Поиск файлов','Refresh':'Обновить','Apply':'Применить','Type:':'Тип:','Name:':'Имя:','Role:':'Роль:','Color:':'Цвет:','Main:':'Основной:','Accent:':'Акцент:','Trim:':'Окантовка:','Tile A:':'Плитка A:','Tile B:':'Плитка B:','Done Editing':'Закончить редактирование','Edit Floor Tiles':'Редактировать плитку пола','Done Floor Edit':'Закончить редактирование пола','SNAP ZONE':'ЗОНА ПРИВЯЗКИ','Enable pet':'Включить питомца','Office Pet':'Питомец офиса','Save changes':'Сохранить изменения','Undo last change':'Отменить последнее изменение','Settings & Help':'Настройки и помощь','Create and customize agents':'Создать и настроить агентов','Expand all bubbles':'Развернуть все облачка','Collapse all widgets':'Свернуть все блоки','Expand all widgets':'Развернуть все блоки'
  };
  var contains = [
    [/^\s*DEMO\s*[—-]/i, '⚡ ЛОКАЛЬНЫЙ РЕЖИМ — расширенные функции доступны на этом компьютере'],
    [/^\s*No recent request\s*$/i, 'Нет последнего запроса'],[/^\s*No recent response\s*$/i, 'Нет последнего ответа'],[/^\s*No model changed\s*$/i, 'Модель не изменена'],[/^\s*Unknown\s*$/i, 'Неизвестно'],[/^\s*None\s*$/i, 'Нет'],[/^\s*Loading proposals\.\.\.\s*$/i, 'Загрузка предложений…']
  ];
  function translateValue(value) {
    if (!value || typeof value !== 'string') return value;
    var trimmed = value.trim();
    if (exact[trimmed]) return value.replace(trimmed, exact[trimmed]);
    for (var i=0;i<contains.length;i++) if (contains[i][0].test(trimmed)) return value.replace(trimmed, contains[i][1]);
    return value;
  }
  function walk(root) {
    if (!root) return;
    var nodes = root.nodeType === 3 ? [root] : (root.querySelectorAll ? Array.prototype.slice.call(root.querySelectorAll('*')) : []);
    if (root.nodeType === 1) nodes.unshift(root);
    nodes.forEach(function (el) {
      // The toolbar owns its Russian labels. Excluding it prevents the
      // localization observer from racing ui-modern during page startup.
      if (el.closest && el.closest('.toolbar')) return;
      if (!el || ['SCRIPT','STYLE','CODE','PRE','INPUT'].indexOf(el.tagName) >= 0) return;
      Array.prototype.slice.call(el.childNodes || []).forEach(function (n) {
        if (n.nodeType === 3) { var next=translateValue(n.nodeValue); if(next!==n.nodeValue)n.nodeValue=next; }
      });
      ['title','placeholder','aria-label'].forEach(function (attr) { if (el.hasAttribute && el.hasAttribute(attr)) { var v=translateValue(el.getAttribute(attr)); if(v!==el.getAttribute(attr))el.setAttribute(attr,v); } });
    });
  }
  function boot() {
    document.documentElement.lang='ru';
    document.title='Виртуальный офис';
    walk(document.body);
    var observer = new MutationObserver(function (records) { records.forEach(function (r) { Array.prototype.slice.call(r.addedNodes).forEach(walk); if(r.type==='characterData') walk(r.target); }); });
    observer.observe(document.body, {childList:true,subtree:true,characterData:true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
