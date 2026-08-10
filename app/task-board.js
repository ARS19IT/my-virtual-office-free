(function () {
    'use strict';

    const panel = () => document.getElementById('taskBoardPanel');
    const content = () => document.getElementById('taskBoardContent');
    const error = () => document.getElementById('taskBoardError');
    let agents = [];
    let tasks = [];
    let columns = [];
    let draggedCard = null;
    let panelDrag = null;

    function esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }
    function showError(message) {
        error().textContent = message || '';
        error().style.display = message ? 'block' : 'none';
    }
    function restorePanelPosition() {
        const saved = (() => { try { return JSON.parse(localStorage.getItem('task-board-position') || 'null'); } catch (_) { return null; } })();
        const el = panel();
        const maxLeft = Math.max(6, window.innerWidth - el.offsetWidth - 6);
        const maxTop = Math.max(48, window.innerHeight - Math.min(el.offsetHeight, window.innerHeight) - 6);
        if (saved && Number.isFinite(saved.left) && Number.isFinite(saved.top)) {
            el.style.left = `${Math.min(maxLeft, Math.max(6, saved.left))}px`;
            el.style.top = `${Math.min(maxTop, Math.max(48, saved.top))}px`;
        } else el.style.left = `${Math.max(6, (window.innerWidth - el.offsetWidth) / 2)}px`;
    }
    function startPanelDrag(event) {
        if (event.target.closest('button')) return;
        const el = panel(), rect = el.getBoundingClientRect();
        panelDrag = { pointerId: event.pointerId, dx: event.clientX - rect.left, dy: event.clientY - rect.top };
        el.setPointerCapture?.(event.pointerId); event.preventDefault();
    }
    function movePanel(event) {
        if (!panelDrag || event.pointerId !== panelDrag.pointerId) return;
        const el = panel(), maxLeft = Math.max(0, innerWidth - el.offsetWidth), maxTop = Math.max(0, innerHeight - 48);
        el.style.left = `${Math.min(maxLeft, Math.max(0, event.clientX - panelDrag.dx))}px`;
        el.style.top = `${Math.min(maxTop, Math.max(0, event.clientY - panelDrag.dy))}px`;
    }
    function endPanelDrag(event) {
        if (!panelDrag || event.pointerId !== panelDrag.pointerId) return;
        const el = panel(); panelDrag = null;
        try { localStorage.setItem('task-board-position', JSON.stringify({ left: el.offsetLeft, top: el.offsetTop })); } catch (_) {}
    }
    function agentName(id) {
        const agent = agents.find(a => a.key === id || a.statusKey === id || a.agentId === id || a.id === id);
        return agent ? `${agent.emoji || '👤'} ${agent.name || agent.label || id}` : (id || 'Unassigned');
    }
    function agentOptions(task) {
        return '<option value="">Unassigned</option>' + agents.map(agent => {
            const id = agent.key || agent.statusKey || agent.agentId || agent.id;
            return `<option value="${esc(id)}" ${String(task.assignee || '') === String(id) ? 'selected' : ''}>${esc(agentName(id))}</option>`;
        }).join('');
    }
    function groupedColumns() {
        const map = new Map(columns.map(column => [`${column.projectId}:${column.id}`, {
            id: column.id, projectId: column.projectId, title: column.title || 'Uncategorized', tasks: []
        }]));
        tasks.forEach(task => {
            const id = String(task.statusId || 'uncategorized');
            const key = `${task.projectId}:${id}`;
            if (!map.has(key)) map.set(key, { id, projectId: task.projectId, title: task.status || 'Uncategorized', tasks: [] });
            map.get(key).tasks.push(task);
        });
        return [...map.values()];
    }
    function renderCard(task) {
        const progress = task.progress || { done: 0, total: 0, percent: 0 };
        const checkpoints = (task.checkpoints || []).map(checkpoint =>
            `<li class="${checkpoint.done ? 'done' : ''}">${checkpoint.done ? '✓' : '○'} ${esc(checkpoint.text || '')}</li>`
        ).join('');
        return `<article class="task-board-card" draggable="true"
            data-project="${esc(task.projectId)}" data-task="${esc(task.id)}"
            data-version="${esc(task.expectedVersion || 0)}">
            <div class="task-board-card-title">${esc(task.title)}</div>
            <div class="task-board-meta"><span>${esc(task.projectTitle)}</span><span class="task-board-status">${esc(task.priority || 'medium')}</span></div>
            <label class="task-board-assignee">Assignee
                <select data-project="${esc(task.projectId)}" data-task="${esc(task.id)}" data-version="${esc(task.expectedVersion || 0)}" data-previous="${esc(task.assignee || '')}">
                    ${agentOptions(task)}
                </select>
            </label>
            <div class="task-board-progress"><div><span>Progress</span><span>${progress.done}/${progress.total} (${progress.percent}%)</span></div>
                <div class="task-board-track"><i style="width:${progress.percent}%"></i></div>
            </div>
            ${checkpoints ? `<details><summary>Checkpoints</summary><ul>${checkpoints}</ul></details>` : ''}
        </article>`;
    }
    function render() {
        const boardColumns = groupedColumns();
        if (!boardColumns.length) {
            content().innerHTML = '<div class="task-board-empty">No tasks yet.</div>';
            return;
        }
        content().innerHTML = `<div class="task-board-columns">${boardColumns.map(column => `
            <section class="task-board-column" data-project="${esc(column.projectId)}" data-column="${esc(column.id)}">
                <header><strong>${esc(column.title)}</strong><span>${column.tasks.length}</span></header>
                <div class="task-board-dropzone" aria-label="Drop tasks in ${esc(column.title)}">
                    ${column.tasks.map(renderCard).join('')}
                </div>
            </section>`).join('')}</div>`;
        content().querySelectorAll('.task-board-card').forEach(card => {
            card.addEventListener('dragstart', onDragStart);
            card.addEventListener('dragend', onDragEnd);
        });
        content().querySelectorAll('.task-board-dropzone').forEach(zone => {
            zone.addEventListener('dragover', onDragOver);
            zone.addEventListener('dragleave', onDragLeave);
            zone.addEventListener('drop', onDrop);
        });
        content().querySelectorAll('select[data-project]').forEach(select => {
            select.addEventListener('change', () => reassign(select));
        });
    }
    function onDragStart(event) {
        draggedCard = event.currentTarget;
        event.dataTransfer.effectAllowed = 'move';
        // Keep project and task separate: IDs may contain slashes.
        event.dataTransfer.setData('application/json', JSON.stringify({ projectId: draggedCard.dataset.project, taskId: draggedCard.dataset.task }));
        event.dataTransfer.setData('text/plain', draggedCard.dataset.task);
        draggedCard.classList.add('is-dragging');
    }
    function onDragEnd() {
        draggedCard?.classList.remove('is-dragging');
        draggedCard = null;
        content().querySelectorAll('.is-drop-target').forEach(el => el.classList.remove('is-drop-target'));
    }
    function onDragOver(event) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        event.currentTarget.closest('.task-board-column').classList.add('is-drop-target');
    }
    function onDragLeave(event) {
        if (!event.currentTarget.contains(event.relatedTarget)) {
            event.currentTarget.closest('.task-board-column').classList.remove('is-drop-target');
        }
    }
    async function onDrop(event) {
        event.preventDefault();
        const zone = event.currentTarget;
        const column = zone.closest('.task-board-column');
        column.classList.remove('is-drop-target');
        let dragData = {};
        try { dragData = JSON.parse(event.dataTransfer.getData('application/json') || '{}'); } catch (_) {}
        const projectId = String(dragData.projectId || '');
        const taskId = String(dragData.taskId || event.dataTransfer.getData('text/plain') || '');
        const task = tasks.find(item => String(item.projectId) === projectId && String(item.id) === taskId);
        if (task && String(column.dataset.project) !== String(task.projectId)) return;
        if (!task || String(task.statusId || '') === String(column.dataset.column || '')) return;
        try {
            const response = await fetch(`/api/task-board/tasks/${encodeURIComponent(task.projectId)}/${encodeURIComponent(task.id)}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ columnId: column.dataset.column, expectedVersion: Number(task.expectedVersion || 0) })
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'Could not move task');
            task.statusId = column.dataset.column;
            task.status = column.querySelector('strong').textContent;
            task.expectedVersion = data.expectedVersion;
            render();
        } catch (err) {
            showError(err.message || 'Could not move task. Refresh and try again.');
        }
    }
    async function reassign(select) {
        const task = tasks.find(item => String(item.projectId) === select.dataset.project && String(item.id) === select.dataset.task);
        const previous = task ? (task.assignee || '') : (select.dataset.previous ?? '');
        select.disabled = true;
        showError('');
        try {
            const key = `task-board-${Date.now()}-${Math.random().toString(36).slice(2)}`;
            const response = await fetch(`/api/task-board/tasks/${encodeURIComponent(select.dataset.project)}/${encodeURIComponent(select.dataset.task)}`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
                body: JSON.stringify({ assignee: select.value || null, expectedVersion: Number(select.dataset.version || 0) })
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'Could not reassign task');
            if (task) task.assignee = select.value || null;
            const version = data.expectedVersion || (data.task && data.task.version) || Number(select.dataset.version || 0);
            if (task) task.expectedVersion = version;
            select.dataset.version = String(version);
            select.dataset.previous = select.value;
        } catch (err) {
            select.value = previous;
            showError(err.message || 'Could not reassign task');
        } finally {
            select.disabled = false;
        }
    }
    async function load() {
        showError('');
        content().innerHTML = '<div class="task-board-empty">Loading…</div>';
        try {
            const roster = await fetch('/agents-list', { cache: 'no-store' });
            agents = (await roster.json()).agents || [];
            const response = await fetch('/api/task-board', { cache: 'no-store' });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'Could not load task board');
            tasks = data.tasks || [];
            columns = data.columns || [];
            render();
        } catch (err) {
            content().innerHTML = '<div class="task-board-empty">Task board unavailable.</div>';
            showError(err.message || 'Request failed');
        }
    }
    document.querySelector('#taskBoardPanel .task-board-header')?.addEventListener('pointerdown', startPanelDrag);
    panel()?.addEventListener('pointermove', movePanel); panel()?.addEventListener('pointerup', endPanelDrag); panel()?.addEventListener('pointercancel', endPanelDrag);
    window.addEventListener('resize', () => { if (!panelDrag) restorePanelPosition(); });
    window.openTaskBoard = function () { const element = panel(); if (element) { element.classList.remove('hidden'); restorePanelPosition(); load(); } };
    window.closeTaskBoard = function () { panel()?.classList.add('hidden'); };
}());
