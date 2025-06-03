// ✅ SIMPLE FIX: Global variables with proper initialization
let ws = null;
let allLogs = [];
let workflowCompleted = false;
let isWorkflowRunning = false;
let totalRows = 0;
let processedRows = 0;

// ✅ SIMPLE FIX: Connection management variables
let isConnecting = false;
let reconnectTimeout = null;
let connectionAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

let completedRows = 0;
let workflowTriggered = false;
let processingStarted = false;
let isProcessing = false;
let hasError = false;

// Workflow connection with status checking
let workflowCheckInterval;
const WEBHOOK_URL = 'http://192.168.0.97:5678/webhook/035f7711-1d10-4fc6-b71b-d02a60272fd7';
const WORKFLOW_TRIGGER_URL = 'http://192.168.0.97:5678/webhook-test/ad44fb78-e0fc-43fa-9003-77f8ef6693b8';

// WebSocket connection with proper management
function connectWebSocket() {
    console.log('🔌 Attempting WebSocket connection...');

    if (isConnecting) {
        console.log('⏸️ Connection attempt already in progress, skipping...');
        return;
    }

    if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
        console.log('🔗 Closing existing WebSocket connection...');
        ws.close(1000, 'Creating new connection');
        ws = null;
    }

    if (connectionAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.log('❌ Max reconnection attempts reached. Stopped trying to reconnect.');
        document.getElementById('status').textContent = 'Connection Failed';
        document.getElementById('status').className = 'connection-status disconnected';
        return;
    }

    isConnecting = true;
    connectionAttempts++;

    console.log(`🔄 Connection attempt ${connectionAttempts}/${MAX_RECONNECT_ATTEMPTS}`);

    try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`ws://192.168.0.97:8001/ws`);

        ws.onopen = function() {
            console.log('✅ Connected to log server successfully!');
            document.getElementById('status').textContent = 'Live';
            document.getElementById('status').className = 'connection-status connected';

            isConnecting = false;
            connectionAttempts = 0;

            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
                reconnectTimeout = null;
            }
        };

        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'all_logs') {
                    allLogs = data.logs;
                    displayLogsInHome(allLogs);
                    displayLogsInLogsPage(allLogs);

                } else if (data.type === 'rows_updated') {
                    totalRows = data.total_rows;
                    updateRowsCard(data);

                    // Start pulsing the dot when total > 0
                    const completedDot = document.querySelector('#completed-status-dot');
                    if (data.total_rows > 0 && completedDot) {
                        completedDot.className = 'status-dot pulse-green';
                    }

                } else if (data.type === 'error_detected') {
                    hasError = true;
                    updateWorkflowStatus('error', 'Error detected in workflow');

                    // Add red-pulse, then revert to green
                    const completedDot = document.querySelector('#completed-status-dot');
                    if (completedDot) {
                        completedDot.className = 'status-dot pulse-red';
                        setTimeout(() => {
                            completedDot.className = 'status-dot pulse-green';
                        }, 3000);
                    }

                } else if (data.type === 'processing_completed') {
                    isProcessing = false;
                    updateWorkflowStatus('completed', 'All rows completed');

                    // Success glow for dot
                    const completedDot = document.querySelector('#completed-status-dot');
                    if (completedDot) {
                        completedDot.className = 'status-dot pulse-success';
                    }

                } else if (data.type === 'new_log') {
                    allLogs.push(data.log);
                    if (allLogs.length > 1000) {
                        allLogs.shift();
                    }
                    displayLogsInHome(allLogs, true);
                    displayLogsInLogsPage(allLogs, true);

                } else if (data.type === 'logs_cleared') {
                    allLogs = [];
                    workflowCompleted = false;
                    displayLogsInHome(allLogs);
                    displayLogsInLogsPage(allLogs);

                } else if (data.type === 'workflow_completed') {
                    workflowCompleted = true;
                    isWorkflowRunning = false;
                    document.getElementById('status').textContent = 'Completed';
                    document.getElementById('status').className = 'connection-status completed';

                    // Auto-reset button after 3 seconds
                    setTimeout(() => {
                        resetButtonToReady();
                    }, 3000);

                } else if (data.type === 'workflow_reset') {
                    workflowCompleted = false;
                    document.getElementById('status').textContent = 'Live';
                    document.getElementById('status').className = 'connection-status connected';
                    resetButtonToReady();

                } else if (data.type === 'rows_completed_updated') {
                    completedRows = data.rows_completed;
                    updateCompletedRowsCard(data);

                    // Update dot animation based on progress
                    const completedDot = document.querySelector('#completed-status-dot');
                    if (completedDot && data.rows_completed > 0) {
                        if (data.rows_completed >= totalRows && totalRows > 0) {
                            completedDot.className = 'status-dot pulse-success';
                        } else {
                            completedDot.className = 'status-dot pulse-green';
                        }
                    }

                }

            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };


        ws.onclose = function(event) {
            console.log('❌ WebSocket connection closed. Code:', event.code, 'Reason:', event.reason);
            isConnecting = false;
            ws = null;

            document.getElementById('status').textContent = 'Disconnected';
            document.getElementById('status').className = 'connection-status disconnected';

            if (connectionAttempts < MAX_RECONNECT_ATTEMPTS) {
                console.log(`⏰ Attempting to reconnect in 3 seconds... (${connectionAttempts}/${MAX_RECONNECT_ATTEMPTS})`);

                if (reconnectTimeout) {
                    clearTimeout(reconnectTimeout);
                }

                reconnectTimeout = setTimeout(() => {
                    reconnectTimeout = null;
                    connectWebSocket();
                }, 3000);
            } else {
                console.log('❌ Max reconnection attempts reached. Connection stopped.');
            }
        };

        ws.onerror = function(error) {
            console.error('❌ WebSocket error:', error);
            isConnecting = false;
            document.getElementById('status').textContent = 'Error';
            document.getElementById('status').className = 'connection-status disconnected';
        };

    } catch (error) {
        console.error('❌ Error creating WebSocket:', error);
        isConnecting = false;
    }
}
function updateWorkflowStatus(status, message) {
    const indicator = document.getElementById('workflow-indicator');
    const statusText = document.getElementById('workflow-status-text');
    const subText = document.getElementById('workflow-sub-text');

    indicator.className = `status-indicator ${status}`;

    switch(status) {
        case 'waiting':
            statusText.textContent = 'Waiting';
            break;
        case 'processing':
            statusText.textContent = 'Processing';
            break;
        case 'error':
            statusText.textContent = 'Error';
            break;
        case 'completed':
            statusText.textContent = 'Completed';
            break;
        default:
            statusText.textContent = 'Inactive';
    }

    subText.textContent = message;
}

function updateCompletedRowsCard(data) {
    const completedRowsElement = document.getElementById('completed-rows-count');
    const completedStatusElement = document.getElementById('completed-rows-status');
    const cardElement = document.getElementById('rows-completed-card');

    if (completedRowsElement) {
        completedRowsElement.textContent = data.rows_completed.toLocaleString();
    }

    if (completedStatusElement) {
        if (data.rows_completed === 0) {
            completedStatusElement.textContent = 'No rows completed yet';
            cardElement.className = 'card'; // Remove any animation
        } else {
            const percentage = data.percentage || ((data.rows_completed / totalRows) * 100);
            let statusText = `${data.rows_completed.toLocaleString()}/${totalRows.toLocaleString()} completed (${percentage.toFixed(1)}%)`;

            if (data.row_number && data.gen_col) {
                statusText += ` | Row ${data.row_number}, Gen-col: ${data.gen_col}`;
            }

            completedStatusElement.textContent = statusText;
            completedStatusElement.className = 'sub-text positive';

            // Add pulsing animation to the card
            if (data.rows_completed >= totalRows && totalRows > 0) {
                completedStatusElement.textContent = `✅ All ${totalRows.toLocaleString()} rows completed!`;
                // cardElement.className = 'card completed'; // Success animation
            } else {
                // cardElement.className = 'card processing'; // Green pulsing while processing
            }
        }
    }
}

function updateStatusFromServer(data) {
    if (data.has_error) {
        updateWorkflowStatus('error', 'Error detected in workflow');
    } else if (data.is_processing) {
        updateWorkflowStatus('processing', 'Processing rows - green pulse active');
    } else if (data.processing_started) {
        updateWorkflowStatus('completed', 'Processing completed');
    } else if (data.workflow_triggered) {
        updateWorkflowStatus('waiting', 'Workflow triggered - waiting for processing');
    } else {
        updateWorkflowStatus('inactive', 'Ready to start');
    }
}

function resetAllStatus() {
    workflowTriggered = false;
    processingStarted = false;
    isProcessing = false;
    hasError = false;
    completedRows = 0;
    updateWorkflowStatus('inactive', 'Ready to start');
    // Reset card animation
    document.getElementById('rows-completed-card').className = 'card';
    resetButtonToReady();
}

// ✅ SIMPLE FIX: Clean button reset function
function resetButtonToReady() {
    const startBtn = document.getElementById('start-workflow-btn');
    isWorkflowRunning = false;
    startBtn.disabled = false;
    startBtn.textContent = 'Trigger Workflow';
    startBtn.style.backgroundColor = '';
    startBtn.style.color = '';
    console.log('🔄 Button reset to ready state');
}

// ✅ FIXED: Workflow status checking that doesn't interfere with button
async function checkWorkflowStatus() {
    try {
        const response = await fetch(WEBHOOK_URL);
        const data = await response.json();

        // ALWAYS update workflow status card regardless of button state
        updateWorkflowStatus(data.active, data.message || 'Workflow status checked');

        // ⚠️ IMPORTANT: Don't disable button based on workflow status
        // Button should only be disabled during manual workflow execution

        // Only help with stuck button recovery when workflow is truly inactive
        if (!isWorkflowRunning && !data.active) {
            const startBtn = document.getElementById('start-workflow-btn');
            if (startBtn.textContent === 'Running...' && startBtn.disabled) {
                console.log('🔄 Workflow status check: Resetting stuck button');
                resetButtonToReady();
            }
        }

    } catch (error) {
        console.error('Error checking workflow status:', error);
        updateWorkflowStatus(false, 'Connection failed');
    }
}
window.addEventListener('beforeunload', function() {
    console.log('🧹 Page unloading - cleaning up WebSocket connection');

    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, 'Page unloading');
        ws = null;
    }
});

// Reset connection attempts when user manually refreshes
window.addEventListener('focus', function() {
    if (connectionAttempts >= MAX_RECONNECT_ATTEMPTS && (!ws || ws.readyState === WebSocket.CLOSED)) {
        console.log('🔄 Window focused - resetting connection attempts');
        connectionAttempts = 0;
        connectWebSocket();
    }
});

// ✅ SIMPLE FIX: Simplified workflow start function
async function startWorkflow() {
    const startBtn = document.getElementById('start-workflow-btn');

    await fetch('http://192.168.0.97:8001/workflow/triggered', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
});

    // Prevent double-clicking
    if (isWorkflowRunning) {
        console.log('⏸️ Workflow already running, ignoring click');
        return;
    }

    startBtn.disabled = true;
    startBtn.textContent = 'Starting...';
    isWorkflowRunning = true;

    try {
        const isCustomEnabled = document.getElementById('custom-toggle').checked;
        const customValue = isCustomEnabled ? parseInt(document.getElementById('custom-value').value) || 1 : "";

        const response = await fetch(WORKFLOW_TRIGGER_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                trigger: 'manual',
                timestamp: new Date().toISOString(),
                customValue: customValue
            })
        });

        if (response.ok) {
            console.log('✅ Workflow started successfully');

            startBtn.textContent = 'Running...';
            startBtn.style.backgroundColor = '#ffc107';
            startBtn.style.color = '#000';

            // ✅ SIMPLE FIX: Auto-reset after 30 seconds if no completion message
            setTimeout(() => {
                if (isWorkflowRunning) {
                    console.log('⏰ Auto-resetting button after 30 seconds');
                    resetButtonToReady();
                }
            }, 30000);

        } else {
            throw new Error('Failed to start workflow');
        }

    } catch (error) {
        console.error('❌ Error starting workflow:', error);

        startBtn.textContent = 'Error - Click to Retry';
        startBtn.style.backgroundColor = '#e53e3e';
        isWorkflowRunning = false;

        // Reset button after 3 seconds on error
        setTimeout(() => {
            resetButtonToReady();
        }, 3000);
    }
}

// Notify server that workflow was triggered


function updateRowsCard(data) {
    const totalRowsElement = document.getElementById('total-rows-count');
    const rowsStatusElement = document.getElementById('rows-status');

    if (totalRowsElement) {
        totalRowsElement.textContent = data.total_rows.toLocaleString();
    }

    if (rowsStatusElement) {
        if (data.total_rows === 0) {
            rowsStatusElement.textContent = data.message || 'Waiting for workflow data...';
            rowsStatusElement.className = 'sub-text';
        } else if (data.processed_rows > 0) {
            const percentage = data.percentage || ((data.processed_rows / data.total_rows) * 100);
            if (data.processed_rows >= data.total_rows) {
                rowsStatusElement.textContent = `✅ All ${data.total_rows.toLocaleString()} rows completed`;
                rowsStatusElement.className = 'sub-text positive';
            } else {
                rowsStatusElement.textContent = `${data.processed_rows.toLocaleString()}/${data.total_rows.toLocaleString()} processed (${percentage.toFixed(1)}%)`;
                rowsStatusElement.className = 'sub-text positive';
            }
        } else {
            rowsStatusElement.textContent = `Ready to process ${data.total_rows.toLocaleString()} rows`;
            rowsStatusElement.className = 'sub-text';
        }
    }
}

async function loadRowsCount() {
    try {
        const response = await fetch('http://192.168.0.97:8001/rows');
        if (response.ok) {
            const data = await response.json();
            totalRows = data.total_rows;
            processedRows = data.processed_rows;
            updateRowsCard({
                total_rows: data.total_rows,
                processed_rows: data.processed_rows,
                percentage: data.percentage
            });
        } else {
            updateRowsCard({total_rows: 0, processed_rows: 0, message: 'Server not responding'});
        }
    } catch (error) {
        console.error('Error loading rows count:', error);
        updateRowsCard({total_rows: 0, processed_rows: 0, message: 'Unable to connect to server'});
    }
}

function updateWorkflowStatus(isActive, message) {
    const indicator = document.getElementById('workflow-indicator');
    const statusText = document.getElementById('workflow-status-text');
    const subText = document.getElementById('workflow-sub-text');

    if (isActive) {
        indicator.className = 'status-indicator active';
        statusText.textContent = 'Active';
        subText.textContent = message;
        subText.className = 'sub-text active';
    } else {
        indicator.className = 'status-indicator inactive';
        statusText.textContent = 'Inactive';
        subText.textContent = message;
        subText.className = 'sub-text inactive';
    }
}

function displayLogsInHome(logs, isNewLog = false) {
    const container = document.getElementById('home-log-entries');

    if (logs.length === 0) {
        container.innerHTML = '<div class="no-logs">No logs yet. Waiting for n8n workflows...</div>';
        return;
    }

    const recentLogs = logs.slice(-4).reverse();

    if (isNewLog && logs.length > 0) {
        const latestLog = logs[logs.length - 1];
        const existingLogs = container.querySelectorAll('.log-item');

        if (existingLogs.length >= 4) {
            existingLogs[existingLogs.length - 1].remove();
        }

        const div = createLogElement(latestLog, true);
        container.insertBefore(div, container.firstChild);

        setTimeout(() => {
            div.classList.remove('new-log', 'success-entry', 'error-entry');
        }, 800);
    } else {
        container.innerHTML = '';
        recentLogs.forEach(log => {
            const div = createLogElement(log, false);
            container.appendChild(div);
        });
    }
}

function displayLogsInLogsPage(logs, isNewLog = false) {
    const container = document.getElementById('full-logs-container');
    const statsBar = document.getElementById('stats-bar');

    const uniqueWorkflows = new Set(logs.filter(log => log.workflow_id).map(log => log.workflow_id)).size;
    const recentLogs = logs.filter(log => {
        const logTime = new Date(log.timestamp);
        const now = new Date();
        return (now - logTime) < 300000;
    }).length;

    const completionStatus = workflowCompleted ? ' | 🟡 WORKFLOW COMPLETED' : '';
    statsBar.innerHTML = `
        Stats: ${logs.length} total logs |
        ${uniqueWorkflows} active workflows |
        ${recentLogs} logs in last 5 minutes${completionStatus}
    `;

    if (logs.length === 0) {
        container.innerHTML = '<div class="no-logs">No logs yet. Waiting for n8n workflows...</div>';
        return;
    }

    if (isNewLog && logs.length > 0) {
        const latestLog = logs[logs.length - 1];
        const div = createLogElement(latestLog, true);
        container.insertBefore(div, container.firstChild);

        setTimeout(() => {
            div.classList.remove('new-log', 'success-entry', 'error-entry');
        }, 800);

        const logElements = container.querySelectorAll('.log-item');
        if (logElements.length > 100) {
            logElements[logElements.length - 1].remove();
        }
    } else {
        container.innerHTML = '';
        logs.slice().reverse().forEach(log => {
            const div = createLogElement(log, false);
            container.appendChild(div);
        });
    }
}

function createLogElement(log, isNew = false) {
    const div = document.createElement('div');

    let logLevel = log.level ? log.level.toLowerCase() : 'info';

    if (log.message && log.message.toLowerCase().includes('error')) {
        logLevel = 'error';
    } else if (log.message && log.message.toLowerCase().includes('success')) {
        logLevel = 'success';
    } else if (log.message && log.message.toLowerCase().includes('warning')) {
        logLevel = 'warning';
    }

    let animationClass = '';
    if (isNew) {
        if (logLevel === 'success') {
            animationClass = ' new-log success-entry';
        } else if (logLevel === 'error') {
            animationClass = ' new-log error-entry';
        } else {
            animationClass = ' new-log';
        }
    }

    div.className = `log-item ${logLevel}${animationClass}`;

    const timestamp = new Date(log.timestamp).toLocaleString();

    let html = `
        <div class="log-item-header">
            <span class="log-title">${log.level || 'Log Entry'}</span>
            <span class="log-timestamp">${timestamp}</span>
        </div>
        <div class="log-item-body">
            <span class="log-status ${logLevel}-label">${logLevel}</span>
    `;

    html += '<div class="log-details">';
    if (log.workflow_id || log.workflow_name || log.node_name) {

        if (log.workflow_name) {
            html += `<p>${log.workflow_name}</p>`;
        }

        if (log.workflow_id && log.workflow_id !== log.workflow_name) {
            html += `<p class="log-id">ID: ${log.workflow_id}</p>`;
        }

        if (log.node_name) {
            html += `<p>Node: ${log.node_name}</p>`;
        }
    }
    html += '</div>';

    if (log.data) {
        if (typeof log.data === 'string') {
            html += `<div class="log-message">${log.data}</div>`;
        } else {
            html += `<pre class="log-code-block">${JSON.stringify(log.data, null, 2)}</pre>`;
        }
    }

    html += '</div>';
    div.innerHTML = html;
    return div;
}

async function loadLogs() {
    try {
        const response = await fetch('http://localhost:8001/logs');
        const data = await response.json();
        allLogs = data.logs || [];
        workflowCompleted = data.workflow_completed || false;
        displayLogsInHome(allLogs);
        displayLogsInLogsPage(allLogs);
    } catch (error) {
        console.error('Error loading logs:', error);
    }
}

async function clearLogs() {
    if (confirm('Are you sure you want to clear all logs? This cannot be undone.')) {
        try {
            allLogs = [];
            displayLogsInHome(allLogs);
            displayLogsInLogsPage(allLogs);

            const response = await fetch('http://localhost:8001/logs', {
                method: 'DELETE'
            });

            if (response.ok) {
                const result = await response.json();
                console.log('Logs cleared successfully:', result);
            } else {
                console.log('Server not responding, but logs cleared locally');
            }

        } catch (error) {
            console.log('Server not available, but logs cleared locally:', error);
        }
    }
}

// Document ready event
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Dashboard initializing...');
    const tabs = document.querySelectorAll('.page-tabs a');
    const pageViews = document.querySelectorAll('.page-view');
    const customToggle = document.getElementById('custom-toggle');
    const customValueInput = document.getElementById('custom-value');
    // Change the initial workflow status from "Checking..." to "Waiting..."
    document.getElementById('workflow-status-text').textContent = 'Waiting...';
    document.getElementById('workflow-sub-text').textContent = 'Ready to start';
    document.getElementById('workflow-indicator').className = 'status-indicator waiting';

    customToggle.addEventListener('change', function() {
        customValueInput.disabled = !this.checked;
    });

    // Single WebSocket connection call
    connectWebSocket();

    // ✅ FIXED: Enable button immediately when dashboard loads
    const startBtn = document.getElementById('start-workflow-btn');
    startBtn.disabled = false;

    // Load initial data after a short delay
    setTimeout(() => {
        if (allLogs.length === 0) {
            loadLogs();
        }
        loadRowsCount();
    }, 2000);

    // ✅ RESTORED: Start workflow status checking (fixed version)
    workflowCheckInterval = setInterval(checkWorkflowStatus, 10000);
    setTimeout(checkWorkflowStatus, 1000); // Initial check after 1 second

    // Tab switching functionality
    tabs.forEach(tab => {
        tab.addEventListener('click', function(event) {
            event.preventDefault();
            tabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            const targetPageId = this.getAttribute('data-page') + '-content';
            pageViews.forEach(view => view.classList.remove('active'));

            const targetPage = document.getElementById(targetPageId);
            if (targetPage) {
                targetPage.classList.add('active');
            }
        });
    });

    // Sheet selector functionality
    const googleDocSelect = document.getElementById('google-doc-select');
    const sheetSelect = document.getElementById('sheet-select');
    const linkSheetBtn = document.getElementById('link-sheet-btn');

    const sheetData = {
        'doc1': ['Q1 Summary', 'Monthly Breakdown', 'Regional Data', 'Projections'],
        'doc2': ['Campaign Overview', 'Social Media', 'Email Campaigns', 'Analytics'],
        'doc3': ['Main Inventory', 'Low Stock Items', 'Supplier Info', 'Order History'],
        'doc4': ['Performance Metrics', 'Reviews', 'Goals', 'Training Records'],
        'doc5': ['Income Statement', 'Expenses', 'Forecasts', 'Variance Analysis']
    };

    googleDocSelect.addEventListener('change', function() {
        const selectedDoc = this.value;
        sheetSelect.innerHTML = '<option value="">Select a sheet</option>';

        if (selectedDoc && sheetData[selectedDoc]) {
            sheetSelect.disabled = false;
            sheetData[selectedDoc].forEach(sheet => {
                const option = document.createElement('option');
                option.value = sheet.toLowerCase().replace(/\s+/g, '-');
                option.textContent = sheet;
                sheetSelect.appendChild(option);
            });
        } else {
            sheetSelect.disabled = true;
            linkSheetBtn.disabled = true;
        }
    });

    sheetSelect.addEventListener('change', function() {
        linkSheetBtn.disabled = !this.value;
    });

    linkSheetBtn.addEventListener('click', function() {
        const selectedDoc = googleDocSelect.options[googleDocSelect.selectedIndex].text;
        const selectedSheet = sheetSelect.options[sheetSelect.selectedIndex].text;

        if (selectedDoc && selectedSheet) {
            alert(`Linking to:\nDocument: ${selectedDoc}\nSheet: ${selectedSheet}`);
        }
    });

    console.log('✅ Dashboard initialization complete - Simple button management active');
});
