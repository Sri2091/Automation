from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime

app = FastAPI(title="n8n Workflow Logger", description="Simple logging server for n8n workflows")

# In-memory storage for logs
logs: List[Dict] = []

class LogEntry(BaseModel):
    message: str
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    node_name: Optional[str] = None
    level: Optional[str] = "info"
    data: Optional[Any] = None

@app.post("/log")
async def receive_log(log_entry: LogEntry):
    """Receive any log entry from n8n workflow"""
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
    
    return {"status": "success", "message": "Log received", "timestamp": timestamp}

@app.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    return {"logs": logs[-limit:] if limit > 0 else logs, "total": len(logs)}

@app.get("/")
async def dashboard():
    """Simple dashboard to view logs"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>n8n Workflow Logs</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .log-entry { background: white; margin: 10px 0; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }
            .log-entry.error { border-left-color: #dc3545; }
            .log-entry.warning { border-left-color: #ffc107; }
            .log-entry.success { border-left-color: #28a745; }
            .timestamp { color: #666; font-size: 0.9em; }
            .level { font-weight: bold; text-transform: uppercase; }
            .level.error { color: #dc3545; }
            .level.warning { color: #ffc107; }
            .level.success { color: #28a745; }
            .level.info { color: #007bff; }
            .workflow-info { color: #666; font-size: 0.9em; margin-top: 5px; }
            .data { background: #f8f9fa; padding: 10px; margin-top: 10px; border-radius: 3px; font-family: monospace; }
            .refresh-btn { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; margin-bottom: 20px; }
            .refresh-btn:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>n8n Workflow Logs</h1>
            <button class="refresh-btn" onclick="loadLogs()">Refresh Logs</button>
            <div id="logs"></div>
        </div>
        
        <script>
            async function loadLogs() {
                try {
                    const response = await fetch('/logs');
                    const data = await response.json();
                    displayLogs(data.logs);
                } catch (error) {
                    console.error('Error loading logs:', error);
                }
            }
            
            function displayLogs(logs) {
                const container = document.getElementById('logs');
                container.innerHTML = '';
                
                logs.reverse().forEach(log => {
                    const div = document.createElement('div');
                    div.className = `log-entry ${log.level}`;
                    
                    let html = `
                        <div class="timestamp">${log.timestamp}</div>
                        <div class="level ${log.level}">[${log.level}]</div>
                        <div class="message">${log.message}</div>
                    `;
                    
                    if (log.workflow_id || log.workflow_name || log.node_name) {
                        html += '<div class="workflow-info">';
                        if (log.workflow_name) html += `Workflow: ${log.workflow_name} `;
                        if (log.workflow_id && log.workflow_id !== log.workflow_name) html += `(${log.workflow_id}) `;
                        if (log.node_name) html += `| Node: ${log.node_name}`;
                        html += '</div>';
                    }
                    
                    if (log.data) {
                        html += `<div class="data">${JSON.stringify(log.data, null, 2)}</div>`;
                    }
                    
                    div.innerHTML = html;
                    container.appendChild(div);
                });
            }
            
            // Load logs on page load
            loadLogs();
            
            // Auto-refresh every 5 seconds
            setInterval(loadLogs, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    uvicorn.run(app, host="0.0.0.0", port=8000)