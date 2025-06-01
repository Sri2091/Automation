from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime
import asyncio
import json

app = FastAPI(title="n8n Workflow Logger", description="Real-time logging server for n8n workflows")

# In-memory storage for logs
logs: List[Dict] = []

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []

# Flag to track if workflow is completed
workflow_completed = False

class LogEntry(BaseModel):
    message: str
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    node_name: Optional[str] = None
    level: Optional[str] = "info"
    data: Optional[Any] = None

async def broadcast_log(log_data: Dict):
    """Broadcast new log to all connected WebSocket clients"""
    if active_connections:
        message = json.dumps({"type": "new_log", "log": log_data})
        # Create a copy of connections to avoid modification during iteration
        connections_copy = active_connections.copy()
        for connection in connections_copy:
            try:
                await connection.send_text(message)
            except:
                # Remove disconnected clients
                if connection in active_connections:
                    active_connections.remove(connection)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    
    # Send existing logs to new client
    try:
        existing_logs = {"type": "all_logs", "logs": logs}
        await websocket.send_text(json.dumps(existing_logs))
        
        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

@app.post("/log")
async def receive_log(log_entry: LogEntry):
    """Receive any log entry from n8n workflow"""
    global workflow_completed
    
    # Check if workflow is already completed - if so, ignore new logs
    if workflow_completed:
        print(f"[IGNORED] Workflow already completed. Ignoring: {log_entry.level}: {log_entry.message}")
        return {"status": "ignored", "message": "Workflow already completed", "reason": "logging_stopped"}
    
    timestamp = datetime.now().isoformat()
    
    # Create log entry with timestamp
    log_data = {
        "timestamp": timestamp,
        "message": log_entry.message,
        "workflow_id": log_entry.workflow_id,
        "workflow_name": log_entry.workflow_name,
        "node_name": log_entry.node_name,
        "level": log_entry.level,
        "data": log_entry.data
    }
    
    # Store log entry
    logs.append(log_data)
    
    # Keep only last 1000 logs to prevent memory issues
    if len(logs) > 1000:
        logs.pop(0)
    
    print(f"[{timestamp}] {log_entry.level.upper()}: {log_entry.message}")
    if log_entry.workflow_id:
        print(f"  Workflow: {log_entry.workflow_name or log_entry.workflow_id}")
    if log_entry.node_name:
        print(f"  Node: {log_entry.node_name}")
    if log_entry.data:
        print(f"  Data: {log_entry.data}")
    print("-" * 50)
    
    # Check if this is a workflow completion message
    if ("workflow completed" in log_entry.level.lower() or 
        "processing completed" in str(log_entry.data).lower() or
        "workflow completed" in log_entry.message.lower()):
        workflow_completed = True
        print("🟢 WORKFLOW COMPLETION DETECTED - Future logs will be ignored")
        
        # Broadcast completion status to all connected clients
        completion_message = {
            "type": "workflow_completed", 
            "message": "Workflow completed - logging stopped",
            "timestamp": timestamp
        }
        if active_connections:
            message = json.dumps(completion_message)
            connections_copy = active_connections.copy()
            for connection in connections_copy:
                try:
                    await connection.send_text(message)
                except:
                    if connection in active_connections:
                        active_connections.remove(connection)
    
    # Broadcast to all connected clients immediately
    await broadcast_log(log_data)
    
    return {"status": "success", "message": "Log received", "timestamp": timestamp}

@app.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    return {
        "logs": logs[-limit:] if limit > 0 else logs, 
        "total": len(logs),
        "workflow_completed": workflow_completed
    }

@app.delete("/logs")
async def clear_logs():
    """Clear all logs and reset workflow completion status"""
    global logs, workflow_completed
    logs.clear()
    workflow_completed = False  # Reset completion status
    
    # Broadcast clear event to all connected clients
    if active_connections:
        message = json.dumps({"type": "logs_cleared"})
        connections_copy = active_connections.copy()
        for connection in connections_copy:
            try:
                await connection.send_text(message)
            except:
                if connection in active_connections:
                    active_connections.remove(connection)
    
    print("All logs cleared and workflow completion status reset")
    return {"status": "success", "message": "All logs cleared and workflow status reset"}

@app.post("/reset")
async def reset_workflow_status():
    """Reset workflow completion status without clearing logs"""
    global workflow_completed
    workflow_completed = False
    
    # Broadcast reset event to all connected clients
    if active_connections:
        message = json.dumps({
            "type": "workflow_reset", 
            "message": "Workflow status reset - logging resumed"
        })
        connections_copy = active_connections.copy()
        for connection in connections_copy:
            try:
                await connection.send_text(message)
            except:
                if connection in active_connections:
                    active_connections.remove(connection)
    
    print("🔄 Workflow completion status reset - logging resumed")
    return {"status": "success", "message": "Workflow status reset - logging resumed"}

@app.get("/status")
async def get_status():
    """Get current workflow status"""
    return {
        "workflow_completed": workflow_completed,
        "total_logs": len(logs),
        "active_connections": len(active_connections)
    }

@app.get("/")
async def dashboard():
    """Real-time dashboard to view logs"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>n8n Workflow Logs</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .log-entry { background: white; margin: 6px 0; padding: 10px; border-radius: 6px; border-left: 3px solid #007bff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            .log-entry.error { border-left-color: #dc3545; }
            .log-entry.warning { border-left-color: #ffc107; }
            .log-entry.success { border-left-color: #28a745; }
            .log-entry[data-message="success"] { border-left-color: #28a745; }
            .log-entry[data-message="error"] { border-left-color: #dc3545; }
            .timestamp { color: #666; font-size: 0.8em; float: right; }
            .level { 
                font-weight: bold; 
                font-size: 1em;
                padding: 5px 8px; 
                border-radius: 3px; 
                display: inline-block;
                margin-bottom: 6px;
                color: white;
                background-color: #17a2b8;
            }
            .level.success-msg { background-color: #28a745; }
            .level.error-msg { background-color: #dc3545; }
            .message { font-size: 1em; margin: 6px 0; }
            .message.success { color: #28a745; font-weight: 600; }
            .workflow-info { 
                color: #495057; 
                font-size: 0.85em; 
                margin: 6px 0;
                padding: 6px;
                background-color: #f8f9fa;
                border-radius: 3px;
                border: 1px solid #e9ecef;
            }
            .workflow-name { font-weight: 600; color: #212529; }
            .workflow-id { color: #6c757d; font-family: monospace; font-size: 0.8em; }
            .node-name { color: #495057; }
            .data { 
                background: #f8f9fa; 
                padding: 8px; 
                margin-top: 6px; 
                border-radius: 3px; 
                font-family: monospace;
                border: 1px solid #e9ecef;
                white-space: pre-wrap;
                font-size: 0.9em;
            }
            .refresh-btn { 
                background: #007bff; 
                color: white; 
                border: none; 
                padding: 12px 24px; 
                border-radius: 6px; 
                cursor: pointer; 
                margin-bottom: 20px;
                margin-right: 10px;
                font-size: 1em;
                transition: background-color 0.2s;
            }
            .refresh-btn:hover { background: #0056b3; }
            .clear-btn { 
                background: #dc3545; 
                color: white; 
                border: none; 
                padding: 12px 24px; 
                border-radius: 6px; 
                cursor: pointer; 
                margin-bottom: 20px;
                margin-right: 10px;
                font-size: 1em;
                transition: background-color 0.2s;
            }
            .clear-btn:hover { background: #c82333; }
            .reset-btn { 
                background: #ffc107; 
                color: black; 
                border: none; 
                padding: 12px 24px; 
                border-radius: 6px; 
                cursor: pointer; 
                margin-bottom: 20px;
                margin-right: 10px;
                font-size: 1em;
                transition: background-color 0.2s;
            }
            .reset-btn:hover { background: #e0a800; }
            .stats { 
                background: white; 
                padding: 15px; 
                border-radius: 8px; 
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .no-logs { 
                text-align: center; 
                color: #6c757d; 
                font-style: italic; 
                padding: 40px;
                background: white;
                border-radius: 8px;
            }
            .connection-status {
                padding: 5px 10px;
                border-radius: 4px;
                font-size: 0.9em;
                margin-left: 10px;
            }
            .connected { background-color: #d4edda; color: #155724; }
            .disconnected { background-color: #f8d7da; color: #721c24; }
            .completed { background-color: #fff3cd; color: #856404; }
            
            .workflow-status {
                padding: 10px 15px;
                border-radius: 6px;
                margin-bottom: 20px;
                font-weight: bold;
            }
            .workflow-active { background-color: #d4edda; color: #155724; }
            .workflow-completed { background-color: #fff3cd; color: #856404; }
            
            /* Animation styles */
            .log-entry.new-log {
                animation: newLogEntrance 0.8s ease-out;
            }
            
            .log-entry.new-log.success-entry {
                animation: newLogEntranceSuccess 0.8s ease-out;
            }
            
            .log-entry.new-log.error-entry {
                animation: newLogEntranceError 0.8s ease-out;
            }
            
            @keyframes newLogEntrance {
                0% {
                    transform: translateY(-20px);
                    opacity: 0;
                }
                100% {
                    transform: translateY(0);
                    opacity: 1;
                }
            }
            
            @keyframes newLogEntranceSuccess {
                0% {
                    transform: translateY(-20px);
                    opacity: 0;
                }
                50% {
                    background: #e8f5e8;
                    box-shadow: 0 0 20px rgba(76, 175, 80, 0.4);
                }
                100% {
                    transform: translateY(0);
                    opacity: 1;
                    background: white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
            }
            
            @keyframes newLogEntranceError {
                0% {
                    transform: translateY(-20px);
                    opacity: 0;
                }
                50% {
                    background: #ffebee;
                    box-shadow: 0 0 20px rgba(244, 67, 54, 0.4);
                }
                100% {
                    transform: translateY(0);
                    opacity: 1;
                    background: white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
            }
            
            .pulse-badge {
                animation: smoothPulse 1s ease-out;
            }
            
            .pulse-badge.success-pulse {
                animation: smoothPulseSuccess 1s ease-out;
            }
            
            .pulse-badge.error-pulse {
                animation: smoothPulseError 1s ease-out;
            }
            
            @keyframes smoothPulse {
                0% { 
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.7);
                }
                50% { 
                    transform: scale(1.05);
                    box-shadow: 0 0 0 8px rgba(40, 167, 69, 0);
                }
                100% { 
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(40, 167, 69, 0);
                }
            }
            
            @keyframes smoothPulseSuccess {
                0% { 
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.7);
                }
                50% { 
                    transform: scale(1.05);
                    box-shadow: 0 0 0 8px rgba(40, 167, 69, 0);
                }
                100% { 
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(40, 167, 69, 0);
                }
            }
            
            @keyframes smoothPulseError {
                0% { 
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.7);
                }
                50% { 
                    transform: scale(1.05);
                    box-shadow: 0 0 0 8px rgba(220, 53, 69, 0);
                }
                100% { 
                    transform: scale(1);
                    box-shadow: 0 0 0 0 rgba(220, 53, 69, 0);
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>n8n Workflow Logs <span id="status" class="connection-status disconnected">Connecting...</span></h1>
            <div id="workflow-status" class="workflow-status workflow-active">Workflow Status: Active - Accepting logs</div>
            <div class="stats" id="stats"></div>
            <button class="refresh-btn" onclick="loadLogs()">Manual Refresh</button>
            <button class="clear-btn" onclick="clearLogs()">Clear All Logs</button>
            <button class="reset-btn" onclick="resetWorkflow()">Reset Workflow Status</button>
            <div id="logs"></div>
        </div>
        
        <script>
            let ws;
            let allLogs = [];
            let workflowCompleted = false;
            
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
                
                ws.onopen = function() {
                    document.getElementById('status').textContent = 'Live';
                    document.getElementById('status').className = 'connection-status connected';
                };
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'all_logs') {
                        allLogs = data.logs;
                        displayLogs(allLogs);
                    } else if (data.type === 'new_log') {
                        allLogs.push(data.log);
                        // Keep only last 1000 logs
                        if (allLogs.length > 1000) {
                            allLogs.shift();
                        }
                        displayLogs(allLogs, true); // Pass true to indicate new log
                        
                        // Pulse the status badge with appropriate color
                        const statusElement = document.getElementById('status');
                        const latestLog = allLogs[allLogs.length - 1];
                        
                        // Remove any existing pulse classes
                        statusElement.classList.remove('pulse-badge', 'success-pulse', 'error-pulse');
                        
                        // Add appropriate pulse class
                        if (latestLog.message.toLowerCase() === 'success' || latestLog.level.toLowerCase() === 'success') {
                            statusElement.classList.add('pulse-badge', 'success-pulse');
                        } else if (latestLog.message.toLowerCase() === 'error' || latestLog.level.toLowerCase() === 'error') {
                            statusElement.classList.add('pulse-badge', 'error-pulse');
                        } else {
                            statusElement.classList.add('pulse-badge');
                        }
                        
                        setTimeout(() => statusElement.classList.remove('pulse-badge', 'success-pulse', 'error-pulse'), 1000);
                    } else if (data.type === 'logs_cleared') {
                        allLogs = [];
                        workflowCompleted = false;
                        updateWorkflowStatus();
                        displayLogs(allLogs);
                    } else if (data.type === 'workflow_completed') {
                        workflowCompleted = true;
                        updateWorkflowStatus();
                        document.getElementById('status').textContent = 'Completed';
                        document.getElementById('status').className = 'connection-status completed';
                    } else if (data.type === 'workflow_reset') {
                        workflowCompleted = false;
                        updateWorkflowStatus();
                        document.getElementById('status').textContent = 'Live';
                        document.getElementById('status').className = 'connection-status connected';
                    }
                };
                
                ws.onclose = function() {
                    document.getElementById('status').textContent = 'Disconnected';
                    document.getElementById('status').className = 'connection-status disconnected';
                    // Reconnect after 3 seconds
                    setTimeout(connectWebSocket, 3000);
                };
                
                ws.onerror = function() {
                    document.getElementById('status').textContent = 'Error';
                    document.getElementById('status').className = 'connection-status disconnected';
                };
            }
            
            function updateWorkflowStatus() {
                const statusElement = document.getElementById('workflow-status');
                if (workflowCompleted) {
                    statusElement.textContent = 'Workflow Status: COMPLETED - Ignoring new logs';
                    statusElement.className = 'workflow-status workflow-completed';
                } else {
                    statusElement.textContent = 'Workflow Status: Active - Accepting logs';
                    statusElement.className = 'workflow-status workflow-active';
                }
            }
            
            async function loadLogs() {
                try {
                    const response = await fetch('/logs');
                    const data = await response.json();
                    allLogs = data.logs;
                    workflowCompleted = data.workflow_completed || false;
                    updateWorkflowStatus();
                    displayLogs(allLogs);
                } catch (error) {
                    console.error('Error loading logs:', error);
                }
            }
            
            function displayLogs(logs, isNewLog = false) {
                const container = document.getElementById('logs');
                const statsContainer = document.getElementById('stats');
                
                if (logs.length === 0) {
                    container.innerHTML = '<div class="no-logs">No logs yet. Waiting for n8n workflows...</div>';
                    statsContainer.innerHTML = 'Stats: 0 total logs';
                    return;
                }
                
                // Update stats
                const uniqueWorkflows = new Set(logs.filter(log => log.workflow_id).map(log => log.workflow_id)).size;
                const recentLogs = logs.filter(log => {
                    const logTime = new Date(log.timestamp);
                    const now = new Date();
                    return (now - logTime) < 300000; // Last 5 minutes
                }).length;
                
                const completionStatus = workflowCompleted ? ' | 🟡 WORKFLOW COMPLETED' : ' | 🟢 WORKFLOW ACTIVE';
                statsContainer.innerHTML = `
                    Stats: ${logs.length} total logs | 
                    ${uniqueWorkflows} active workflows | 
                    ${recentLogs} logs in last 5 minutes${completionStatus}
                `;
                
                // If it's a new log, just add it to the top instead of rebuilding everything
                if (isNewLog && logs.length > 0) {
                    const latestLog = logs[logs.length - 1];
                    const div = createLogElement(latestLog, true);
                    container.insertBefore(div, container.firstChild);
                    
                    // Remove animation class after animation completes
                    setTimeout(() => {
                        div.classList.remove('new-log', 'success-entry', 'error-entry');
                    }, 800);
                    
                    // Remove excess logs from DOM if we have too many
                    const logElements = container.querySelectorAll('.log-entry');
                    if (logElements.length > 100) {
                        logElements[logElements.length - 1].remove();
                    }
                } else {
                    // Full rebuild for initial load
                    container.innerHTML = '';
                    logs.slice().reverse().forEach(log => {
                        const div = createLogElement(log, false);
                        container.appendChild(div);
                    });
                }
            }
            
            function createLogElement(log, isNew = false) {
                const div = document.createElement('div');
                
                // Determine animation class based on message content or level
                let animationClass = '';
                if (isNew) {
                    if (log.message.toLowerCase() === 'success' || log.level.toLowerCase() === 'success') {
                        animationClass = ' new-log success-entry';
                    } else if (log.level.toLowerCase() === 'error' || log.message.toLowerCase() === 'error') {
                        animationClass = ' new-log error-entry';
                    } else {
                        animationClass = ' new-log';
                    }
                }
                
                div.className = `log-entry ${log.level.toLowerCase()}${animationClass}`;
                div.setAttribute('data-message', log.message.toLowerCase());
                
                const timestamp = new Date(log.timestamp).toLocaleString();
                
                let html = `
                    <div class="timestamp">${timestamp}</div>
                    <div class="level ${log.message.toLowerCase() === 'success' ? 'success-msg' : ''} ${log.level.toLowerCase() === 'error' || log.message.toLowerCase() === 'error' ? 'error-msg' : ''}">${log.level}</div>
                    <div class="message ${log.message.toLowerCase() === 'success' ? 'success' : ''}">${log.message}</div>
                `;
                
                // Workflow info display
                if (log.workflow_id || log.workflow_name || log.node_name) {
                    html += '<div class="workflow-info">';
                    
                    if (log.workflow_name) {
                        html += `<div class="workflow-name">${log.workflow_name}</div>`;
                    }
                    
                    if (log.workflow_id && log.workflow_id !== log.workflow_name) {
                        html += `<div class="workflow-id">ID: ${log.workflow_id}</div>`;
                    }
                    
                    if (log.node_name) {
                        html += `<div class="node-name">Node: ${log.node_name}</div>`;
                    }
                    
                    html += '</div>';
                }
                
                // Data display
                if (log.data) {
                    html += `<div class="data">${JSON.stringify(log.data, null, 2)}</div>`;
                }
                
                div.innerHTML = html;
                return div;
            }
            
            async function clearLogs() {
                if (confirm('Are you sure you want to clear all logs and reset workflow status? This cannot be undone.')) {
                    try {
                        const response = await fetch('/logs', {
                            method: 'DELETE'
                        });
                        const result = await response.json();
                        
                        if (result.status === 'success') {
                            allLogs = [];
                            workflowCompleted = false;
                            updateWorkflowStatus();
                            displayLogs(allLogs);
                        }
                    } catch (error) {
                        console.error('Error clearing logs:', error);
                        alert('Failed to clear logs. Please try again.');
                    }
                }
            }
            
            async function resetWorkflow() {
                if (confirm('Are you sure you want to reset the workflow status? This will resume logging.')) {
                    try {
                        const response = await fetch('/reset', {
                            method: 'POST'
                        });
                        const result = await response.json();
                        
                        if (result.status === 'success') {
                            workflowCompleted = false;
                            updateWorkflowStatus();
                            document.getElementById('status').textContent = 'Live';
                            document.getElementById('status').className = 'connection-status connected';
                        }
                    } catch (error) {
                        console.error('Error resetting workflow:', error);
                        alert('Failed to reset workflow status. Please try again.');
                    }
                }
            }
            
            // Initialize WebSocket connection
            connectWebSocket();
            
            // Fallback: load logs on page load if WebSocket fails
            setTimeout(() => {
                if (allLogs.length === 0) {
                    loadLogs();
                }
            }, 2000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)