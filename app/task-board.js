(function () {
    'use strict';
    var panel = function () { return document.getElementById('taskBoardPanel'); };
    var content = function () { return document.getElementById('taskBoardContent'); };
    var error = function () { return document.getElementById('taskBoardError'); };
    var agents = [];

    function esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
            return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
        });
    }
    function showError(message) { error().textContent = message || ''; error().style.display = message ? 'block' : 'none'; }
    function agentName(id) {
        var a = agents.find(function (item) { return item.key === id || item.statusKey === id || item.agentId === id; });
        return a ? ((a.emoji || '👤') + ' ' + a.name) : (id ? id : 'Unassigned');
    }
    async function load() {
        showError('');
        content().innerHTML = '<div class="task-board-empty">Loading…</div>';
        try {
            var roster = await fetch('/agents-list', { cache: 'no-store' });
            var rosterData = await roster.json();
            agents = rosterData.agents || [];
            var response = await fetch('/api/task-board', { cache: 'no-store' });
            var data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'Could not load task board');
            render(data.tasks || []);
        } catch (e) {
            content().innerHTML = '<div class="task-board-empty">Task board unavailable.</div>';
            showError(e.message || 'Request failed');
        }
    }
    function render(tasks) {
        if (!tasks.length) { content().innerHTML = '<div class="task-board-empty">No tasks yet.</div>'; return; }
        content().innerHTML = tasks.map(function (task) {
            var p = task.progress || { done: 0, total: 0, percent: 0 };
            var options = '<option value="">Unassigned</option>' + agents.map(function (a) {
                var id = a.key || a.statusKey || a.agentId;
                return '<option value="' + esc(id) + '" ' + (task.assignee === id ? 'selected' : '') + '>' + esc(agentName(id)) + '</option>';
            }).join('');
            var checkpoints = (task.checkpoints || []).map(function (c) {
                return '<li class="' + (c.done ? 'done' : '') + '">' + (c.done ? '✓' : '○') + ' ' + esc(c.text || '') + '</li>';
            }).join('');
            return '<article class="task-board-card"><div class="task-board-card-title">' + esc(task.title) + '</div>' +
                '<div class="task-board-meta"><span>' + esc(task.projectTitle) + '</span><span class="task-board-status">' + esc(task.status) + '</span></div>' +
                '<label class="task-board-assignee">Assignee<select data-project="' + esc(task.projectId) + '" data-task="' + esc(task.id) + '" data-version="' + esc(task.expectedVersion || 0) + '">' + options + '</select></label>' +
                '<div class="task-board-progress"><div><span>Progress</span><span>' + p.done + '/' + p.total + ' (' + p.percent + '%)</span></div><div class="task-board-track"><i style="width:' + p.percent + '%"></i></div></div>' +
                (checkpoints ? '<details><summary>Checkpoints</summary><ul>' + checkpoints + '</ul></details>' : '<div class="task-board-no-checkpoints">No checkpoints</div>') + '</article>';
        }).join('');
        content().querySelectorAll('select[data-project]').forEach(function (select) {
            select.addEventListener('change', function () { reassign(select); });
        });
    }
    async function reassign(select) {
        var previous = select.dataset.previous || select.value;
        select.disabled = true; showError('');
        try {
            var expectedVersion = Number(select.dataset.version || 0);
            var idempotencyKey = 'task-board-' + Date.now() + '-' + Math.random().toString(36).slice(2);
            var response = await fetch('/api/task-board/tasks/' + encodeURIComponent(select.dataset.project) + '/' + encodeURIComponent(select.dataset.task), {
                method: 'PUT', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
                body: JSON.stringify({ assignee: select.value || null, expectedVersion: expectedVersion })
            });
            var data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'Could not reassign task');
            select.dataset.version = String(data.expectedVersion || (data.task && data.task.version) || expectedVersion);
            select.dataset.previous = select.value;
        } catch (e) {
            select.value = previous; showError(e.message || 'Could not reassign task');
        } finally { select.disabled = false; }
    }
    window.openTaskBoard = function () { var p = panel(); if (!p) return; p.classList.remove('hidden'); load(); };
    window.closeTaskBoard = function () { var p = panel(); if (p) p.classList.add('hidden'); };
}());
