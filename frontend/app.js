const { animate, stagger } = anime;
const chartTheme = {
  accent: '#412CFF',
  accentFill: 'rgba(65, 44, 255, 0.10)',
  grid: 'rgba(34, 35, 49, 0.08)',
  text: '#222331',
  muted: '#747684',
  success: '#12815f',
  warning: '#a86f00',
  danger: '#d94b74',
  font: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
};

// ── Animation Helpers ──
function animateFadeUp(selector, delay = 0) {
  animate(selector, {
    opacity: [0, 1],
    translateY: [20, 0],
    duration: 500,
    delay: delay ? stagger(80, { start: delay }) : stagger(80),
    ease: 'outExpo',
  });
}

function animateScaleIn(selector, delay = 0) {
  animate(selector, {
    opacity: [0, 1],
    scale: [0.85, 1],
    duration: 400,
    delay: delay ? stagger(60, { start: delay }) : stagger(60),
    ease: 'outBack',
  });
}

function animateScoreBars(container) {
  const fills = container.querySelectorAll('.score-bar-fill');
  fills.forEach(fill => {
    const target = fill.getAttribute('data-target-width');
    fill.style.width = '0%';
    animate(fill, {
      width: `${target}%`,
      duration: 800,
      delay: stagger(100),
      ease: 'outExpo',
    });
  });

  const values = container.querySelectorAll('.score-bar-value');
  values.forEach(val => {
    const target = parseInt(val.getAttribute('data-target-value'), 10);
    const obj = { v: 0 };
    animate(obj, {
      v: target,
      duration: 800,
      delay: stagger(100),
      ease: 'outExpo',
      onUpdate: () => { val.textContent = `${Math.round(obj.v)}%`; },
    });
  });
}

function animateStatValues(container) {
  const statValues = container.querySelectorAll('.stat-value');
  statValues.forEach(el => {
    const raw = el.textContent;
    const numMatch = raw.match(/^([\d.]+)/);
    if (!numMatch) return;
    const target = parseFloat(numMatch[1]);
    const suffix = raw.replace(numMatch[1], '');
    const isInt = !raw.includes('.') || suffix === '%';
    const obj = { v: 0 };
    animate(obj, {
      v: target,
      duration: 900,
      ease: 'outExpo',
      onUpdate: () => {
        el.textContent = (isInt ? Math.round(obj.v) : obj.v.toFixed(1)) + suffix;
      },
    });
  });
}

// ── Tab Navigation ──
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    const section = document.getElementById(`tab-${tab.dataset.tab}`);
    section.classList.add('active');

    // Animate tab content entrance
    animate(section, {
      opacity: [0, 1],
      translateY: [12, 0],
      duration: 350,
      ease: 'outQuad',
    });

    if (tab.dataset.tab === 'dashboard') loadDashboard();
    if (tab.dataset.tab === 'history') loadHistory();
  });
});

// ── Task Form ──
const tasksContainer = document.getElementById('tasks-container');
document.getElementById('add-task').addEventListener('click', () => {
  const row = document.createElement('div');
  row.className = 'task-row';
  row.innerHTML = `
    <input type="text" class="task-input" placeholder="e.g. Find contact information" required>
    <button type="button" class="btn-icon remove-task" title="Remove">&times;</button>
  `;
  tasksContainer.appendChild(row);
  animate(row, {
    opacity: [0, 1],
    translateX: [-20, 0],
    duration: 350,
    ease: 'outQuad',
  });
});

tasksContainer.addEventListener('click', e => {
  if (e.target.classList.contains('remove-task') && tasksContainer.children.length > 1) {
    const row = e.target.closest('.task-row');
    animate(row, {
      opacity: [1, 0],
      translateX: [0, 20],
      duration: 250,
      ease: 'inQuad',
      onComplete: () => row.remove(),
    });
  }
});

// ── Job Queue ──
const activeJobs = new Map(); // job_id -> { url, tasks, status }
let pollInterval = null;
let currentPollMs = 3000;

document.getElementById('browse-form').addEventListener('submit', async e => {
  e.preventDefault();
  const url = document.getElementById('url').value;
  const tasks = [...document.querySelectorAll('.task-input')].map(i => i.value).filter(Boolean);
  if (!tasks.length) return;

  try {
    const res = await fetch('/api/browse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, tasks }),
    });
    const data = await res.json();
    if (data.job_id) {
      activeJobs.set(data.job_id, { url, tasks, status: 'running' });
      renderJobsQueue();
      startPolling();
    }
  } catch (err) {
    // Show inline error in queue
    const tempId = 'err-' + Date.now();
    activeJobs.set(tempId, { url, tasks, status: 'completed', error: err.message, results: [] });
    renderJobsQueue();
  }
});

function startPolling() {
  if (pollInterval) return;
  currentPollMs = 3000;
  pollInterval = setInterval(pollJobs, currentPollMs);
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

async function pollJobs() {
  const running = [...activeJobs.entries()].filter(([, j]) => j.status === 'running');
  if (!running.length) { stopPolling(); return; }

  let hasPending = false;
  for (const [jobId] of running) {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      const job = await res.json();
      activeJobs.set(jobId, job);
      if (job.pending_inputs && job.pending_inputs.length > 0) hasPending = true;
    } catch { /* ignore poll errors */ }
  }
  renderJobsQueue();

  // Poll faster when there are pending HITL inputs
  const newInterval = hasPending ? 1500 : 3000;
  if (pollInterval && currentPollMs !== newInterval) {
    clearInterval(pollInterval);
    currentPollMs = newInterval;
    pollInterval = setInterval(pollJobs, currentPollMs);
  }
}

function renderJobsQueue() {
  const container = document.getElementById('jobs-queue');
  if (!activeJobs.size) { container.innerHTML = ''; return; }

  // Preserve HITL input values and focus state before re-render
  const hitlValues = {};
  let focusedTaskId = null;
  container.querySelectorAll('.hitl-prompt').forEach(el => {
    const tid = el.dataset.taskId;
    const input = el.querySelector('.hitl-input');
    if (input) {
      hitlValues[tid] = input.value;
      if (document.activeElement === input) focusedTaskId = tid;
    }
  });

  const cards = [...activeJobs.entries()].reverse().map(([jobId, job]) => {
    const isRunning = job.status === 'running';
    const host = (() => { try { return new URL(job.url).hostname; } catch { return job.url; } })();
    const taskCount = (job.tasks || []).length;
    const doneCount = (job.results || []).length;

    // HITL: pending input prompts
    const pendingInputs = job.pending_inputs || [];
    const hitlHtml = pendingInputs.map(p => `
      <div class="hitl-prompt" data-task-id="${p.task_id}" data-job-id="${jobId}">
        <div class="hitl-header">
          <span class="hitl-icon">&#9888;</span>
          <span class="hitl-label">Input needed for: ${esc(p.task)}</span>
        </div>
        <div class="hitl-question">${esc(p.question)}</div>
        <div class="hitl-input-row">
          <input type="text" class="hitl-input" placeholder="Type your response..." autocomplete="off">
          <button class="btn-primary hitl-submit" onclick="submitHitlResponse('${jobId}', '${p.task_id}', this)">Send</button>
        </div>
      </div>
    `).join('');

    let statusHtml;
    if (isRunning) {
      const progress = taskCount > 0 ? `${doneCount} of ${taskCount} tasks done` : 'Starting...';
      statusHtml = `
        <div class="job-status-row">
          <div class="loading-spinner-sm"></div>
          <span class="job-progress">${progress}</span>
        </div>
        ${hitlHtml}`;
    } else {
      statusHtml = '';
    }

    const resultsHtml = (job.results || []).map(r => `
      <div class="result-card">
        <div class="result-header">
          <span class="result-task">${esc(r.task)}</span>
          <span class="badge ${r.found ? 'badge-success' : 'badge-error'}">
            ${r.found ? 'Found' : 'Not Found'}
          </span>
        </div>
        ${r.answer ? `<div class="result-answer">${esc(r.answer)}</div>` : ''}
        ${r.error ? `<div class="result-answer" style="color: var(--danger)">${esc(r.error)}</div>` : ''}
        <div class="result-meta">
          <span>Steps: ${r.steps_taken}</span>
          <span>Duration: ${r.duration_seconds.toFixed(1)}s</span>
          <span>Errors: ${r.errors_encountered}</span>
          <span>Overall: ${r.scores ? (r.scores.overall * 100).toFixed(0) + '%' : '-'}</span>
        </div>
        ${r.recording_path ? `<div class="recording-container"><video controls class="recording-video" preload="metadata"><source src="/media/${esc(r.recording_path)}" type="video/mp4"></video></div>` : ''}
        ${r.scores ? renderScoreBars(r.scores) : ''}
        ${renderStepDetails(r.step_details)}
      </div>
    `).join('');

    return `
      <div class="card job-card" data-job-id="${jobId}">
        <div class="job-header">
          <div class="job-title">
            <span class="badge ${isRunning ? 'badge-running' : 'badge-success'}">${isRunning ? 'Running' : 'Done'}</span>
            <span class="job-url">${esc(host)}</span>
            <span class="job-task-count">${taskCount} task${taskCount !== 1 ? 's' : ''}</span>
          </div>
          <button class="btn-icon job-dismiss" onclick="dismissJob('${jobId}')" title="Dismiss">&times;</button>
        </div>
        ${statusHtml}
        ${resultsHtml}
      </div>`;
  }).join('');

  const prevIds = new Set(container.querySelectorAll('.job-card').length ? [...container.querySelectorAll('.job-card')].map(el => el.dataset.jobId) : []);
  container.innerHTML = cards;

  // Animate new cards
  container.querySelectorAll('.job-card').forEach(card => {
    if (!prevIds.has(card.dataset.jobId)) {
      animate(card, { opacity: [0, 1], translateY: [15, 0], duration: 400, ease: 'outQuad' });
    }
  });

  // Animate score bars and value counters in completed results
  container.querySelectorAll('.result-card').forEach(card => {
    animateScoreBars(card);
  });

  // Restore HITL input values and focus after re-render
  container.querySelectorAll('.hitl-prompt').forEach(el => {
    const tid = el.dataset.taskId;
    const input = el.querySelector('.hitl-input');
    if (input && hitlValues[tid] !== undefined) {
      input.value = hitlValues[tid];
      if (tid === focusedTaskId) input.focus();
    }
  });
}

function dismissJob(jobId) {
  const card = document.querySelector(`.job-card[data-job-id="${jobId}"]`);
  if (card) {
    animate(card, {
      opacity: [1, 0], translateX: [0, 30], duration: 250, ease: 'inQuad',
      onComplete: () => { activeJobs.delete(jobId); renderJobsQueue(); },
    });
  } else {
    activeJobs.delete(jobId);
    renderJobsQueue();
  }
}

// Allow Enter key to submit HITL responses
document.getElementById('jobs-queue').addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.target.classList.contains('hitl-input')) {
    const btn = e.target.closest('.hitl-prompt').querySelector('.hitl-submit');
    if (btn && !btn.disabled) btn.click();
  }
});

async function submitHitlResponse(jobId, taskId, btn) {
  const row = btn.closest('.hitl-prompt');
  const input = row.querySelector('.hitl-input');
  const answer = input.value.trim();
  if (!answer) return;

  btn.disabled = true;
  btn.textContent = 'Sending...';

  try {
    const res = await fetch(`/api/jobs/${jobId}/input?task_id=${encodeURIComponent(taskId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      animate(row, {
        opacity: [1, 0], height: [row.offsetHeight, 0], duration: 300, ease: 'inQuad',
        onComplete: () => row.remove(),
      });
    } else {
      btn.disabled = false;
      btn.textContent = 'Send';
      alert(data.error || 'Failed to submit response');
    }
  } catch (err) {
    btn.disabled = false;
    btn.textContent = 'Send';
  }
}

function renderScoreBars(scores) {
  const dims = ['completeness', 'confidence', 'efficiency', 'speed', 'reliability'];
  return `<div class="score-bar-group">${dims.map(d => {
    const val = scores[d];
    const pct = (val * 100).toFixed(0);
    const color = val >= 0.7 ? 'var(--success)' : val >= 0.4 ? 'var(--warning)' : 'var(--magenta)';
    return `
      <div class="score-bar-row">
        <span class="score-bar-label">${capitalize(d)}</span>
        <div class="score-bar-track">
          <div class="score-bar-fill" data-target-width="${pct}" style="width:0%;background:${color}"></div>
        </div>
        <span class="score-bar-value" data-target-value="${pct}">0%</span>
      </div>`;
  }).join('')}</div>`;
}

// ── Dashboard ──
let radarChart = null;
let trendChart = null;
let urlRadarChart = null;

async function loadDashboard() {
  const [statsRes, historyRes, urlsRes] = await Promise.all([
    fetch('/api/dashboard'),
    fetch('/api/results?limit=100'),
    fetch('/api/urls'),
  ]);
  const stats = await statsRes.json();
  const history = await historyRes.json();
  const urls = await urlsRes.json();

  renderStatCards(stats);
  renderInsights(stats.top_issues || [], stats.recommendations || []);
  renderRadarChart(stats.avg_scores);
  renderTrendChart(history);
  populateUrlDropdown(urls);
}

function renderStatCards(stats) {
  const grid = document.getElementById('stats-grid');
  const cards = [
    { value: stats.total_runs, label: 'Total Runs' },
    { value: stats.successful_runs, label: 'Successful' },
    { value: `${(stats.avg_scores.overall * 100).toFixed(0)}%`, label: 'Avg Score' },
    { value: `${stats.avg_duration.toFixed(1)}s`, label: 'Avg Duration' },
    { value: stats.avg_steps.toFixed(1), label: 'Avg Steps' },
  ];
  grid.innerHTML = cards.map(c => `
    <div class="stat-card">
      <div class="stat-value">${c.value}</div>
      <div class="stat-label">${c.label}</div>
    </div>
  `).join('');

  // Animate stat cards staggered entrance
  animateScaleIn('#stats-grid .stat-card');
  // Animate counter values
  setTimeout(() => animateStatValues(grid), 100);
}

function renderInsights(issues, recommendations) {
  const issuesEl = document.getElementById('top-issues');
  if (!issues.length) {
    issuesEl.innerHTML = '<div class="empty-state">No issues detected yet</div>';
  } else {
    issuesEl.innerHTML = issues.map(issue => {
      const severityClass = issue.severity === 'high' ? 'severity-high' : issue.severity === 'medium' ? 'severity-medium' : 'severity-low';
      return `
        <div class="issue-item ${severityClass}">
          <div class="issue-header">
            <span class="issue-severity">${issue.severity.toUpperCase()}</span>
            <span class="issue-category">${esc(issue.category)}</span>
          </div>
          <div class="issue-title">${esc(issue.title)}</div>
          <div class="issue-detail">${esc(issue.detail)}</div>
        </div>`;
    }).join('');
  }

  const recsEl = document.getElementById('recommendations');
  if (!recommendations.length) {
    recsEl.innerHTML = '<div class="empty-state">Run more tasks to get recommendations</div>';
  } else {
    recsEl.innerHTML = recommendations.map(rec => `
      <div class="rec-item">
        <span class="rec-marker">&rsaquo;</span>
        <span>${esc(rec)}</span>
      </div>
    `).join('');
  }

  animateFadeUp('.issue-item', 100);
  animateFadeUp('.rec-item', 200);
}

function renderRadarChart(avgScores) {
  const ctx = document.getElementById('radar-chart').getContext('2d');
  const labels = ['Completeness', 'Confidence', 'Efficiency', 'Speed', 'Reliability'];
  const values = [avgScores.completeness, avgScores.confidence, avgScores.efficiency, avgScores.speed, avgScores.reliability];

  if (radarChart) radarChart.destroy();
  radarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        label: 'Average Score',
        data: values.map(v => v * 100),
        backgroundColor: chartTheme.accentFill,
        borderColor: chartTheme.accent,
        borderWidth: 2,
        pointBackgroundColor: chartTheme.accent,
        pointRadius: 4,
      }],
    },
    options: {
      scales: {
        r: {
          min: 0, max: 100,
          ticks: { stepSize: 25, color: chartTheme.muted, backdropColor: 'transparent' },
          grid: { color: chartTheme.grid },
          angleLines: { color: chartTheme.grid },
          pointLabels: { color: chartTheme.text, font: { family: chartTheme.font, size: 11 } },
        },
      },
      plugins: { legend: { display: false } },
    },
  });

  // Fade in chart cards
  animateFadeUp('.charts-row .chart-card', 150);
}

function renderTrendChart(history) {
  const ctx = document.getElementById('trend-chart').getContext('2d');
  const sorted = [...history].reverse();
  const labels = sorted.map((_, i) => `Run ${i + 1}`);

  if (trendChart) trendChart.destroy();
  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Overall',
          data: sorted.map(r => (r.score_overall * 100).toFixed(1)),
          borderColor: chartTheme.accent,
          backgroundColor: chartTheme.accentFill,
          fill: true,
          tension: 0.3,
          pointRadius: 3,
        },
        {
          label: 'Completeness',
          data: sorted.map(r => (r.score_completeness * 100).toFixed(1)),
          borderColor: chartTheme.success,
          borderDash: [4, 4],
          tension: 0.3,
          pointRadius: 2,
        },
        {
          label: 'Reliability',
          data: sorted.map(r => (r.score_reliability * 100).toFixed(1)),
          borderColor: chartTheme.danger,
          borderDash: [4, 4],
          tension: 0.3,
          pointRadius: 2,
        },
      ],
    },
    options: {
      scales: {
        y: { min: 0, max: 100, ticks: { color: chartTheme.muted }, grid: { color: chartTheme.grid } },
        x: { ticks: { color: chartTheme.muted }, grid: { display: false } },
      },
      plugins: {
        legend: { labels: { color: chartTheme.text, boxWidth: 12, font: { family: chartTheme.font, size: 11 } } },
      },
    },
  });
}

// ── Per-URL Performance ──
function populateUrlDropdown(urls) {
  const select = document.getElementById('url-select');
  const currentValue = select.value;
  select.innerHTML = '<option value="">Select a URL...</option>';
  urls.forEach(url => {
    const opt = document.createElement('option');
    opt.value = url;
    try { opt.textContent = new URL(url).hostname; } catch { opt.textContent = url; }
    select.appendChild(opt);
  });
  if (currentValue && urls.includes(currentValue)) {
    select.value = currentValue;
  }
}

document.getElementById('url-select').addEventListener('change', async e => {
  const url = e.target.value;
  const empty = document.getElementById('url-perf-empty');
  const content = document.getElementById('url-perf-content');

  if (!url) {
    content.classList.add('hidden');
    empty.textContent = 'Select a URL to view its score breakdown';
    empty.classList.remove('hidden');
    animate(empty, { opacity: [0, 1], duration: 300 });
    return;
  }

  const res = await fetch(`/api/performance?url=${encodeURIComponent(url)}`);
  const data = await res.json();

  if (!data.total_runs) {
    content.classList.add('hidden');
    empty.textContent = 'No runs found for this URL';
    empty.classList.remove('hidden');
    animate(empty, { opacity: [0, 1], duration: 300 });
    return;
  }

  empty.classList.add('hidden');
  content.classList.remove('hidden');
  renderUrlPerformance(data);
});

function renderUrlPerformance(data) {
  const ctx = document.getElementById('url-radar-chart').getContext('2d');
  const labels = ['Completeness', 'Confidence', 'Efficiency', 'Speed', 'Reliability'];
  const values = [data.avg_scores.completeness, data.avg_scores.confidence, data.avg_scores.efficiency, data.avg_scores.speed, data.avg_scores.reliability];

  if (urlRadarChart) urlRadarChart.destroy();
  urlRadarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        label: 'Score',
        data: values.map(v => v * 100),
        backgroundColor: chartTheme.accentFill,
        borderColor: chartTheme.accent,
        borderWidth: 2,
        pointBackgroundColor: chartTheme.accent,
        pointRadius: 4,
      }],
    },
    options: {
      scales: {
        r: {
          min: 0, max: 100,
          ticks: { stepSize: 25, color: chartTheme.muted, backdropColor: 'transparent' },
          grid: { color: chartTheme.grid },
          angleLines: { color: chartTheme.grid },
          pointLabels: { color: chartTheme.text, font: { family: chartTheme.font, size: 11 } },
        },
      },
      plugins: { legend: { display: false } },
    },
  });

  // Render run details
  const runsList = document.getElementById('url-runs-list');
  runsList.innerHTML = data.runs.map(r => {
    const score = r.score_overall || 0;
    const scoreClass = score >= 0.7 ? 'score-high' : score >= 0.4 ? 'score-mid' : 'score-low';
    const time = r.created_at ? new Date(r.created_at).toLocaleString() : '';
    const scores = {
      completeness: r.score_completeness,
      confidence: r.score_confidence,
      efficiency: r.score_efficiency,
      speed: r.score_speed,
      reliability: r.score_reliability,
      overall: r.score_overall,
    };
    return `
      <div class="url-run-detail">
        <div class="url-run-detail-header">
          <span class="result-task">${esc(r.task)}</span>
          <span class="score-pill ${scoreClass}">${(score * 100).toFixed(0)}%</span>
        </div>
        <div class="url-run-detail-meta">
          <span class="badge ${r.found ? 'badge-success' : 'badge-error'}">${r.found ? 'Found' : 'Failed'}</span>
          <span>${r.steps_taken} steps</span>
          <span>${r.duration_seconds.toFixed(1)}s</span>
          <span>${time}</span>
        </div>
        ${renderScoreBars(scores)}
        ${renderStepDetails(r.step_details)}
      </div>`;
  }).join('');

  // Animate everything in
  animate('#url-perf-content', { opacity: [0, 1], scale: [0.97, 1], duration: 350, ease: 'outQuad' });
  // Stagger run detail cards
  animateFadeUp('.url-run-detail', 200);
  setTimeout(() => {
    document.querySelectorAll('.url-run-detail').forEach(card => animateScoreBars(card));
  }, 400);
}

// ── History ──
let allHistory = [];

async function loadHistory() {
  const res = await fetch('/api/results?limit=200');
  allHistory = await res.json();
  applyHistoryFilter();
}

function applyHistoryFilter() {
  const query = document.getElementById('filter-url').value.trim().toLowerCase();
  if (!query) {
    renderHistory(allHistory);
    return;
  }
  const filtered = allHistory.filter(r =>
    r.url.toLowerCase().includes(query) || r.task.toLowerCase().includes(query)
  );
  renderHistory(filtered);
}

document.getElementById('filter-btn').addEventListener('click', applyHistoryFilter);

document.getElementById('filter-url').addEventListener('input', applyHistoryFilter);

document.getElementById('filter-url').addEventListener('keydown', e => {
  if (e.key === 'Enter') applyHistoryFilter();
});

function renderHistory(rows) {
  const tbody = document.getElementById('history-body');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-muted)">No results yet</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((r, i) => {
    const time = r.created_at ? new Date(r.created_at).toLocaleString() : '-';
    const host = (() => { try { return new URL(r.url).hostname; } catch { return r.url; } })();
    const score = r.score_overall || 0;
    const scoreClass = score >= 0.7 ? 'score-high' : score >= 0.4 ? 'score-mid' : 'score-low';
    const task = r.task.length > 50 ? r.task.slice(0, 50) + '...' : r.task;
    return `
      <tr data-result-id="${r.id}">
        <td style="white-space:nowrap">${time}</td>
        <td title="${esc(r.url)}">${esc(host)}</td>
        <td title="${esc(r.task)}">${esc(task)}</td>
        <td><span class="badge ${r.found ? 'badge-success' : 'badge-error'}">${r.found ? 'Found' : 'Failed'}</span></td>
        <td><span class="score-pill ${scoreClass}">${(score * 100).toFixed(0)}%</span></td>
        <td>${r.steps_taken}</td>
        <td>${r.duration_seconds.toFixed(1)}s</td>
        <td><button class="btn-secondary" onclick="showDetail(${i})">View</button></td>
        <td><button class="btn-icon btn-delete" onclick="deleteResult(${r.id}, this)" title="Delete">&times;</button></td>
      </tr>`;
  }).join('');

  // Staggered row fade-in
  animate('#history-body tr', {
    opacity: [0, 1],
    translateX: [-15, 0],
    duration: 350,
    delay: stagger(40),
    ease: 'outQuad',
  });
}

// ── Detail Modal ──
function showDetail(index) {
  const r = allHistory[index];
  if (!r) return;
  const scores = {
    completeness: r.score_completeness,
    confidence: r.score_confidence,
    efficiency: r.score_efficiency,
    speed: r.score_speed,
    reliability: r.score_reliability,
    overall: r.score_overall,
  };
  document.getElementById('modal-body').innerHTML = `
    <p><strong>URL:</strong> ${esc(r.url)}</p>
    <p><strong>Task:</strong> ${esc(r.task)}</p>
    <p><strong>Status:</strong> <span class="badge ${r.found ? 'badge-success' : 'badge-error'}">${r.found ? 'Found' : 'Not Found'}</span></p>
    ${r.answer ? `<p><strong>Answer:</strong></p><div class="result-answer">${esc(r.answer)}</div>` : ''}
    ${r.error ? `<p><strong>Error:</strong></p><div class="result-answer" style="color:var(--danger)">${esc(r.error)}</div>` : ''}
    <div class="result-meta" style="margin: 1rem 0">
      <span>Steps: ${r.steps_taken}</span>
      <span>Duration: ${r.duration_seconds.toFixed(1)}s</span>
      <span>Errors: ${r.errors_encountered}</span>
    </div>
    ${r.recording_path ? `
    <h3 style="margin-top:1rem">Recording</h3>
    <div class="recording-container">
      <video controls class="recording-video" preload="metadata">
        <source src="/media/${esc(r.recording_path)}" type="video/mp4">
        Your browser does not support video playback.
      </video>
    </div>` : ''}
    <h3 style="margin-top:1rem">Score Breakdown</h3>
    ${renderScoreBars(scores)}
    ${renderStepDetails(r.step_details)}
  `;

  const modal = document.getElementById('detail-modal');
  modal.classList.remove('hidden');

  // Animate modal entrance
  animate('.modal-backdrop', { opacity: [0, 1], duration: 250 });
  animate('.modal-content', {
    opacity: [0, 1],
    scale: [0.9, 1],
    duration: 350,
    ease: 'outBack',
  });

  // Animate score bars in modal
  setTimeout(() => animateScoreBars(document.getElementById('modal-body')), 250);
}

function closeModal() {
  animate('.modal-content', {
    opacity: [1, 0],
    scale: [1, 0.9],
    duration: 200,
    ease: 'inQuad',
  });
  animate('.modal-backdrop', {
    opacity: [1, 0],
    duration: 200,
    onComplete: () => document.getElementById('detail-modal').classList.add('hidden'),
  });
}

document.querySelector('.modal-close').addEventListener('click', closeModal);
document.querySelector('.modal-backdrop').addEventListener('click', closeModal);

// ── Page Load Animation ──
animate('nav', { opacity: [0, 1], translateY: [-10, 0], duration: 400, ease: 'outQuad' });
animate('#tab-run .card', {
  opacity: [0, 1],
  translateY: [20, 0],
  duration: 500,
  delay: stagger(100, { start: 150 }),
  ease: 'outExpo',
});

// ── Step Details ──
function renderStepDetails(steps) {
  if (!steps || !steps.length) return '';
  return `
    <div class="step-details-section">
      <button class="btn-secondary step-toggle" onclick="this.nextElementSibling.classList.toggle('hidden'); this.textContent = this.nextElementSibling.classList.contains('hidden') ? 'Show Steps (${steps.length})' : 'Hide Steps'">Show Steps (${steps.length})</button>
      <div class="step-details-list hidden">
        ${steps.map(s => `
          <div class="step-detail-card">
            <div class="step-detail-header">Step ${s.step}</div>
            ${s.screenshot ? `<div class="step-field"><span class="step-field-label">Screenshot</span><div class="step-screenshot-wrap"><img class="step-screenshot" src="/media/${esc(s.screenshot)}" alt="Step ${s.step} screenshot" loading="lazy" onclick="openScreenshot(this.src)"></div></div>` : ''}
            ${s.reasoning ? `<div class="step-field"><span class="step-field-label">Reasoning</span><div class="step-field-content">${esc(s.reasoning).substring(0, 500)}${s.reasoning.length > 500 ? '...' : ''}</div></div>` : ''}
            ${s.code ? `<div class="step-field"><span class="step-field-label">Code</span><pre class="step-code">${esc(s.code)}</pre></div>` : ''}
            ${s.observations ? `<div class="step-field"><span class="step-field-label">Observations</span><div class="step-field-content">${esc(s.observations)}</div></div>` : ''}
            ${s.error ? `<div class="step-field"><span class="step-field-label">Error</span><div class="step-field-content step-error">${esc(s.error)}</div></div>` : ''}
          </div>
        `).join('')}
      </div>
    </div>`;
}

function openScreenshot(src) {
  const overlay = document.createElement('div');
  overlay.className = 'screenshot-overlay';
  overlay.innerHTML = `<img src="${src}" alt="Screenshot full view">`;
  overlay.addEventListener('click', () => {
    animate(overlay, { opacity: [1, 0], duration: 200, onComplete: () => overlay.remove() });
  });
  document.body.appendChild(overlay);
  animate(overlay, { opacity: [0, 1], duration: 250 });
}

// ── Delete Records ──
async function deleteResult(id, btn) {
  if (!confirm('Delete this record?')) return;
  const row = btn.closest('tr');
  try {
    const res = await fetch(`/api/results/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.deleted) {
      animate(row, {
        opacity: [1, 0], translateX: [0, 30], duration: 250, ease: 'inQuad',
        onComplete: () => {
          allHistory = allHistory.filter(r => r.id !== id);
          applyHistoryFilter();
        },
      });
    }
  } catch { /* ignore */ }
}

document.getElementById('clear-all-btn').addEventListener('click', async () => {
  if (!confirm('Delete ALL history records? This cannot be undone.')) return;
  try {
    const res = await fetch('/api/results', { method: 'DELETE' });
    const data = await res.json();
    if (data.deleted) {
      allHistory = [];
      applyHistoryFilter();
    }
  } catch { /* ignore */ }
});

// ── Helpers ──
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
