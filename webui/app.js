﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿﻿const AppState = {
    currentStep: 1,
    questionRegion: { selected: false },
    numberRegion: { selected: false },
    numberCoordsCount: 0,
    collectedQuestions: 0,
    parsedAnswers: 0,
    mode: 'test',
    questions: [],
    answers: [],
    logs: [],
    maxLogs: 100,
    operationProgress: {
        detect: { current: -1, total: -1, message: '', phase: '' },
        parse: { current: -1, total: -1, message: '', phase: '' },
        collect: { current: -1, total: -1, message: '', phase: '' },
        execute: { current: -1, total: -1, message: '', phase: '' }
    }
};

function updateState(newState) {
    Object.assign(AppState, newState);
    renderState();
}

function renderState() {
    document.getElementById('stateQuestionRegion').textContent = AppState.questionRegion.selected ? '已选择' : '未选择';
    document.getElementById('stateQuestionRegion').className = AppState.questionRegion.selected ? 'status-value status-success' : 'status-value';
    
    document.getElementById('stateNumberRegion').textContent = AppState.numberRegion.selected ? '已选择' : '未选择';
    document.getElementById('stateNumberRegion').className = AppState.numberRegion.selected ? 'status-value status-success' : 'status-value';
    
    document.getElementById('stateNumberCoords').textContent = `${AppState.numberCoordsCount} 个`;
    document.getElementById('stateCollectedQuestions').textContent = `${AppState.collectedQuestions} 个`;
    document.getElementById('stateParsedAnswers').textContent = `${AppState.parsedAnswers} 个`;
    document.getElementById('stateMode').textContent = AppState.mode;
}

function addLog(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = {
        time: timestamp,
        message: message,
        type: type
    };
    
    AppState.logs.push(logEntry);
    if (AppState.logs.length > AppState.maxLogs) {
        AppState.logs.shift();
    }
    
    renderLogs();
}

function renderLogs() {
    const miniLog = document.getElementById('miniLog');
    if (!miniLog) return;
    
    miniLog.innerHTML = '';
    
    if (AppState.logs.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'log-line log-empty';
        empty.textContent = '等待操作...';
        miniLog.appendChild(empty);
        return;
    }
    
    AppState.logs.forEach(log => {
        const line = document.createElement('div');
        line.className = `log-line ${log.type}`;
        line.textContent = `[${log.time}] ${log.message}`;
        miniLog.appendChild(line);
    });
    
    miniLog.scrollTop = miniLog.scrollHeight;
}

function updateProgressBar(sectionId, fillId, textId, current, total, label = '') {
    const section = document.getElementById(sectionId);
    const fill = document.getElementById(fillId);
    const text = document.getElementById(textId);
    if (section) {
        section.style.display = 'block';
    }
    const safeTotal = Math.max(0, Number(total) || 0);
    const safeCurrent = Math.max(0, Number(current) || 0);
    const percent = safeTotal > 0 ? Math.min(100, (safeCurrent / safeTotal) * 100) : 0;
    if (fill) {
        fill.style.width = `${percent}%`;
    }
    if (text) {
        text.textContent = label ? `${label} ${safeCurrent} / ${safeTotal}` : `${safeCurrent} / ${safeTotal}`;
    }
}

function hideProgressBar(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.style.display = 'none';
    }
}

function trackOperationProgress(kind, payload) {
    const current = Number(payload?.current || 0);
    const total = Number(payload?.total || 0);
    const message = payload?.message || '';
    const phase = payload?.phase || '';
    const cache = AppState.operationProgress[kind] || { current: -1, total: -1 };

    if (cache.current !== current || cache.total !== total || cache.message !== message || cache.phase !== phase) {
        AppState.operationProgress[kind] = { current, total, message, phase };
        if (message) {
            addLog(message, phase === 'error' ? 'error' : (phase === 'done' ? 'success' : 'info'));
        }
    }
}

function startPollingOperation(kind, sectionId, fillId, textId, fetchStatus, stopWhenDone = true) {
    let lastCurrent = -1;
    let lastTotal = -1;
    const timer = setInterval(async () => {
        try {
            const status = await fetchStatus();
            if (!status || !status.success) {
                return;
            }

            const current = Number(status.current || 0);
            const total = Number(status.total || 0);
            lastCurrent = current;
            lastTotal = total;
            updateProgressBar(sectionId, fillId, textId, current, total, status.message || '');
            trackOperationProgress(kind, status);

            if (stopWhenDone && status.running === false) {
                clearInterval(timer);
                const doneCurrent = total > 0 ? total : lastCurrent;
                const doneTotal = total > 0 ? total : lastTotal;
                updateProgressBar(sectionId, fillId, textId, doneCurrent, doneTotal, status.message || '');
                setTimeout(() => hideProgressBar(sectionId), 300);
            }
        } catch (error) {
            console.error(`${kind} progress polling failed:`, error);
        }
    }, 300);

    return timer;
}

function navigateToStep(stepNum) {
    addLog(`切换到步骤 ${stepNum}`, 'info');
    
    AppState.currentStep = stepNum;
    
    document.querySelectorAll('.nav-step').forEach(step => {
        const s = parseInt(step.dataset.step);
        step.classList.toggle('active', s === stepNum);
    });
    
    document.querySelectorAll('.step-content').forEach(content => {
        const s = parseInt(content.dataset.step);
        content.style.display = s === stepNum ? 'block' : 'none';
    });
    
    renderState();
}

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initEventListeners();
    addLog('应用已启动', 'info');
    renderState();
});

function initNavigation() {
    document.querySelectorAll('.nav-step').forEach(step => {
        step.addEventListener('click', () => {
            const stepNum = parseInt(step.dataset.step);
            navigateToStep(stepNum);
        });
    });
}

function initEventListeners() {
    document.getElementById('btnCaptureOCR')?.addEventListener('click', captureOCR);
    document.getElementById('btnFixedRegionOCR')?.addEventListener('click', fixedRegionOCR);
    document.getElementById('btnAdvancedSettings')?.addEventListener('click', toggleAdvancedSettings);
    document.getElementById('btnCloseAdvanced')?.addEventListener('click', toggleAdvancedSettings);
    document.getElementById('btnCopyScreenshot')?.addEventListener('click', copyScreenshot);
    document.getElementById('btnCopyResult')?.addEventListener('click', copyOCRResult);
    document.getElementById('btnClearResult')?.addEventListener('click', clearOCRResult);
    
    document.getElementById('btnSelectQuestionRegion')?.addEventListener('click', selectQuestionRegion);
    document.getElementById('btnSelectNumberRegion')?.addEventListener('click', selectNumberRegion);
    document.getElementById('btnSaveNumberCapture')?.addEventListener('click', saveNumberCapture);
    document.getElementById('btnDetectQuestions')?.addEventListener('click', detectQuestionPoints);
    document.getElementById('btnManualEditPoint')?.addEventListener('click', openPointModal);
    document.getElementById('btnInferPoints')?.addEventListener('click', triggerInferMissingPoints);
    document.getElementById('btnStartCollection')?.addEventListener('click', startCollection);
    document.getElementById('btnStopCollection')?.addEventListener('click', stopCollection);
    document.getElementById('btnParseOptions')?.addEventListener('click', parseCollectedOptions);
    document.getElementById('btnCollectQuestions')?.addEventListener('click', collectQuestions);
    document.getElementById('btnExportQuestions')?.addEventListener('click', exportCollectedQuestions);
    document.getElementById('btnGetAIPrompt')?.addEventListener('click', getAIPrompt);
    
    document.getElementById('btnParseAnswers')?.addEventListener('click', parseAnswers);
    document.getElementById('btnClearAnswers')?.addEventListener('click', clearAnswers);
    
    document.getElementById('btnExecuteAll')?.addEventListener('click', executeAllAnswers);
    document.getElementById('btnStopExecution')?.addEventListener('click', stopExecution);
    
    initAnswerList();
    
    document.getElementById('executeMode')?.addEventListener('change', (e) => {
        AppState.mode = e.target.value;
        renderState();
        addLog(`切换到${e.target.value}模式`, 'info');
    });
}

function initAnswerList() {
    const container = document.getElementById('answerList');
    if (!container) return;
    
    container.innerHTML = '';
    
    // 根据实际采集的题目数量动态生成
    const questions = AppState.questions || [];
    if (questions.length === 0) {
        container.innerHTML = '<div class="empty-text">请先采集题目</div>';
        return;
    }
    
    for (let i = 1; i <= questions.length; i++) {
        const q = questions[i-1];
        const displayNo = q.display_no || String(i);
        const qtype = q.type || 'single';
        
        const row = document.createElement('div');
        row.className = 'answer-row';
        row.innerHTML = `
            <span class="answer-no">${displayNo}</span>
            <input type="text" class="answer-input" data-no="${i}" data-type="${qtype}" placeholder="输入答案 (如 A, BC, 正确)" />
        `;
        container.appendChild(row);
    }
}

let CaptureState = {
    mode: 'single_ocr',
    isSelecting: false,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0,
    screenInfo: null,
    selection: null
};

function showCaptureOverlay(imagePath, screenInfo, mode) {
    CaptureState.mode = mode;
    CaptureState.screenInfo = screenInfo;
    CaptureState.selection = null;
    
    const overlay = document.getElementById('captureOverlay');
    const img = document.getElementById('captureImage');
    const selectionBox = document.getElementById('selectionBox');
    
    img.src = imagePath;
    selectionBox.style.display = 'none';
    overlay.style.display = 'flex';
    
    img.onload = function() {
        CaptureState.imgNaturalWidth = img.naturalWidth;
        CaptureState.imgNaturalHeight = img.naturalHeight;
    };
}

function hideCaptureOverlay() {
    const overlay = document.getElementById('captureOverlay');
    overlay.style.display = 'none';
    CaptureState.selection = null;
    CaptureState.screenInfo = null;
}

async function startScreenCapture(mode) {
    addLog('开始截图...', 'info');
    
    try {
        const result = await window.pywebview.api.begin_screen_capture(mode);
        
        if (result.success) {
            showCaptureOverlay(result.image_path, result.screen, mode);
            addLog('截图已获取，请在图上拖拽选择区域', 'info');
        } else {
            addLog(`截图失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`截图异常: ${e.message}`, 'error');
    }
}

function cancelCapture() {
    hideCaptureOverlay();
    addLog('已取消截图', 'warning');
}

async function confirmCapture() {
    const selectionBox = document.getElementById('selectionBox');
    const img = document.getElementById('captureImage');
    
    if (!CaptureState.selection) {
        addLog('请先选择区域', 'warning');
        return;
    }
    
    const rect = {
        x: CaptureState.selection.x,
        y: CaptureState.selection.y,
        width: CaptureState.selection.width,
        height: CaptureState.selection.height,
        display_width: img.clientWidth,
        display_height: img.clientHeight,
        natural_width: img.naturalWidth,
        natural_height: img.naturalHeight,
        screen_left: CaptureState.screenInfo.left,
        screen_top: CaptureState.screenInfo.top
    };
    
    addLog('确认区域...', 'info');
    
    try {
        const selectResult = await window.pywebview.api.finish_region_select(CaptureState.mode, rect);
        
        if (!selectResult.success) {
            addLog(`区域选择失败: ${selectResult.error}`, 'error');
            hideCaptureOverlay();
            return;
        }
        
        hideCaptureOverlay();
        
        if (CaptureState.mode === 'single_ocr') {
            const backend = document.getElementById('ocrBackend')?.value || 'auto';
            const ocrResult = await window.pywebview.api.capture_ocr_from_selected_region(selectResult.region, backend);
            
            if (ocrResult.success) {
                document.getElementById('ocrResultText').value = ocrResult.text || '';
                
                AppState.questionRegion = {
                    selected: true,
                    x: ocrResult.region.left,
                    y: ocrResult.region.top,
                    width: ocrResult.region.width,
                    height: ocrResult.region.height
                };
                const statusEl = document.getElementById('questionRegionStatus');
                if (statusEl) {
                    statusEl.textContent = `(${ocrResult.region.left}, ${ocrResult.region.top}) - ${ocrResult.region.width}x${ocrResult.region.height}`;
                    statusEl.classList.add('status-success');
                }
                
                addLog(`OCR识别完成 (${ocrResult.backend || backend}), 耗时: ${ocrResult.elapsed}s`, 'success');
            } else {
                addLog(`OCR识别失败: ${ocrResult.error}`, 'error');
            }
        } else if (CaptureState.mode === 'question_region') {
            AppState.questionRegion = {
                selected: true,
                ...selectResult.region
            };
            document.getElementById('questionRegionStatus').textContent = 
                `(${selectResult.region.left}, ${selectResult.region.top}) - ${selectResult.region.width}x${selectResult.region.height}`;
            document.getElementById('questionRegionStatus').classList.add('status-success');
            addLog(`题目区域已选择: ${selectResult.region.width}x${selectResult.region.height}`, 'success');
            renderState();
        } else if (CaptureState.mode === 'number_region') {
            AppState.numberRegion = {
                selected: true,
                ...selectResult.region
            };
            document.getElementById('numberRegionStatus').textContent = 
                `(${selectResult.region.left}, ${selectResult.region.top}) - ${selectResult.region.width}x${selectResult.region.height}`;
            document.getElementById('numberRegionStatus').classList.add('status-success');
            addLog(`题号区域已选择: ${selectResult.region.width}x${selectResult.region.height}`, 'success');
            renderState();
        }
    } catch (e) {
        addLog(`处理异常: ${e.message}`, 'error');
    }
}

function initCaptureInteraction() {
    const viewport = document.getElementById('captureViewport');
    const selectionBox = document.getElementById('selectionBox');
    const img = document.getElementById('captureImage');
    
    if (!viewport || !selectionBox || !img) return;
    
    let isDragging = false;
    let dragHandle = null;
    
    function getImgCoords(e) {
        const rect = img.getBoundingClientRect();
        return {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    }
    
    function updateSelectionBox() {
        if (!CaptureState.selection) return;
        
        const imgRect = img.getBoundingClientRect();
        const scaleX = imgRect.width / img.naturalWidth;
        const scaleY = imgRect.height / img.naturalHeight;
        
        selectionBox.style.left = (CaptureState.selection.x * scaleX) + 'px';
        selectionBox.style.top = (CaptureState.selection.y * scaleY) + 'px';
        selectionBox.style.width = (CaptureState.selection.width * scaleX) + 'px';
        selectionBox.style.height = (CaptureState.selection.height * scaleY) + 'px';
    }
    
    viewport.addEventListener('mousedown', function(e) {
        if (e.target.classList.contains('selection-handle')) {
            isDragging = true;
            dragHandle = e.target.className.split(' ')[1];
            return;
        }
        
        if (e.target === img || selectionBox.contains(e.target)) {
            isDragging = true;
            dragHandle = 'move';
            const coords = getImgCoords(e);
            CaptureState.startX = coords.x;
            CaptureState.startY = coords.y;
        }
    });
    
    document.addEventListener('mousemove', function(e) {
        if (!isDragging) return;
        
        const coords = getImgCoords(e);
        const imgRect = img.getBoundingClientRect();
        
        let x = CaptureState.startX;
        let y = CaptureState.startY;
        let width = coords.x - CaptureState.startX;
        let height = coords.y - CaptureState.startY;
        
        if (width < 0) {
            x = coords.x;
            width = -width;
        }
        if (height < 0) {
            y = coords.y;
            height = -height;
        }
        
        x = Math.max(0, Math.min(x, imgRect.width));
        y = Math.max(0, Math.min(y, imgRect.height));
        width = Math.min(width, imgRect.width - x);
        height = Math.min(height, imgRect.height - y);
        
        const scaleX = img.naturalWidth / imgRect.width;
        const scaleY = img.naturalHeight / imgRect.height;
        
        CaptureState.selection = {
            x: Math.round(x * scaleX),
            y: Math.round(y * scaleY),
            width: Math.round(width * scaleX),
            height: Math.round(height * scaleY)
        };
        
        updateSelectionBox();
        selectionBox.style.display = 'block';
    });
    
    document.addEventListener('mouseup', function() {
        isDragging = false;
        dragHandle = null;
    });
    
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            cancelCapture();
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    initCaptureInteraction();
});

async function captureOCR() {
    addLog('点击: 截图识别', 'info');

    // 显示进度条
    updateProgressBar('singleOcrProgress', 'singleOcrProgressFill', 'singleOcrProgressText', 0, 1, '正在截取屏幕...');

    // 启动轮询
    const ocrTimer = startPollingOperation(
        'single_ocr',
        'singleOcrProgress',
        'singleOcrProgressFill',
        'singleOcrProgressText',
        () => window.pywebview.api.get_operation_status()
    );

    try {
        const backend = document.getElementById('ocrBackend')?.value || 'auto';
        const result = await window.pywebview.api.capture_ocr_with_tkinter(backend);

        if (result.success) {
            document.getElementById('ocrResultText').value = result.text || '';

            if (result.image_data_url) {
                const previewImg = document.getElementById('screenshotPreviewImg');
                const placeholder = document.getElementById('screenshotPlaceholder');
                if (previewImg) {
                    previewImg.src = result.image_data_url;
                    previewImg.style.display = 'block';
                }
                if (placeholder) {
                    placeholder.style.display = 'none';
                }
            }

            AppState.questionRegion = {
                selected: true,
                x: result.region.left,
                y: result.region.top,
                width: result.region.width,
                height: result.region.height
            };
            const statusEl = document.getElementById('questionRegionStatus');
            if (statusEl) {
                statusEl.textContent = `(${result.region.left}, ${result.region.top}) - ${result.region.width}x${result.region.height}`;
                statusEl.classList.add('status-success');
            }

            addLog(`OCR识别完成 (${result.backend || backend}), 耗时: ${result.elapsed}s`, 'success');
        } else {
            addLog(`OCR识别失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`截图异常: ${e.message}`, 'error');
    }

    clearInterval(ocrTimer);
    hideProgressBar('singleOcrProgress');
}

async function fixedRegionOCR() {
    addLog('点击: 固定区域识别', 'info');

    // 显示进度条
    updateProgressBar('singleOcrProgress', 'singleOcrProgressFill', 'singleOcrProgressText', 0, 1, '正在识别固定区域...');

    // 启动轮询
    const ocrTimer = startPollingOperation(
        'single_ocr',
        'singleOcrProgress',
        'singleOcrProgressFill',
        'singleOcrProgressText',
        () => window.pywebview.api.get_operation_status()
    );

    try {
        const backend = document.getElementById('ocrBackend')?.value || 'auto';
        const result = await window.pywebview.api.recognize_fixed_region(backend);

        if (result.success) {
            document.getElementById('ocrResultText').value = result.text || '';
            addLog(`固定区域OCR完成 (${result.backend || backend}), 耗时: ${result.elapsed}s`, 'success');
        } else {
            addLog(`OCR识别失败: ${result.error || result.message}`, 'error');
        }
    } catch (e) {
        addLog(`OCR识别异常: ${e.message}`, 'error');
    }

    clearInterval(ocrTimer);
    hideProgressBar('singleOcrProgress');
}

function toggleAdvancedSettings() {
    const panel = document.getElementById('advancedPanel');
    if (panel) {
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    }
}

async function copyScreenshot() {
    addLog('点击: 复制截图', 'info');
    try {
        const result = await window.pywebview.api.copy_screenshot();
        if (result.success) {
            addLog('截图已复制到剪贴板', 'success');
        }
    } catch (e) {
        addLog('复制截图失败 (Mock)', 'success');
    }
}

async function copyOCRResult() {
    const text = document.getElementById('ocrResultText')?.value;
    if (!text) {
        addLog('OCR结果为空', 'warning');
        return;
    }
    
    addLog('点击: 复制结果', 'info');
    try {
        const result = await window.pywebview.api.copy_ocr_result(text);
        if (result.success) {
            addLog('结果已复制到剪贴板', 'success');
        }
    } catch (e) {
        navigator.clipboard.writeText(text).then(() => {
            addLog('结果已复制到剪贴板 (JS)', 'success');
        }).catch(() => {
            addLog('复制失败', 'error');
        });
    }
}

function clearOCRResult() {
    addLog('点击: 清空结果', 'info');
    document.getElementById('ocrResultText').value = '';
    addLog('结果已清空', 'info');
}

async function selectQuestionRegion() {
    addLog('点击: 选择题目区域', 'info');
    
    try {
        const result = await window.pywebview.api.select_question_region();
        
        if (result.success) {
            AppState.questionRegion = {
                selected: true,
                ...result.region
            };
            const statusEl = document.getElementById('questionRegionStatus');
            if (statusEl) {
                statusEl.textContent = `(${result.region.left}, ${result.region.top}) - ${result.region.width}x${result.region.height}`;
                statusEl.classList.add('status-success');
            }
            addLog(`题目区域已选择: ${result.region.width}x${result.region.height}`, 'success');
            renderState();
        } else {
            addLog(`选择失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`选择异常: ${e.message}`, 'error');
    }
}

async function selectNumberRegion() {
    addLog('点击: 选择题号区域', 'info');
    
    try {
        const result = await window.pywebview.api.select_number_region();
        
        if (result.success) {
            AppState.numberRegion = {
                selected: true,
                ...result.region
            };
            const statusEl = document.getElementById('numberRegionStatus');
            if (statusEl) {
                statusEl.textContent = `(${result.region.left}, ${result.region.top}) - ${result.region.width}x${result.region.height}`;
                statusEl.classList.add('status-success');
            }
            addLog(`题号区域已选择: ${result.region.width}x${result.region.height}`, 'success');
            renderState();
        } else {
            addLog(`选择失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`选择异常: ${e.message}`, 'error');
    }
}

async function saveNumberCapture() {
    addLog('点击: 保存题号截图', 'info');
    
    try {
        const result = await window.pywebview.api.save_number_region_capture();
        
        if (result.success) {
            addLog(`题号截图已保存: ${result.path || ''}`, 'success');
        } else {
            addLog(`保存失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`保存异常: ${e.message}`, 'error');
    }
}

async function detectQuestionPoints() {
    addLog('点击: 智能识别题号坐标', 'info');
    updateProgressBar('detectProgress', 'detectProgressFill', 'detectProgressText', 0, 1, '正在识别题号');
    const detectTimer = startPollingOperation(
        'detect',
        'detectProgress',
        'detectProgressFill',
        'detectProgressText',
        () => window.pywebview.api.get_operation_status()
    );
    
    try {
        const result = await window.pywebview.api.detect_question_points();
        
        if (result.success) {
            AppState.questionPoints = result.points || [];
            AppState.numberCoordsCount = result.count || 0;
            renderQuestionPointsTable(result.points);
            addLog(`识别完成: ${result.count}个题号`, 'success');
        } else {
            addLog(`识别失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`识别异常: ${e.message}`, 'error');
    }
    clearInterval(detectTimer);
    hideProgressBar('detectProgress');
    
    renderState();
}

function renderQuestionPointsTable(points) {
    const tbody = document.getElementById('questionPointsTableBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!points || points.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-text">暂无数据</td></tr>';
        return;
    }

    points.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${p.display_no}</td>
            <td>${p.x}</td>
            <td>${p.y}</td>
            <td>${p.source}</td>
            <td><button class="btn btn-danger btn-sm" onclick="deleteQuestionPoint(${p.display_no})">删除</button></td>
        `;
        tbody.appendChild(tr);
    });
}

let isCollectionRunning = false;
let collectionPollTimer = null;

async function startCollection() {
    if (isCollectionRunning) return;
    
    addLog('点击: 开始采集', 'info');
    isCollectionRunning = true;
    updateProgressBar('collectionProgress', 'collectionProgressFill', 'collectionProgressText', 0, 1, '正在保存截图');
    
    const saveImages = document.getElementById('chkSaveCapture')?.checked || false;
    const testMode = document.getElementById('chkTestMode')?.checked || false;
    const interval = parseFloat(document.getElementById('collectionInterval')?.value || 0.4);
    
    try {
        const options = {
            test_mode: testMode,
            save_images: saveImages,
            interval: interval,
            click_delay: 0.0,
            text_ocr_backend: "auto",
            option_ocr_backend: "auto",
            parse_options: false
        };
        const result = await window.pywebview.api.start_collection(options);
        
        if (result.success) {
            showCollectionProgress(true);
            addLog(`采集已启动，共 ${result.total || 0} 题，当前只保存截图，不做 OCR`, 'info');
            
            pollCollectionStatus();
        } else {
            addLog(`采集失败: ${result.error}`, 'error');
            isCollectionRunning = false;
        }
    } catch (e) {
        addLog(`采集异常: ${e.message}`, 'error');
        isCollectionRunning = false;
    }
}

async function pollCollectionStatus() {
    if (!isCollectionRunning) return;
    
    try {
        const status = await window.pywebview.api.get_collection_status();
        
        if (status.success) {
            const current = status.current || 0;
            const total = status.total || 0;
            
            updateCollectionProgress(current, total);
            trackOperationProgress('collect', status);
            if (status.message) {
                updateProgressBar('collectionProgress', 'collectionProgressFill', 'collectionProgressText', current, total || 1, status.message);
            }
            
            if (status.records && status.records.length > 0) {
                renderCollectionResultsTable(status.records);
            }
            
            if (!status.running) {
                isCollectionRunning = false;
                showCollectionProgress(false);
                addLog(`截图采集完成: ${current}题`, 'success');
                clearInterval(collectionPollTimer);
                collectionPollTimer = null;
                return;
            }
        }
    } catch (e) {
        console.error('Poll error:', e);
    }
    
    collectionPollTimer = setTimeout(pollCollectionStatus, 500);
}

async function simulateCollection(mockResults) {
    const total = mockResults.length;
    const interval = parseFloat(document.getElementById('collectionInterval')?.value || 0.4) * 1000;
    let current = 0;
    
    for (const result of mockResults) {
        if (!isCollectionRunning) break;
        
        current++;
        updateCollectionProgress(current, total);
        
        if (interval > 0) {
            await new Promise(r => setTimeout(r, interval));
        }
    }
    
    isCollectionRunning = false;
    showCollectionProgress(false);
    renderCollectionResultsTable(mockResults);
    addLog(`截图采集完成: ${current}题`, 'success');
}

function generateMockCollectionResults(count) {
    const results = [];
    for (let i = 0; i < count; i++) {
        results.push({
            index: i + 1,
            click_x: 100 + (i % 5) * 150,
            click_y: 200 + Math.floor(i / 5) * 80,
            ocr_text: `题目${i + 1}的内容文本`,
            image_path: `capture_${i + 1}.png`,
            status: 'success'
        });
    }
    return results;
}

function showCollectionProgress(show) {
    const progress = document.getElementById('collectionProgress');
    if (progress) {
        progress.style.display = show ? 'block' : 'none';
    }
}

function updateCollectionProgress(current, total) {
    const fill = document.getElementById('collectionProgressFill');
    const text = document.getElementById('collectionProgressText');
    const percent = (current / total) * 100;
    
    if (fill) fill.style.width = `${percent}%`;
    if (text) text.textContent = `${current} / ${total}`;
}

function renderCollectionResultsTable(results) {
    const tbody = document.getElementById('collectionResultsTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (!results || results.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-text">暂无数据</td></tr>';
        return;
    }
    
    results.forEach(r => {
        const tr = document.createElement('tr');
        const statusClass = (r.status === 'success' || r.status === 'captured' || r.status === 'parsed') ? 'status-success' : 'status-error';
        tr.innerHTML = `
            <td>${r.index}</td>
            <td>${r.click_x}</td>
            <td>${r.click_y}</td>
            <td>${r.ocr_text || '-'}</td>
            <td>${r.image_path || '-'}</td>
            <td class="${statusClass}">${r.status}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function stopCollection() {
    addLog('点击: 停止采集', 'warning');
    isCollectionRunning = false;
    
    if (collectionPollTimer) {
        clearTimeout(collectionPollTimer);
        collectionPollTimer = null;
    }
    
    try {
        await window.pywebview.api.stop_collection();
    } catch (e) {
        // ignore
    }
    
    showCollectionProgress(false);
    addLog('采集已停止', 'info');
}

async function parseCollectedOptions() {
    addLog('点击: 解析选项', 'info');

    // 显示进度条
    updateProgressBar('optionParseProgress', 'optionParseProgressFill', 'optionParseProgressText', 0, 1, '正在初始化解析引擎...');

    // 启动轮询
    const parseTimer = startPollingOperation(
        'parse_collected_options',
        'optionParseProgress',
        'optionParseProgressFill',
        'optionParseProgressText',
        () => window.pywebview.api.get_operation_status()
    );

    const textOcrBackend = document.getElementById('textOcrBackend')?.value || 'auto';
    const optionOcrBackend = document.getElementById('optionOcrBackend')?.value || 'auto';

    try {
        const options = {
            text_ocr_backend: textOcrBackend,
            option_ocr_backend: optionOcrBackend
        };

        const result = await window.pywebview.api.parse_collected_options(options);

        if (result.success) {
            renderCollectionResultsTable(result.records || []);
            addLog(result.message, 'success');
        } else {
            addLog(`解析失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`解析异常: ${e.message}`, 'error');
    }

    clearInterval(parseTimer);
    hideProgressBar('optionParseProgress');
}

async function collectQuestions() {
    addLog('点击: 开始采集', 'info');
    
    try {
        const result = await window.pywebview.api.collect_questions();
        
        if (result.success) {
            AppState.questions = result.questions || [];
            AppState.collectedQuestions = result.count || 0;
            AppState.numberCoordsCount = result.count || 0;
            
            renderQuestionTable(result.questions);
            initAnswerList();  // 采集完成后根据实际题目重新生成答案列表
            addLog(`采集完成: ${result.count}题`, 'success');
        }
    } catch (e) {
        addLog(`采集异常: ${e.message}`, 'error');
    }
    
    renderState();
}

function renderQuestionTable(questions) {
    const tbody = document.getElementById('questionTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (!questions || questions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-text">暂无数据</td></tr>';
        return;
    }
    
    const typeLabels = { 'single': '单选', 'multi': '多选', 'true_false': '判断' };
    
    questions.forEach(q => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${q.id}</td>
            <td>${q.display_no}</td>
            <td>${typeLabels[q.type] || '-'}</td>
            <td>${q.x}</td>
            <td>${q.y}</td>
            <td class="status-success">${q.has_text ? '已采集' : '未采集'}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function exportCollectedQuestions() {
    addLog('点击: 复制所有题目', 'info');
    
    try {
        const result = await window.pywebview.api.export_collected_questions();
        
        if (result.success) {
            addLog(result.message, 'success');
        } else {
            addLog(`复制失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`复制异常: ${e.message}`, 'error');
    }
}

async function getAIPrompt() {
    addLog('点击: 复制AI提示词', 'info');
    
    try {
        const result = await window.pywebview.api.get_ai_prompt_with_questions();
        
        if (result.success) {
            addLog(result.message, 'success');
        } else {
            addLog(`复制失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`复制异常: ${e.message}`, 'error');
    }
}

async function parseAnswers() {
    const text = document.getElementById('answerInput')?.value.trim();
    
    if (!text) {
        addLog('请先输入或粘贴答案', 'error');
        return;
    }
    
    addLog('点击: 解析答案', 'info');
    
    try {
        const result = await window.pywebview.api.parse_answers(text);
        
        if (result.success) {
            AppState.answers = result.rows || [];
            AppState.parsedAnswers = (result.rows || []).length;
            AppState.answersDict = result.answers || {};
            
            renderAnswerTable(result.rows || []);
            fillAnswerListFromParsed(result.answers || {});
            addLog(`解析完成: ${result.rows?.length || 0}个答案`, 'success');
            
            const taskResult = await window.pywebview.api.build_answer_click_tasks({
                answers: result.answers || {},
                rows: result.rows || []
            });
            
            if (taskResult.success) {
                AppState.answerTasks = taskResult.tasks || [];
                AppState.taskSummary = taskResult.summary || {};
                renderAnswerTasksTable(taskResult.tasks || []);
                addLog(`任务生成: ready=${taskResult.summary?.ready || 0}, no_answer=${taskResult.summary?.no_answer || 0}`, 'success');
            } else {
                addLog(`任务生成失败: ${taskResult.error}`, 'error');
            }
        } else {
            addLog(`解析失败: ${result.error}`, 'error');
        }
    } catch (e) {
        addLog(`解析异常: ${e.message}`, 'error');
    }
    
    document.getElementById('answerResultSection').style.display = 'block';
    renderState();
}

function fillAnswerListFromParsed(answersDict) {
    const inputs = document.querySelectorAll('.answer-input');
    inputs.forEach(input => {
        input.value = '';
    });
    
    for (const [globalId, answer] of Object.entries(answersDict)) {
        const match = globalId.match(/^Q(\d+)$/);
        if (match) {
            const no = parseInt(match[1]);
            const input = document.querySelector(`.answer-input[data-no="${no}"]`);
            if (input) {
                input.value = answer;
            }
        }
    }
}

function clearAnswers() {
    const textarea = document.getElementById('answerInput');
    if (textarea) {
        textarea.value = '';
    }
    
    const inputs = document.querySelectorAll('.answer-input');
    inputs.forEach(input => {
        input.value = '';
    });
    
    AppState.answers = [];
    AppState.parsedAnswers = 0;
    AppState.answersDict = {};
    
    const tbody = document.getElementById('answerTableBody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-text">无有效答案</td></tr>';
    }
    
    addLog('答案已清空', 'info');
    renderState();
}

function parseAnswerText(text) {
    const results = [];
    const lines = text.split('\n').filter(l => l.trim());
    
    let sequenceIndex = 0;
    
    for (const line of lines) {
        const trimmed = line.trim();
        
        const patterns = [
            { regex: /^(\d+)\s*[.、)]\s*([A-Z]+)$/, type: 'single', desc: '题号.答案' },
            { regex: /^第(\d+)题\s+([A-Z]+)$/, type: 'single', desc: '第N题 答案' },
            { regex: /^题目(\d+)\s+([A-Z]+)$/, type: 'single', desc: '题目N 答案' },
            { regex: /^Q(\d+)\s+([A-Z]+)$/, type: 'single', desc: 'QN 答案' },
            { regex: /^[二二]?-(\d+)\s+([A-Z]+)$/, type: 'multi', desc: '二-N 答案' },
            { regex: /^[三三]?-(\d+)\s+(正确|对|错|错误|否|FALSE|TRUE|T|F|YES|NO|1|0|√|×|✓|✗)$/, type: 'true_false', desc: '三-N 判断' },
            { regex: /^判断(\d+)\s+(正确|对|错|错误|否|FALSE|TRUE|T|F|YES|NO|1|0|√|×|✓|✗)$/, type: 'true_false', desc: '判断N 判断' },
            { regex: /^(\d+)([A-Z])$/, type: 'single', desc: 'N答案' },
        ];
        
        let matched = false;
        
        for (const pattern of patterns) {
            const match = trimmed.match(pattern.regex);
            if (match) {
                let questionId, answer;
                
                if (pattern.type === 'true_false') {
                    if (pattern.regex.toString().includes('二') || pattern.regex.toString().includes('2')) {
                        questionId = `二-${match[1]}`;
                    } else if (pattern.regex.toString().includes('三') || pattern.regex.toString().includes('3')) {
                        questionId = `三-${match[1]}`;
                    } else {
                        questionId = String(match[1]);
                    }
                    
                    const rawAnswer = match[2].toUpperCase();
                    answer = ['正确', '对', 'T', 'TRUE', 'YES', '1', '√', '✓'].includes(rawAnswer) ? 'TRUE' : 'FALSE';
                } else {
                    if (pattern.regex.toString().includes('二') || pattern.regex.toString().includes('2')) {
                        questionId = `二-${match[1]}`;
                    } else if (pattern.regex.toString().includes('三') || pattern.regex.toString().includes('3')) {
                        questionId = `三-${match[1]}`;
                    } else if (pattern.regex.toString().includes('Q')) {
                        questionId = `Q${match[1]}`;
                    } else if (pattern.regex.toString().includes('题目')) {
                        questionId = `题目${match[1]}`;
                    } else if (pattern.regex.toString().includes('第')) {
                        questionId = `第${match[1]}题`;
                    } else {
                        questionId = match[1];
                    }
                    answer = match[2].toUpperCase();
                }
                
                results.push({
                    raw_input: trimmed,
                    question_id: questionId,
                    answer: answer,
                    type: pattern.type,
                    status: 'valid',
                    description: pattern.desc
                });
                
                matched = true;
                break;
            }
        }
        
        if (!matched) {
            const singleCharMatches = trimmed.match(/^([A-Z])$/);
            if (singleCharMatches) {
                sequenceIndex++;
                results.push({
                    raw_input: trimmed,
                    question_id: `#${sequenceIndex}`,
                    answer: singleCharMatches[1].toUpperCase(),
                    type: 'single',
                    status: 'valid',
                    description: '顺序解析'
                });
                matched = true;
            }
        }
        
        if (!matched && trimmed.length > 0) {
            const allChars = trimmed.replace(/[^A-Z]/g, '').toUpperCase();
            if (allChars.length > 0 && /^[A-Z]+$/.test(allChars)) {
                for (const char of allChars) {
                    sequenceIndex++;
                    results.push({
                        raw_input: trimmed,
                        question_id: `#${sequenceIndex}`,
                        answer: char,
                        type: 'single',
                        status: 'valid',
                        description: '顺序解析'
                    });
                }
                matched = true;
            }
        }
        
        if (!matched && trimmed.length > 0) {
            results.push({
                raw_input: trimmed,
                question_id: '-',
                answer: '-',
                type: 'unknown',
                status: 'invalid',
                description: '无法解析'
            });
        }
    }
    
    return results;
}

function renderAnswerTable(results) {
    const tbody = document.getElementById('answerTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (!results || results.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-text">无有效答案</td></tr>';
        return;
    }
    
    results.forEach(r => {
        const statusClass = r.status === 'valid' ? 'status-success' : (r.status === 'invalid' ? 'status-error' : 'status-warning');
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${r.raw_input}</td>
            <td>${r.display_no || r.global_id || r.question_id || '-'}</td>
            <td><code style="background: var(--color-surface-card); padding: 2px 6px; border-radius: 4px;">${r.answer}</code></td>
            <td class="${statusClass}">${r.status}</td>
            <td>${r.message || r.description || '-'}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderAnswerTasksTable(tasks) {
    const tbody = document.getElementById('answerClickTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (!tasks || tasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-text">暂无数据 - 请先在"答案输入"页面解析答案</td></tr>';
        return;
    }
    
    tasks.forEach(t => {
        const statusClass = t.status === 'ready' ? 'status-success' : 
                           (t.status === 'no_answer' ? 'status-warning' : 'status-error');
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${t.display_no || t.question_no}</td>
            <td><code style="background: var(--color-surface-card); padding: 2px 6px; border-radius: 4px;">${t.answer || '-'}</code></td>
            <td>${t.question_click ? `(${t.question_click[0]}, ${t.question_click[1]})` : '-'}</td>
            <td>${t.answer_clicks && t.answer_clicks.length > 0 ? t.answer_clicks.map(ac => `(${ac[0]}, ${ac[1]})`).join(', ') : '-'}</td>
            <td class="${statusClass}">${t.status}</td>
        `;
        tbody.appendChild(tr);
    });
    
    const summaryEl = document.getElementById('answerClickSummary');
    if (summaryEl && AppState.taskSummary) {
        const s = AppState.taskSummary;
        summaryEl.innerHTML = `<td colspan="5">就绪: ${s.ready || 0} | 无答案: ${s.no_answer || 0} | 无坐标: ${s.no_option || 0} | 需检查: ${s.need_check || 0}</td>`;
    }
}

function clearAnswers() {
    addLog('点击: 清空答案', 'info');
    
    const input = document.getElementById('answerInput');
    if (input) input.value = '';
    
    const resultSection = document.getElementById('answerResultSection');
    if (resultSection) resultSection.style.display = 'none';
    hideProgressBar('parseProgress');
    hideProgressBar('answerClickProgress');
    
    AppState.answers = [];
    AppState.parsedAnswers = 0;
    
    renderState();
    addLog('答案已清空', 'info');
}

async function executeClicks() {
    executeAllAnswers();
}

let isExecutionRunning = false;
let currentExecutionIndex = 0;
let answerClickTasks = [];

function buildAnswerClickTasks() {
    const tasks = [];
    const testMode = document.getElementById('chkAnswerTestMode')?.checked || false;
    
    const answersData = {
        answers: {},
        rows: AppState.answers
    };
    
    AppState.answers.forEach((answer, index) => {
        const gid = answer.global_id || `Q${String(answer.question_id).padStart(6, '0')}`;
        answersData.answers[gid] = answer.answer || "";
    });
    
    try {
        const result = window.pywebview.api.build_answer_click_tasks({
            answers: answersData.answers,
            rows: AppState.answers || []
        });
        if (result && result.success) {
            answerClickTasks = result.tasks || [];
            const summaryEl = document.getElementById('answerClickSummary');
            if (summaryEl && result.summary) {
                summaryEl.textContent = `就绪: ${result.summary.ready} | 无答案: ${result.summary.no_answer} | 无坐标: ${result.summary.no_option} | 需检查: ${result.summary.need_check}`;
            }
            return answerClickTasks;
        }
    } catch (e) {
        console.error("build_answer_click_tasks failed:", e);
    }
    
    AppState.answers.forEach((answer, index) => {
        let questionX = 0, questionY = 0;
        let optionX = 0, optionY = 0;
        let status = 'ready';
        
        if (AppState.questionPoints && AppState.questionPoints.length > 0) {
            const qp = AppState.questionPoints[index];
            if (qp) {
                questionX = qp.x;
                questionY = qp.y;
            } else {
                status = 'no_answer';
            }
        } else {
            questionX = 100 + (index % 5) * 150;
            questionY = 200 + Math.floor(index / 5) * 80;
        }
        
        if (answer.answer && answer.answer !== '-') {
            optionX = questionX + 50;
            optionY = questionY + 30;
        } else {
            status = 'no_option';
        }
        
        if (status === 'ready' && answer.status !== 'valid') {
            status = 'need_check';
        }
        
        tasks.push({
            index: index,
            question_id: answer.question_id,
            answer: answer.answer,
            question_x: questionX,
            question_y: questionY,
            option_x: optionX,
            option_y: optionY,
            status: status,
            testMode: testMode
        });
    });
    
    answerClickTasks = tasks;
    return tasks;
}

function renderAnswerClickTable(tasks) {
    const tbody = document.getElementById('answerClickTableBody');
    if (!tbody) return;
    
    if (!tasks || tasks.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-text">暂无数据 - 请先在"答案输入"页面解析答案</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    
    tasks.forEach(task => {
        let statusClass = 'status-success';
        if (task.status === 'no_answer') statusClass = 'status-muted';
        else if (task.status === 'no_option') statusClass = 'status-warning';
        else if (task.status === 'need_check') statusClass = 'status-warning';

        const questionClick = task.question_click || (
            task.question_x !== undefined && task.question_y !== undefined
                ? [task.question_x, task.question_y]
                : []
        );
        const optionClicks = task.answer_clicks || (
            task.option_x !== undefined && task.option_y !== undefined
                ? [[task.option_x, task.option_y]]
                : []
        );
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${task.display_no || task.question_no || task.question_id || '-'}</td>
            <td><code>${task.answer}</code></td>
            <td>${questionClick.length === 2 ? `(${questionClick[0]}, ${questionClick[1]})` : '-'}</td>
            <td>${optionClicks.length > 0 ? optionClicks.map(ac => `(${ac[0]}, ${ac[1]})`).join(', ') : '-'}</td>
            <td class="${statusClass}">${task.status}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function executeAllAnswers() {
    addLog('点击: 自动批量答题', 'info');

    const clickDelay = parseFloat(document.getElementById('clickDelay').value) || 0.15;
    const clickInterval = parseFloat(document.getElementById('clickInterval').value) || 0.15;
    const clickMode = document.getElementById('clickModeSelect').value; // 动态获取引擎模式

    showProgressBar('answerClickProgress');
    updateAnswerClickProgress(0, 100, '准备执行');

    const executeTimer = startPollingOperation(
        'execute',
        'answerClickProgress',
        'answerClickProgressFill',
        'answerClickProgressText',
        () => window.pywebview.api.get_execution_status()
    );

    try {
        // 将 click_mode 作为 options 的一个参数完整发送给后端
        const res = await window.pywebview.api.execute_all_answers({
            test_mode: false,
            click_mode: clickMode,
            click_delay: clickDelay,
            interval: clickInterval
        });

        if (res && res.success) {
            addLog(`执行完成: ${res.message}`, 'success');
            showToast(res.message);
        } else {
            addLog(`执行失败: ${res ? res.error : '未知错误'}`, 'error');
            showToast(res ? res.error : '未知错误', true);
        }
    } catch (e) {
        addLog(`执行异常: ${e.message}`, 'error');
        showToast(e.message, true);
    }

    clearInterval(executeTimer);
    hideProgressBar('answerClickProgress');
}

async function stopExecution() {
    addLog('点击: 停止执行', 'warning');
    
    try {
        await window.pywebview.api.stop_execution();
    } catch (e) {
        // ignore
    }
    
    hideProgressBar('answerClickProgress');
    addLog('执行已停止', 'info');
}

function showAnswerClickProgress(show) {
    const progress = document.getElementById('answerClickProgress');
    if (progress) {
        progress.style.display = show ? 'block' : 'none';
    }
}

function updateAnswerClickProgress(current, total, label = '') {
    const fill = document.getElementById('answerClickProgressFill');
    const text = document.getElementById('answerClickProgressText');
    const safeTotal = Math.max(0, Number(total) || 0);
    const safeCurrent = Math.max(0, Number(current) || 0);
    const percent = safeTotal > 0 ? (safeCurrent / safeTotal) * 100 : 0;
    
    if (fill) fill.style.width = `${percent}%`;
    if (text) text.textContent = label ? `${label} ${safeCurrent} / ${safeTotal}` : `${safeCurrent} / ${safeTotal}`;
}

function showToast(message, isError = false) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    toast.style.borderColor = isError ? 'var(--color-accent-red)' : 'var(--color-hairline)';
    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 3000);
}

// ==================== 手动编辑题号坐标功能 ====================

let mouseCountdownTimer = null;

/**
 * 触发智能网格推断（独立API，用户手动触发）
 */
async function triggerInferMissingPoints() {
    const btn = document.getElementById('btnInferPoints');

    // 禁用按钮，防止重复点击
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = '⏳ 正在进行网格推断...';

    addLog('开始执行智能网格推断...', 'info');

    try {
        // 调用后端API
        const result = await window.pywebview.api.trigger_infer_missing_points();

        if (result.success) {
            // 推断成功
            showToast(result.message, false);
            addLog(result.message, 'success');
            addLog(`推断详情：原始 ${result.original_count} 个点 → 最终 ${result.total_count} 个点（新增 ${result.inferred_count} 个，分为 ${result.sections} 个段落）`, 'info');

            // 用返回的数据重新渲染表格
            AppState.questionPoints = result.points || [];
            AppState.numberCoordsCount = result.total_count || 0;
            renderQuestionPointsTable(result.points);
            renderState();

            // 更新统计信息
            document.getElementById('detectedCount').textContent = `${result.total_count} 个`;
        } else {
            // 推断失败
            showToast(result.error || '网格推断失败', true);
            addLog(`推断失败: ${result.error}`, 'error');
        }
    } catch (e) {
        // 异常处理
        showToast(`网格推断异常: ${e}`, true);
        addLog(`推断异常: ${e}`, 'error');
        console.error('triggerInferMissingPoints error:', e);
    } finally {
        // 恢复按钮状态
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

/**
 * 打开手动编辑模态框
 */
function openPointModal(editNo = null) {
    const overlay = document.getElementById('pointModalOverlay');
    const title = document.getElementById('pointModalTitle');
    const inputNo = document.getElementById('inputPointNo');
    const inputX = document.getElementById('inputPointX');
    const inputY = document.getElementById('inputPointY');

    // 清空或填充表单（题号始终可编辑）
    if (editNo !== null) {
        title.textContent = `编辑题号`;
        inputNo.value = editNo;
    } else {
        title.textContent = '手动添加/编辑题号';
        inputNo.value = '';
    }
    inputNo.disabled = false;  // 始终允许编辑题号
    inputX.value = '';
    inputY.value = '';

    // 显示模态框
    overlay.style.display = 'flex';

    // 绑定事件
    bindPointModalEvents();
}

/**
 * 关闭手动编辑模态框
 */
function closePointModal() {
    const overlay = document.getElementById('pointModalOverlay');
    overlay.style.display = 'none';

    // 取消快捷键监听（防止钩子残留）
    cancelHotkeyListener();
}

/**
 * 绑定模态框事件
 */
function bindPointModalEvents() {
    // 关闭按钮
    document.getElementById('btnClosePointModal').onclick = closePointModal;
    document.getElementById('btnCancelPointModal').onclick = closePointModal;

    // 确认按钮
    document.getElementById('btnConfirmPointModal').onclick = confirmPointModal;

    // 获取鼠标坐标按钮（倒计时功能）
    document.getElementById('btnGetMousePos').onclick = startMouseCountdown;

    // 点击遮罩层关闭
    document.getElementById('pointModalOverlay').onclick = function(e) {
        if (e.target === this) {
            closePointModal();
        }
    };
}

/**
 * 启动Home键监听获取鼠标坐标（非阻塞 + 前端轮询）
 */
let hotkeyPollTimer = null;  // 轮询定时器引用

function startMouseCountdown() {
    const btn = document.getElementById('btnGetMousePos');

    btn.disabled = true;
    btn.textContent = '🖱️ 请将鼠标指向题目，然后按 [Home] 键...';
    addLog('正在启动快捷键监听...', 'info');

    // 第1步：启动后端的非阻塞快捷键监听
    window.pywebview.api.start_hotkey_listener().then(startResult => {
        if (!startResult.success) {
            showToast(startResult.error || '启动监听失败', true);
            resetHotkeyButton();
            return;
        }

        addLog('快捷键监听已启动，请按 Home 键', 'success');

        // 第2步：开始轮询检测按键结果（300ms间隔）
        hotkeyPollTimer = setInterval(async () => {
            try {
                const result = await window.pywebview.api.check_hotkey_result();

                if (result.waiting) {
                    // 仍在等待用户按键，继续轮询
                    return;
                }

                // 收到结果！停止轮询
                clearInterval(hotkeyPollTimer);
                hotkeyPollTimer = null;
                resetHotkeyButton();

                if (result.success) {
                    // 成功获取坐标，填入输入框
                    document.getElementById('inputPointX').value = result.x;
                    document.getElementById('inputPointY').value = result.y;
                    addLog(`已捕获坐标: (${result.x}, ${result.y})`, 'success');
                } else {
                    showToast(result.error || '获取坐标失败', true);
                }
            } catch (e) {
                // 出错时停止轮询
                clearInterval(hotkeyPollTimer);
                hotkeyPollTimer = null;
                resetHotkeyButton();
                showToast(`轮询失败: ${e}`, true);
            }
        }, 300);  // 每300ms检查一次

    }).catch(e => {
        showToast(`启动监听失败: ${e}`, true);
        resetHotkeyButton();
    });
}

/**
 * 重置快捷键按钮状态
 */
function resetHotkeyButton() {
    const btn = document.getElementById('btnGetMousePos');
    if (btn) {
        btn.textContent = '🎯 监听快捷键 (按 Home 键获取)';
        btn.disabled = false;
    }
}

/**
 * 取消快捷键监听（关闭对话框时调用）
 */
async function cancelHotkeyListener() {
    // 停止前端轮询
    if (hotkeyPollTimer) {
        clearInterval(hotkeyPollTimer);
        hotkeyPollTimer = null;
    }

    // 通知后端取消监听
    try {
        await window.pywebview.api.cancel_hotkey_listener();
        addLog('已取消快捷键监听', 'info');
    } catch (e) {
        console.warn('取消后端监听失败:', e);
    }

    // 恢复按钮状态
    resetHotkeyButton();
}

/**
 * 确认添加/更新题号
 */
async function confirmPointModal() {
    const no = parseInt(document.getElementById('inputPointNo').value);
    const x = parseFloat(document.getElementById('inputPointX').value);
    const y = parseFloat(document.getElementById('inputPointY').value);

    // 验证输入
    if (!no || isNaN(no) || no < 1) {
        showToast('请输入有效的题号（大于等于1）', true);
        return;
    }
    if (isNaN(x) || isNaN(y)) {
        showToast('请先填写 X 和 Y 坐标', true);
        return;
    }

    try {
        const result = await window.pywebview.api.add_or_update_question_point({
            no: no,
            x: x,
            y: y
        });

        if (result.success) {
            addLog(result.message, 'success');
            renderQuestionPointsTable(result.points);

            // 更新统计信息
            const countEl = document.querySelector('.detect-actions')?.nextElementSibling?.querySelector('.progress-text');
            if (countEl) {
                // 查找包含"共 X 个"的元素并更新
                const statsText = document.body.innerText.match(/共\s*(\d+)\s*个/);
                if (statsText) {
                    // 更新页面中的统计显示
                }
            }

            closePointModal();
            showToast(result.message);
        } else {
            showToast(result.error || '操作失败', true);
        }
    } catch (e) {
        showToast(`操作失败: ${e}`, true);
    }
}

/**
 * 删除指定题号
 */
async function deleteQuestionPoint(no) {
    if (!confirm(`确定要删除题号 ${no} 吗？`)) {
        return;
    }

    try {
        const result = await window.pywebview.api.delete_question_point(no);

        if (result.success) {
            addLog(result.message, 'success');
            renderQuestionPointsTable(result.points);
            showToast(result.message);
        } else {
            showToast(result.error || '删除失败', true);
        }
    } catch (e) {
        showToast(`删除失败: ${e}`, true);
    }
}

