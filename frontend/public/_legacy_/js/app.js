/* === Herta Frontend Application === */

const API = '';

// === Global App State (persists across page switches) ===
const appState = {
    selectedTarget: '',
    selectedKB: '',
    runningTasks: {},  // taskId -> { type, target, onProgress, onComplete }
};

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

// === Format Helpers ===
function fmtPct(val) {
    if (val == null) return '-';
    return Number(val).toFixed(2) + '%';
}

const STRATEGY_LABELS = {
    direct: 'Direct（直接注入）',
    simple: 'Simple（固定大小）',
    semantic: 'Semantic（语义分块）',
    autosize: 'AutoSize（自动选优）',
    code_aware: 'Code Aware（代码感知）',
    proposition: 'Proposition（原子命题）',
};
function fmtStrategy(val) {
    return STRATEGY_LABELS[val] || val || '-';
}

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
        if (data.status === 'completed') { onComplete(data); delete appState.runningTasks[taskId]; return; }
        if (data.status === 'failed') { toast(data.error || data.message, 'error'); delete appState.runningTasks[taskId]; return; }
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

    // Load latest compare result
    try {
        const targets = await api('/api/generate/targets');
        for (const t of targets.targets || []) {
            try {
                const cmp = await api(`/api/compare/result/${t.name}`);
                if (cmp.exists && cmp.metrics) {
                    const m = cmp.metrics;
                    document.getElementById('dash-config-score').textContent = fmtPct(m.config_similarity);
                    document.getElementById('dash-handler-score').textContent = fmtPct(m.handler_similarity);
                    document.getElementById('dash-overall-score').textContent = fmtPct(m.overall_similarity);
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
        <div class="kb-item${appState.selectedKB === kb.source ? ' selected' : ''}">
            <div class="kb-item-info">
                <h4>${kb.source}</h4>
                <div class="kb-item-meta">
                    <span>Chunks: ${kb.chunk_count}</span>
                    <span>策略: ${fmtStrategy(kb.chunk_strategy)}</span>
                    <span>模型: ${kb.embedding_model || '-'}</span>
                </div>
            </div>
            <div class="kb-item-actions">
                ${appState.selectedKB === kb.source ? '<span class="kb-item-badge">当前选中</span>' : `<button class="btn sm" onclick="selectKB('${kb.source}')">选择使用</button>`}
            </div>
        </div>
    `).join('');
}

function selectKB(source) {
    appState.selectedKB = source;
    toast(`已选择知识库: ${source}，可前往代码生成页面使用`);
    loadKnowledge();
    // Sync generate page dropdown if already loaded
    const genKBSel = document.getElementById('gen-source-kb');
    if (genKBSel) genKBSel.value = source;
}

document.getElementById('btn-build-kb').addEventListener('click', () => openModal('build-dialog'));

document.getElementById('btn-build-confirm').addEventListener('click', async () => {
    const source = document.getElementById('build-source').value.trim();
    if (!source) { toast('请输入来源标识', 'warn'); return; }

    closeModal('build-dialog');
    toast('开始构建知识库...');

    const force = document.getElementById('build-force').checked;
    const res = await api('/api/kb/build', {
        method: 'POST',
        body: JSON.stringify({
            source,
            chunk_strategy: document.getElementById('build-strategy').value,
            chunk_size: parseInt(document.getElementById('build-chunk-size').value),
            chunk_overlap: parseInt(document.getElementById('build-overlap').value),
            force,
        }),
    });

    pollTask(res.task_id,
        (d) => toast(`${d.message} (${d.progress}%)`),
        (d) => {
            toast('知识库构建完成!');
            appState.selectedKB = source;
            loadKnowledge();
        }
    );
});

// --- Generate ---
async function loadGenerate() {
    const [targetsRes, kbRes] = await Promise.all([
        api('/api/generate/targets'),
        api('/api/kb/list'),
    ]);

    const tSel = document.getElementById('gen-target');
    const prevTarget = tSel.value || appState.selectedTarget;
    tSel.innerHTML = '<option value="">-- 选择目标协议 --</option>' +
        (targetsRes.targets || []).map(t => `<option value="${t.name}">${t.name}${t.has_gt_config ? ' (有参考)' : ''}</option>`).join('');
    // Restore previous selection
    if (prevTarget) tSel.value = prevTarget;

    const kSel = document.getElementById('gen-source-kb');
    const prevKB = kSel.value || appState.selectedKB;
    kSel.innerHTML = '<option value="">-- 选择知识库 --</option>' +
        (kbRes.knowledge_bases || []).map(k => `<option value="${k.source}">${k.source}</option>`).join('');
    if (prevKB) kSel.value = prevKB;

    // Sync appState from restored values
    appState.selectedTarget = tSel.value;
    appState.selectedKB = kSel.value;

    // Update workflow step indicators
    updateWorkflowSteps();

    // Auto-load previous result if target selected
    if (tSel.value) {
        loadGenResult(tSel.value);
    }
}

function updateWorkflowSteps() {
    const steps = document.querySelectorAll('.workflow-steps .step');
    const resultDiv = document.getElementById('gen-result');
    const hasResult = !resultDiv.classList.contains('hidden');

    steps.forEach(s => s.classList.remove('active', 'done'));
    if (appState.selectedTarget) {
        steps[0].classList.add('done');
        steps[1].classList.add('active');
    } else {
        steps[0].classList.add('active');
    }
    if (hasResult) {
        steps[1].classList.add('done');
        steps[2].classList.add('active');
    }
}

// Keep dropdowns synced to appState
document.getElementById('gen-target').addEventListener('change', function() {
    appState.selectedTarget = this.value;
    // Also update compare page
    const cmpSel = document.getElementById('cmp-target');
    if (cmpSel) cmpSel.value = this.value;
    updateWorkflowSteps();
    if (this.value) loadGenResult(this.value);
    else document.getElementById('gen-result').classList.add('hidden');
});

document.getElementById('gen-source-kb').addEventListener('change', function() {
    appState.selectedKB = this.value;
});

document.getElementById('btn-gen-config').addEventListener('click', async () => {
    const target = document.getElementById('gen-target').value;
    if (!target) { toast('请先选择目标协议', 'warn'); return; }
    const source_kb = document.getElementById('gen-source-kb').value;
    if (!source_kb) { toast('请先选择源知识库（在知识库页面构建并选择）', 'warn'); return; }

    const prog = document.getElementById('gen-progress');
    prog.classList.remove('hidden');
    document.getElementById('gen-progress-bar').style.width = '0%';
    document.getElementById('gen-progress-msg').textContent = '正在提交...';
    document.getElementById('gen-progress-title').textContent = '生成 Config 中...';

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
            updateWorkflowSteps();
            loadGenResult(target);
        }
    );
});

document.getElementById('btn-gen-handler').addEventListener('click', async () => {
    const target = document.getElementById('gen-target').value;
    const source_kb = document.getElementById('gen-source-kb').value;
    if (!source_kb) { toast('请先选择源知识库', 'warn'); return; }

    const prog = document.getElementById('gen-progress');
    prog.classList.remove('hidden');
    document.getElementById('gen-progress-title').textContent = '生成 Handler 中...';
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
            updateWorkflowSteps();
            loadGenResult(target);
        }
    );
});

async function loadGenResult(target) {
    const res = await api(`/api/generate/result/${target}`);
    if (!res.exists) return;

    const resultDiv = document.getElementById('gen-result');
    resultDiv.classList.remove('hidden');

    // Default show config
    if (res.config) {
        document.getElementById('gen-result-code').textContent = JSON.stringify(res.config, null, 2);
    } else if (res.handler_source) {
        document.getElementById('gen-result-code').textContent = res.handler_source;
    }

    // Enable handler button if config exists
    if (res.config) {
        document.getElementById('btn-gen-handler').disabled = false;
    }
}

document.getElementById('btn-view-config').addEventListener('click', async () => {
    const target = document.getElementById('gen-target').value;
    if (!target) return;
    const res = await api(`/api/generate/result/${target}`);
    if (res.config) {
        document.getElementById('gen-result').classList.remove('hidden');
        document.getElementById('gen-result-code').textContent = JSON.stringify(res.config, null, 2);
    } else {
        toast('尚未生成 Config', 'warn');
    }
});

document.getElementById('btn-view-handler').addEventListener('click', async () => {
    const target = document.getElementById('gen-target').value;
    if (!target) return;
    const res = await api(`/api/generate/result/${target}`);
    if (res.handler_source) {
        document.getElementById('gen-result').classList.remove('hidden');
        document.getElementById('gen-result-code').textContent = res.handler_source;
    } else {
        toast('尚未生成 Handler', 'warn');
    }
});

// --- Compare ---
async function loadCompare() {
    const res = await api('/api/generate/targets');
    const sel = document.getElementById('cmp-target');
    const prev = sel.value || appState.selectedTarget;
    sel.innerHTML = '<option value="">-- 选择目标协议 --</option>' +
        (res.targets || []).map(t => `<option value="${t.name}">${t.name}</option>`).join('');
    if (prev) sel.value = prev;

    // If target already selected, try loading existing compare result
    if (sel.value) {
        try {
            const cmp = await api(`/api/compare/result/${sel.value}`);
            if (cmp.exists && cmp.metrics) {
                showCompareResultFromMetrics(cmp.metrics);
            }
        } catch (_) {}
    }
}

document.getElementById('cmp-target').addEventListener('change', function() {
    appState.selectedTarget = this.value;
    // Sync generate page
    const genSel = document.getElementById('gen-target');
    if (genSel) genSel.value = this.value;
});

document.getElementById('btn-run-compare').addEventListener('click', async () => {
    const target = document.getElementById('cmp-target').value;
    if (!target) { toast('请选择目标协议', 'warn'); return; }

    // Check if generated results exist
    const genRes = await api(`/api/generate/result/${target}`);
    if (!genRes.exists || (!genRes.config && !genRes.handler_source)) {
        toast('请先在"代码生成"页面生成 Config 和 Handler，再运行评测', 'warn');
        return;
    }

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

    document.getElementById('cmp-topology').textContent = fmtPct(r.topology_similarity);
    document.getElementById('cmp-cmd').textContent = fmtPct(r.cmd_list_similarity);
    document.getElementById('cmp-tele').textContent = fmtPct(r.tele_handler_similarity);
    document.getElementById('cmp-internal').textContent = fmtPct(r.internal_handler_similarity);
    document.getElementById('cmp-config').textContent = fmtPct(r.config_similarity);

    document.getElementById('cmp-gt-count').textContent = r.gt_function_count;
    document.getElementById('cmp-gen-count').textContent = r.gen_function_count;
    document.getElementById('cmp-match-count').textContent = r.matched_count;
    document.getElementById('cmp-handler-score').textContent = fmtPct(r.handler_similarity);
    document.getElementById('cmp-handler-score-card').textContent = fmtPct(r.handler_similarity);
    document.getElementById('cmp-overall-score').textContent = fmtPct(r.overall_similarity);

    // Function match table
    const tbody = document.querySelector('#cmp-func-table tbody');
    tbody.innerHTML = (r.function_matches || []).map(m => `
        <tr>
            <td>${m.gt_func_name}</td>
            <td>${m.gen_func_name || '-'}</td>
            <td>${m.is_name_match ? '<span class="accent-text">Y</span>' : 'N'}</td>
            <td>${m.is_matched ? (m.ast_similarity * 100).toFixed(2) + '%' : '-'}</td>
            <td>${m.is_matched ? (m.tree_edit_similarity * 100).toFixed(2) + '%' : '-'}</td>
            <td>${m.is_matched ? (m.semantic_feature_similarity * 100).toFixed(2) + '%' : '-'}</td>
            <td>${m.is_matched ? '<span class="accent-text">Matched</span>' : '-'}</td>
        </tr>
    `).join('');

    // Load config comparison detail
    loadConfigDetail();
}

async function loadConfigDetail() {
    const target = document.getElementById('cmp-target').value;
    if (!target) return;

    const detailDiv = document.getElementById('cmp-config-detail');
    detailDiv.innerHTML = '<div class="empty-state">加载中...</div>';

    try {
        const [genRes, gtRes] = await Promise.all([
            api(`/api/generate/result/${target}`).catch(() => ({ exists: false })),
            api(`/api/compare/gt-config/${target}`).catch(() => ({ exists: false })),
        ]);

        const genConfig = genRes.config || null;
        const gtConfig = gtRes.config || null;

        if (!genConfig && !gtConfig) {
            detailDiv.innerHTML = '<div class="empty-state">无配置数据可对比</div>';
            return;
        }

        // Build side-by-side config comparison
        const summary = buildConfigComparisonSummary(genConfig, gtConfig);
        detailDiv.innerHTML = summary;

        // Make the config blocks collapsible
        detailDiv.querySelectorAll('.cmp-section-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const body = btn.nextElementSibling;
                body.classList.toggle('collapsed');
                btn.querySelector('.toggle-arrow').textContent = body.classList.contains('collapsed') ? '▶' : '▼';
            });
        });
    } catch (e) {
        detailDiv.innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

function buildConfigComparisonSummary(genConfig, gtConfig) {
    if (!genConfig || !gtConfig) {
        const side = genConfig ? '生成' : '真实';
        return `<div class="empty-state">${side}配置不可用</div>`;
    }

    const sections = [];
    const fields = [
        { key: 'version', label: '版本' },
        { key: 'author', label: '作者' },
        { key: 'start_index', label: '起始索引' },
    ];

    // Basic fields
    let basicHtml = '<table class="data-table"><thead><tr><th>字段</th><th>生成值</th><th>真实值</th></tr></thead><tbody>';
    for (const f of fields) {
        const gv = genConfig[f.key] ?? '-';
        const tv = gtConfig[f.key] ?? '-';
        const match = String(gv) === String(tv);
        basicHtml += `<tr><td>${f.label}</td><td${match ? '' : ' style="color:var(--accent-warn)"'}>${gv}</td><td>${tv}</td></tr>`;
    }
    basicHtml += '</tbody></table>';
    sections.push({ label: '基本字段', html: basicHtml });

    // Array fields comparison
    const arrayFields = [
        { key: 'cmd_list', label: '命令列表 (cmd_list)' },
        { key: 'tele_handler', label: '遥测处理 (tele_handler)' },
        { key: 'internal_handler', label: '内部处理 (internal_handler)' },
    ];

    for (const af of arrayFields) {
        const genArr = genConfig[af.key] || [];
        const gtArr = gtConfig[af.key] || [];
        const maxLen = Math.max(genArr.length, gtArr.length);

        if (maxLen === 0) continue;

        let arrHtml = `<div class="cmp-count-row"><span>生成: ${genArr.length} 项</span><span>真实: ${gtArr.length} 项</span></div>`;

        if (af.key === 'cmd_list') {
            arrHtml += '<table class="data-table"><thead><tr><th>#</th><th>生成 desc</th><th>生成 cmd</th><th>生成 handler</th><th>真实 desc</th><th>真实 cmd</th><th>真实 handler</th></tr></thead><tbody>';
            for (let i = 0; i < maxLen; i++) {
                const g = genArr[i] || {};
                const t = gtArr[i] || {};
                const cmdMatch = String(g.cmd) === String(t.cmd);
                arrHtml += `<tr><td>${i}</td><td>${g.desc || '-'}</td><td${cmdMatch ? '' : ' style="color:var(--accent-warn)"'}>${g.cmd ?? '-'}</td><td>${g.handler || '-'}</td><td>${t.desc || '-'}</td><td>${t.cmd ?? '-'}</td><td>${t.handler || '-'}</td></tr>`;
            }
            arrHtml += '</tbody></table>';
        } else {
            arrHtml += '<table class="data-table"><thead><tr><th>#</th><th>生成 desc</th><th>生成 len</th><th>生成 handler</th><th>真实 desc</th><th>真实 len</th><th>真实 handler</th></tr></thead><tbody>';
            for (let i = 0; i < maxLen; i++) {
                const g = genArr[i] || {};
                const t = gtArr[i] || {};
                const lenMatch = String(g.len) === String(t.len);
                arrHtml += `<tr><td>${i}</td><td>${g.desc || '-'}</td><td${lenMatch ? '' : ' style="color:var(--accent-warn)"'}>${g.len ?? '-'}</td><td>${g.handler || '-'}</td><td>${t.desc || '-'}</td><td>${t.len ?? '-'}</td><td>${t.handler || '-'}</td></tr>`;
            }
            arrHtml += '</tbody></table>';
        }
        sections.push({ label: af.label, html: arrHtml });
    }

    return sections.map((s, idx) => `
        <div class="cmp-section">
            <button class="cmp-section-toggle"><span class="toggle-arrow">${idx === 0 ? '▼' : '▶'}</span> ${s.label}</button>
            <div class="cmp-section-body${idx === 0 ? '' : ' collapsed'}">${s.html}</div>
        </div>
    `).join('');
}

function showCompareResultFromMetrics(m) {
    showCompareResult({
        topology_similarity: m.topology_similarity,
        cmd_list_similarity: m.cmd_list_similarity,
        tele_handler_similarity: m.tele_handler_similarity,
        internal_handler_similarity: m.internal_handler_similarity,
        config_similarity: m.config_similarity,
        gt_function_count: m.gt_function_count || '-',
        gen_function_count: m.gen_function_count || '-',
        matched_count: m.matched_count || '-',
        handler_similarity: m.handler_similarity,
        overall_similarity: m.overall_similarity,
        function_matches: m.function_matches || [],
    });
}

// --- Settings ---
async function loadSettings() {
    const res = await api('/api/settings').catch(() => ({}));

    const keyInput = document.getElementById('set-api-key');
    const keyStatus = document.getElementById('set-api-key-status');

    if (res.api_key_set) {
        keyInput.placeholder = `已设置 (${res.api_key_preview})，留空则不修改`;
        keyInput.value = '';
        if (keyStatus) keyStatus.textContent = 'API Key 已通过环境变量或上次保存设置';
    } else {
        keyInput.placeholder = '输入你的 ZAI API Key（必填）';
        if (keyStatus) keyStatus.textContent = '尚未设置 API Key，代码生成功能将不可用';
    }

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
    toast('设置已保存（当前会话有效，重启服务器后需重新设置或使用环境变量）');
    loadSettings();
});

// === Init ===
loadPage('dashboard');
