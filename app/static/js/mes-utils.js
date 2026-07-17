/**
 * MES Industrial - Shared Gantt & Date Range Utilities
 * Provides: dateRangeBar(), applyGanttZoom(), normDateRange()
 */

// ─── Date helpers ────────────────────────────────────────────────────────────
window.MES = window.MES || {};

MES.todayRange = function() {
    const d = new Date();
    const s = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0);
    const e = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);
    return { s, e };
};

MES.weekRange = function() {
    const d = new Date();
    // Monday=0 offset
    const day = d.getDay() === 0 ? 6 : d.getDay() - 1; // 0=Mon ... 6=Sun
    const s = new Date(d.getFullYear(), d.getMonth(), d.getDate() - day, 0, 0, 0, 0);
    const e = new Date(s.getFullYear(), s.getMonth(), s.getDate() + 6, 23, 59, 59, 999);
    return { s, e };
};

MES.monthRange = function() {
    const d = new Date();
    const s = new Date(d.getFullYear(), d.getMonth(), 1, 0, 0, 0, 0);
    const e = new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59, 999);
    return { s, e };
};

MES.fmtDate = function(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
};

// ─── Gantt zoom dispatcher (works even before data is loaded) ─────────────────
MES.applyGanttZoom = function(chart, range) {
    if (!chart) return;
    let r;
    if (range === 'today') r = MES.todayRange();
    else if (range === 'week')  r = MES.weekRange();
    else if (range === 'month') r = MES.monthRange();
    else {
        // 'all' — reset to full range using percentage
        chart.dispatchAction({ type: 'dataZoom', dataZoomIndex: 0, start: 0, end: 100 });
        return;
    }
    chart.dispatchAction({
        type: 'dataZoom',
        dataZoomIndex: 0,
        startValue: r.s.getTime(),
        endValue:   r.e.getTime()
    });
};

// ─── Date-range filter bar builder ───────────────────────────────────────────
// opts: { container, onApply, defaultRange='week', showPresets=true }
MES.buildDateBar = function(opts) {
    const { container, onApply, defaultRange = 'week', showPresets = true } = opts;
    if (!container) return;

    const presets = [
        { key: 'today', label: 'Hoy' },
        { key: 'week',  label: 'Semana' },
        { key: 'month', label: 'Mes' }
    ];

    container.innerHTML = `
        <div class="flex flex-wrap gap-2 items-end">
            ${showPresets ? `<div class="flex flex-col gap-1">
                <label class="text-[10px] font-bold uppercase" style="color:var(--text-muted)">Rango Rápido</label>
                <div class="inline-flex rounded-lg overflow-hidden" style="border:1px solid var(--border-color)">
                    ${presets.map((p, i) => `
                        <button id="mes-preset-${p.key}" onclick="MES._applyPreset('${p.key}')"
                            class="px-3 py-1.5 text-xs font-semibold transition-colors mes-preset-btn"
                            style="${i > 0 ? 'border-left:1px solid var(--border-color)' : ''}">
                            ${p.label}
                        </button>`).join('')}
                </div>
            </div>` : ''}
            <div class="flex flex-col gap-1">
                <label class="text-[10px] font-bold uppercase" style="color:var(--text-muted)">Desde</label>
                <input type="date" id="mes-date-start"
                    class="rounded-lg px-3 py-1.5 text-xs focus:ring-2 focus:ring-brand-500 outline-none"
                    style="background:var(--bg-surface);color:var(--text-primary);border:1px solid var(--border-color)">
            </div>
            <div class="flex flex-col gap-1">
                <label class="text-[10px] font-bold uppercase" style="color:var(--text-muted)">Hasta</label>
                <input type="date" id="mes-date-end"
                    class="rounded-lg px-3 py-1.5 text-xs focus:ring-2 focus:ring-brand-500 outline-none"
                    style="background:var(--bg-surface);color:var(--text-primary);border:1px solid var(--border-color)">
            </div>
            <button onclick="MES._applyManual()" class="px-3 py-1.5 text-xs font-semibold rounded-lg flex items-center gap-1 transition-colors"
                style="background:var(--accent-color);color:#fff">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
                </svg>
                Buscar
            </button>
        </div>`;

    // Style for active preset
    const style = document.createElement('style');
    style.textContent = `.mes-preset-btn{background:transparent;color:var(--text-primary)} .mes-preset-btn.active{background:rgba(59,130,246,.15);color:#3b82f6}`;
    document.head.appendChild(style);

    MES._dateBarCallback = onApply;

    // Apply default preset
    MES._applyPreset(defaultRange);
};

MES._applyPreset = function(key) {
    // Mark active button
    document.querySelectorAll('.mes-preset-btn').forEach(b => b.classList.remove('active'));
    const btn = document.getElementById(`mes-preset-${key}`);
    if (btn) btn.classList.add('active');

    let r;
    if (key === 'today') r = MES.todayRange();
    else if (key === 'week')  r = MES.weekRange();
    else if (key === 'month') r = MES.monthRange();
    else return;

    const si = document.getElementById('mes-date-start');
    const ei = document.getElementById('mes-date-end');
    if (si) si.value = MES.fmtDate(r.s);
    if (ei) ei.value = MES.fmtDate(r.e);

    if (MES._dateBarCallback) MES._dateBarCallback(r.s, r.e, key);
};

MES._applyManual = function() {
    document.querySelectorAll('.mes-preset-btn').forEach(b => b.classList.remove('active'));
    const s = new Date(document.getElementById('mes-date-start').value + 'T00:00:00');
    const e = new Date(document.getElementById('mes-date-end').value + 'T23:59:59');
    if (!isNaN(s) && !isNaN(e) && MES._dateBarCallback) {
        MES._dateBarCallback(s, e, 'custom');
    }
};

// ─── Product Color Sync (Consistent coloring across charts) ────────────────
MES.getProductColor = function(productCode, isDark) {
    const paletteLight = [
        '#bfdbfe', // Pastel Blue
        '#fecaca', // Pastel Red
        '#bbf7d0', // Pastel Green
        '#fde68a', // Pastel Amber
        '#e9d5ff', // Pastel Purple
        '#a5f3fc', // Pastel Cyan
        '#fbcfe8', // Pastel Pink
        '#fed7aa'  // Pastel Orange
    ];
    const paletteDark = [
        '#2563eb', // Blue
        '#dc2626', // Red
        '#16a34a', // Green
        '#d97706', // Amber
        '#7c3aed', // Purple
        '#0891b2', // Cyan
        '#db2777', // Pink
        '#ea580c'  // Orange
    ];
    
    let hash = 0;
    const str = productCode || 'UNKNOWN';
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % paletteLight.length;
    
    return isDark ? paletteDark[index] : paletteLight[index];
};

