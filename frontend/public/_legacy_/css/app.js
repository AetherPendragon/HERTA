/* === Herta Frontend Application === */

const API = '';

// === Navigation ===
document.querySelectorAll('.nav-links li').forEach(li => {
    li.addEventListener('click', () => {
        document.querySelectorAll('.nav-links li').forEach(l => l.classList.remove('active'));
        li.classList.add('active');
        const page = li.dataset.page;
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.getElementById(`page-${page}`).classList.add('active');
        document.getElementById('page-title').textContent = li.querySelector('.nav-label').textContent;
        loadPage(page);
    });
});

// === Clock ===
function updateClock() {
    const now = new Date();
    document.getElementById('topbar-time').textContent = now.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
}
setInterval(updateClock, 1000);
updateClock();

// === Toast ===
function toast(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.getElementById('toast-container').appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

// === Modal ===
function openModal(id) { document.getElementById(id).classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }

// === API Helpers ===
async function api(url, opts = {}) {
    try {
        const res = await fetch(API + url, {
            headers: { 'Content-Type': 'application/json' },
            ...opts,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        toast(`请求失败: ${e.message}`, 'error');
        throw e;
    }
}

// === Task Polling ===
async function pollTask(taskId, onProgress, onComplete) {
    const poll = async () => {
        const data = await api(`/api/settings/task/${taskId}`);
        if (!data.exists) { setTimeout(poll, 1000); return; }
        onProgress(data);
        if (data.status === 'completed') { onComplete(data); return; }
        if (data.status === 'failed') { toast(data.error || data.message, 'error'); return; }
        setTimeout(poll, 1000);
    };
    poll();
}

// === Page Loaders ===
let radarChart = null;

function loadPage(page) {
    switch (page) {
        case 'dashboard': loadDashboard(); break;
        case 'knowledge': loadKnowledge(); break;
        case 'generate': loadGenerate(); break;
        case 'compare': loadCompare(); break;
        case 'settings': loadSettings(); break;
    }
}

// --- Dashboard ---
async function loadDashboard() {
    const [kbRes, settingsRes] = await Promise.all([
        api('/api/kb/list').catch(() => ({ knowledge_bases: [] })),
        api('/api/settings').catch(() => ({})),
    ]);

    document.getElementById('dash-kb-count').textContent = kbRes.knowledge_bases?.length || 0;
    document.getElementById('dash-kb-sub').textContent = kbRes.knowledge_bases?.map(k => k.source).join(', ') || '无';

    document.getElementById('dash-model').textContent = settingsRes.chat_model || '-';
    document.getElementById('dash-embed-model').textContent = settingsRes.embedding_model || '-';
    document.getElementById('dash-embed-dim').textContent = settingsRes.embedding_dimensions || '-';
    document.getElementById('dash-api-key').textContent = settingsRes.api_key_preview || '未设置';

    // Try to load latest compare result
    try {
        const targets = await api('/api/generate/targets');
        for (const t of targets.targets || []) {
            try {
                const cmp = await api(`/api/compare/result/${t.name}`);
                if (cmp.exists && cmp.metrics) {
                    const m = cmp.metrics;
                    document.getElementById('dash-config-score').textContent = m.config_similarity?.toFixed(1) + '%';
                    document.getElementById('dash-handler-score').textContent = m.handler_similarity?.toFixed(1) + '%';
                    document.getElementById('dash-overall-score').textContent = m.overall_similarity?.toFixed(1) + '%';
                    renderRadar(m);
                    break;
                }
            } catch (_) {}
        }
    } catch (_) {}
}

function renderRadar(metrics) {
    document.getElementById('radar-empty').style.display = 'none';
    const ctx = document.getElementById('radar-chart').getContext('2d');
    if (radarChart) radarChart.destroy();

    radarChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['拓扑', '命令表', '遥测表', '内部处理', 'Config总分', 'Handler'],
            datasets: [{
                label: '相似度 (%)',
                data: [
                    metrics.topology_similarity || 0,
                    metrics.cmd_list_similarity || 0,
                    metrics.tele_handler_similarity || 0,
                    metrics.internal_handler_similarity || 0,
                    metrics.config_similarity || 0,
                    metrics.handler_similarity || 0,
                ],
                backgroundColor: 'rgba(0, 212, 170, 0.15)',
                borderColor: '#00d4aa',
                borderWidth: 2,
                pointBackgroundColor: '#00d4aa',
                pointRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { color: '#6e7681', backdropColor: 'transparent', font: { family: 'JetBrains Mono', size: 10 } },
                    grid: { color: '#30363d' },
                    angleLines: { color: '#30363d' },
                    pointLabels: { color: '#8b949e', font: { family: 'Noto Sans SC', size: 12 } },
                }
            },
            plugins: {
                legend: { display: false },
            }
        }
    });
}

// --- Knowledge Base ---
async function loadKnowledge() {
    const res = await api('/api/kb/list');
    const container = document.getElementById('kb-list');
    if (!res.knowledge_bases?.length) {
        container.innerHTML = '<div class="empty-state">暂无知识库，点击上方按钮构建</div>';
        return;
    }
    container.innerHTML = res.knowledge_bases.map(kb => `
        <div class="kb-item">
            <div class="kb-item-info">
                <h4>${kb.source}</h4>
                <div class="kb-item-meta">
                    <span>Chunks: ${kb.chunk_count}</span>
                    <span>策略: ${kb.chunk_strategy || '-'}</span>
                    <span>模型: ${kb.embedding_model || '-'}</span>
                </div>
            </div>
            <span class="kb-item-badge">${kb.has_index ? 'INDEX OK' : 'NO INDEX'}</span>
        </div>
    `).join('');
}

document.getElementById('btn-build-kb').addEventListener('click', () => openModal('build-dialog'));

document.getElementById('btn-build-confirm').addEventListener('click', async () => {
    const source = document.getElementById('build-source').value.trim();
    if (!source) { toast('请输入来源标识', 'warn'); return; }

    closeModal('build-dialog');
    toast('开始构建知识库...');

    const res = await api('/api/kb/build', {
        method: 'POST',
        body: JSON.stringify({
            source,
            chunk_strategy: document.getElementById('build-strategy').value,
            chunk_size: parseInt(document.getElementById('build-chunk-size').value),
            chunk_overlap: parseInt(document.getElementById('build-overlap').value),
        }),
    });

    pollTask(res.task_id,
        (d) => toast(`${d.message} (${d.progress}%)`),
        (d) => { toast('知识库构建完成!'); loadKnowledge(); }
    );
});

// --- Generate ---
let currentTarget = null;

async function loadGenerate() {
    const [targetsRes, kbRes] = await Promise.all([
        api('/api/generate/targets'),
        api('/api/kb/list'),
    ]);

    const tSel = document.getElementById('gen-target');
    tSel.innerHTML = '<option value="">-- 选择目标协议 --</option>' +
        (targetsRes.targets || []).map(t => `<option value="${t.name}">${t.name}</option>`).join('');

    const kSel = document.getElementById('gen-source-kb');
    kSel.innerHTML = '<option value="">-- 选择知识库 --</option>' +
        (kbRes.knowledge_bases || []).map(k => `<option value="${k.source}">${k.source}</option>`).join('');
}

document.getElementById('btn-gen-config').addEventListener('click', async () => {
    const target = document.getElementById('gen-target').value;
    if (!target) { toast('请先选择目标协议', 'warn'); return; }
    const source_kb = document.getElementById('gen-source-kb').value;

    const prog = document.getElementById('gen-progress');
    prog.classList.remove('hidden');
    document.getElementById('gen-progress-bar').style.width = '0%';
    document.getElementById('gen-progress-msg').textContent = '正在提交...';

    const res = await api('/api/generate/config', {
        method: 'POST',
        body: JSON.stringify({ target, source_kb, top_k: parseInt(document.getElementById('gen-topk').value) }),
    });

    pollTask(res.task_id,
        (d) => {
            document.getElementById('gen-progress-bar').style.width = d.progress + '%';
            document.getElementById('gen-progress-msg').textContent = d.message;
        },
        (d) => {
            document.getElementById('gen-progress-title').textContent = 'Config 生成完成!';
            document.getElementById('btn-gen-handler').disabled = false;
            toast('Config 生成完成');
            loadGenResult(target);
        }
    );
});

document.getElementById('btn-gen-handler').addEventListener('click', async () => {
    const target = document.getElementById('gen-target').value;
    const source_kb = document.getElementById('gen-source-kb').value;

    const prog = document.getElementById('gen-progress');
    prog.classList.remove('hidden');
    document.getElementById('gen-progress-title').textContent = '生成中...';
    document.getElementById('gen-progress-bar').style.width = '0%';
    document.getElementById('gen-progress-msg').textContent = '正在提交...';

    const res = await api('/api/generate/handler', {
        method: 'POST',
        body: JSON.stringify({ target, source_kb, top_k: parseInt(document.getElementById('gen-topk').value) }),
    });

    pollTask(res.task_id,
        (d) => {
            document.getElementById('gen-progress-bar').style.width = d.progress + '%';
            document.getElementById('gen-progress-msg').textContent = d.message;
        },
        (d) => {
            document.getElementById('gen-progress-title').textContent = 'Handler 生成完成!';
            toast('Handler 代码生成完成');
            loadGenResult(target);
        }
    );
});

async function loadGenResult(target) {
    const res = await api(`/api/generate/result/${target}`);
    if (!res.exists) return;

    const resultDiv = document.getElementById('gen-result');
    resultDiv.classList.remove('hidden');
    document.getElementById('gen-result-code').textContent = JSON.stringify(res.config || {}, null, 2);
}

document.getElementById('btn-view-config').addEventListener('click', async () => {
    const target = document.getElementById('gen-target').value;
    const res = await api(`/api/generate/result/${target}`);
    if (res.config) {
        document.getElementById('gen-result').classList.remove('hidden');
        document.getElementById('gen-result-code').textContent = JSON.stringify(res.config, null, 2);
    }
});

document.getElementById('btn-view-handler').addEventListener('click', async () => {
    const target = document.getElementById('gen-target').value;
    const res = await api(`/api/generate/result/${target}`);
    if (res.handler_source) {
        document.getElementById('gen-result').classList.remove('hidden');
        document.getElementById('gen-result-code').textContent = res.handler_source;
    }
});

// --- Compare ---
async function loadCompare() {
    const res = await api('/api/generate/targets');
    const sel = document.getElementById('cmp-target');
    sel.innerHTML = '<option value="">-- 选择目标协议 --</option>' +
        (res.targets || []).map(t => `<option value="${t.name}">${t.name}</option>`).join('');
}

document.getElementById('btn-run-compare').addEventListener('click', async () => {
    const target = document.getElementById('cmp-target').value;
    if (!target) { toast('请选择目标协议', 'warn'); return; }

    const prog = document.getElementById('cmp-progress');
    prog.classList.remove('hidden');
    document.getElementById('cmp-progress-bar').style.width = '0%';
    document.getElementById('cmp-progress-msg').textContent = '正在提交...';

    const res = await api('/api/compare/run', {
        method: 'POST',
        body: JSON.stringify({ target }),
    });

    pollTask(res.task_id,
        (d) => {
            document.getElementById('cmp-progress-bar').style.width = d.progress + '%';
            document.getElementById('cmp-progress-msg').textContent = d.message;
        },
        (d) => {
            prog.classList.add('hidden');
            toast('评测完成!');
            showCompareResult(d.result);
        }
    );
});

function showCompareResult(r) {
    if (!r) return;
    document.getElementById('cmp-results').classList.remove('hidden');

    document.getElementById('cmp-topology').textContent = r.topology_similarity + '%';
    document.getElementById('cmp-cmd').textContent = r.cmd_list_similarity + '%';
    document.getElementById('cmp-tele').textContent = r.tele_handler_similarity + '%';
    document.getElementById('cmp-internal').textContent = r.internal_handler_similarity + '%';
    document.getElementById('cmp-config').textContent = r.config_similarity + '%';

    document.getElementById('cmp-gt-count').textContent = r.gt_function_count;
    document.getElementById('cmp-gen-count').textContent = r.gen_function_count;
    document.getElementById('cmp-match-count').textContent = r.matched_count;
    document.getElementById('cmp-handler-score').textContent = r.handler_similarity + '%';
    document.getElementById('cmp-overall-score').textContent = r.overall_similarity + '%';

    // Function match table
    const tbody = document.querySelector('#cmp-func-table tbody');
    tbody.innerHTML = (r.function_matches || []).map(m => `
        <tr>
            <td>${m.gt_func_name}</td>
            <td>${m.gen_func_name || '-'}</td>
            <td>${m.is_name_match ? '<span class="accent-text">Y</span>' : 'N'}</td>
            <td>${m.is_matched ? (m.ast_similarity * 100).toFixed(1) + '%' : '-'}</td>
            <td>${m.is_matched ? (m.tree_edit_similarity * 100).toFixed(1) + '%' : '-'}</td>
            <td>${m.is_matched ? (m.semantic_feature_similarity * 100).toFixed(1) + '%' : '-'}</td>
            <td>${m.is_matched ? '<span class="accent-text">Matched</span>' : '-'}</td>
        </tr>
    `).join('');
}

// --- Settings ---
async function loadSettings() {
    const res = await api('/api/settings').catch(() => ({}));
    document.getElementById('set-api-key').value = '';
    document.getElementById('set-chat-model').value = res.chat_model || '';
    document.getElementById('set-embed-model').value = res.embedding_model || '';
}

document.getElementById('btn-save-settings').addEventListener('click', async () => {
    const body = {
        api_key: document.getElementById('set-api-key').value,
        chat_model: document.getElementById('set-chat-model').value,
        embedding_model: document.getElementById('set-embed-model').value,
    };
    await api('/api/settings', { method: 'POST', body: JSON.stringify(body) });
    toast('设置已保存');
});

// === Init ===
loadPage('dashboard');
