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

async def auto_reset_workflow():
    """Automatically reset workflow status after 2 seconds"""
    global workflow_completed
    
    # Wait for 2 seconds
    await asyncio.sleep(2)
    
    # Reset the workflow status
    workflow_completed = False
    
    # Broadcast reset event to all connected clients
    if active_connections:
        message = json.dumps({
            "type": "workflow_reset", 
            "message": "Workflow status auto-reset - logging resumed",
            "timestamp": datetime.now().isoformat()
        })
        connections_copy = active_connections.copy()
        for connection in connections_copy:
            try:
                await connection.send_text(message)
            except:
                if connection in active_connections:
                    active_connections.remove(connection)
    
    print("🔄 AUTOMATIC RESET: Workflow completion status reset - logging resumed")

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
        print("⏰ Will automatically reset in 2 seconds...")
        
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
        
        # Schedule automatic reset after 2 seconds
        asyncio.create_task(auto_reset_workflow())
    
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)