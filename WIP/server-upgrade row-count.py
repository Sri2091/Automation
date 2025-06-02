from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware 
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime
import asyncio
import json
import re

app = FastAPI(title="n8n Workflow Logger", description="Real-time logging server for n8n workflows")

# ✅ ADD CORS MIDDLEWARE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# In-memory storage for logs
logs: List[Dict] = []

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []

# Flag to track if workflow is completed
workflow_completed = False

# Row tracking variables
rows_count = 0
rows_completed = 0  # NEW: Track completed rows

# Processing status tracking
is_processing = False
has_error = False
processing_started = False
workflow_triggered = False  # Track when workflow starts


class LogEntry(BaseModel):
    message: str
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    node_name: Optional[str] = None
    level: Optional[str] = "info"
    data: Optional[Any] = None

class RowsData(BaseModel):
    total_rows: int
    processed_rows: Optional[int] = 0
    message: Optional[str] = None

class CompletedRowData(BaseModel):
    completed_rows: int
    row_number: Optional[int] = None
    gen_col: Optional[str] = None
    message: Optional[str] = None

async def broadcast_log(log_data: Dict):
    """Broadcast new log to all connected WebSocket clients"""
    if active_connections:
        try:
            # Ensure all data is JSON serializable
            safe_log_data = {
                "type": "new_log", 
                "log": {
                    "timestamp": str(log_data.get("timestamp", "")),
                    "message": str(log_data.get("message", "")),
                    "workflow_id": str(log_data.get("workflow_id", "")) if log_data.get("workflow_id") else None,
                    "workflow_name": str(log_data.get("workflow_name", "")) if log_data.get("workflow_name") else None,
                    "node_name": str(log_data.get("node_name", "")) if log_data.get("node_name") else None,
                    "level": str(log_data.get("level", "info")),
                    "data": log_data.get("data"),  # Keep as-is, should be serializable
                    "hidden": bool(log_data.get("hidden", False))
                }
            }
            message = json.dumps(safe_log_data)
            connections_copy = active_connections.copy()
            for connection in connections_copy:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print(f"❌ Error sending to WebSocket client: {e}")
                    if connection in active_connections:
                        active_connections.remove(connection)
        except Exception as e:
            print(f"❌ Error in broadcast_log: {e}")

async def broadcast_status_update(status_type: str, data: Dict):
    """Broadcast status updates to all connected clients"""
    if active_connections:
        try:
            # Ensure all data is JSON serializable
            safe_data = {"type": status_type}
            for key, value in data.items():
                if callable(value):
                    print(f"⚠️ Warning: Skipping function object in broadcast: {key}")
                    continue
                safe_data[key] = value
            
            message = json.dumps(safe_data)
            connections_copy = active_connections.copy()
            for connection in connections_copy:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print(f"❌ Error sending to WebSocket client: {e}")
                    if connection in active_connections:
                        active_connections.remove(connection)
        except Exception as e:
            print(f"❌ Error in broadcast_status_update: {e}")

async def auto_reset_workflow():
    """Automatically reset workflow status after 2 seconds"""
    global workflow_completed, is_processing, has_error, processing_started, workflow_triggered
    
    # Wait for 2 seconds
    await asyncio.sleep(2)
    
    # Reset the workflow status
    workflow_completed = False
    is_processing = False
    has_error = False
    processing_started = False
    workflow_triggered = False
    
    # Broadcast reset event to all connected clients
    await broadcast_status_update("workflow_reset", {
        "message": "Workflow status auto-reset - logging resumed",
        "timestamp": datetime.now().isoformat()
    })
    
    print("🔄 AUTOMATIC RESET: Workflow completion status reset - logging resumed")

def should_hide_log(log_entry: LogEntry) -> bool:
    """Determine if log should be hidden based on processing state"""
    global workflow_triggered, processing_started
    
    # If workflow hasn't been triggered yet, hide all logs
    if not workflow_triggered:
        return True
    
    # If processing hasn't started, hide logs until "Loop Started" appears
    if not processing_started:
        if ("loop started" in log_entry.level.lower() or 
            "loop started" in log_entry.message.lower() or
            (log_entry.data and "loop started" in str(log_entry.data).lower())):
            return False  # Don't hide this log, it's the start signal
        return True  # Hide other logs
    
    # Once processing started, show all logs
    return False

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    
    # Send existing logs to new client (filtered)
    try:
        filtered_logs = [log for log in logs if not log.get('hidden', False)]
        existing_logs = {"type": "all_logs", "logs": filtered_logs}
        await websocket.send_text(json.dumps(existing_logs))
        
        # Send current status - ensure all values are JSON serializable
        status_data = {
            "type": "status_update",
            "is_processing": bool(is_processing),
            "has_error": bool(has_error),
            "processing_started": bool(processing_started),
            "workflow_triggered": bool(workflow_triggered),
            "rows_completed": int(rows_completed),
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_text(json.dumps(status_data))
        
        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)

@app.post("/log")
async def receive_log(log_entry: LogEntry):
    """Receive any log entry from n8n workflow"""
    global workflow_completed, is_processing, has_error, processing_started
    
    # Check if workflow is already completed - if so, ignore new logs
    if workflow_completed:
        print(f"[IGNORED] Workflow already completed. Ignoring: {log_entry.level}: {log_entry.message}")
        return {"status": "ignored", "message": "Workflow already completed", "reason": "logging_stopped"}
    
    timestamp = datetime.now().isoformat()
    
    # Check for error conditions
    is_error_log = (
        "error" in log_entry.level.lower() or
        "error" in log_entry.message.lower() or
        (log_entry.data and "error" in str(log_entry.data).lower()) or
        "failed" in log_entry.message.lower() or
        "exception" in log_entry.message.lower()
    )
    
    # Check for loop started (processing begins)
    is_loop_start = (
        "loop started" in log_entry.level.lower() or
        "loop started" in log_entry.message.lower() or
        (log_entry.data and "loop started" in str(log_entry.data).lower())
    )
    
    # Update processing states
    if is_error_log and not has_error:
        has_error = True
        await broadcast_status_update("error_detected", {
            "message": "Error detected in workflow",
            "timestamp": timestamp
        })
        print("🔴 ERROR DETECTED - Status changed to error pulse")
    
    if is_loop_start and not processing_started:
        processing_started = True
        is_processing = True
        has_error = False  # Reset error state when processing starts
        await broadcast_status_update("processing_started", {
            "message": "Processing started - green pulse activated",
            "timestamp": timestamp
        })
        print("🟢 PROCESSING STARTED - Status changed to green pulse")
    
    # Determine if this log should be hidden
    should_hide = should_hide_log(log_entry)
    
    # Create log entry with timestamp
    log_data = {
        "timestamp": timestamp,
        "message": log_entry.message,
        "workflow_id": log_entry.workflow_id,
        "workflow_name": log_entry.workflow_name,
        "node_name": log_entry.node_name,
        "level": log_entry.level,
        "data": log_entry.data,
        "hidden": should_hide
    }

    # Store log entry (always store, but mark if hidden)
    logs.append(log_data)
    
    # Keep only last 1000 logs to prevent memory issues
    if len(logs) > 1000:
        logs.pop(0)
    
    if should_hide:
        print(f"[HIDDEN] {log_entry.level.upper()}: {log_entry.message}")
    else:
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
        is_processing = False
        print("🟢 WORKFLOW COMPLETION DETECTED - Future logs will be ignored")
        print("⏰ Will automatically reset in 2 seconds...")
        
        # Broadcast completion status to all connected clients
        await broadcast_status_update("workflow_completed", {
            "message": "Workflow completed - logging stopped",
            "timestamp": timestamp
        })
        
        # Schedule automatic reset after 2 seconds
        asyncio.create_task(auto_reset_workflow())
    
    # Broadcast to all connected clients immediately (only if not hidden)
    if not should_hide:
        await broadcast_log(log_data)
    
    return {"status": "success", "message": "Log received", "timestamp": timestamp, "hidden": should_hide}

@app.post("/workflow/triggered")
async def workflow_triggered():
    """Called when workflow is manually triggered"""
    global workflow_triggered, is_processing, has_error, processing_started
    
    workflow_triggered = True
    is_processing = False  # Will turn true when loop starts
    has_error = False
    processing_started = False
    
    timestamp = datetime.now().isoformat()
    
    await broadcast_status_update("workflow_triggered", {
        "message": "Workflow triggered - waiting for processing to start",
        "timestamp": timestamp
    })
    
    print("🚀 WORKFLOW TRIGGERED - Logs will now be shown when processing starts")
    return {"status": "success", "message": "Workflow trigger acknowledged", "timestamp": timestamp}

@app.post("/rows/completed")
async def update_completed_rows(completed_data: CompletedRowData):
    """Update the number of completed rows"""
    global rows_completed, is_processing
    
    rows_completed = completed_data.completed_rows
    
    timestamp = datetime.now().isoformat()
    
    # Check if all rows are completed
    if rows_completed >= rows_count and rows_count > 0:
        is_processing = False
        await broadcast_status_update("processing_completed", {
            "message": "All rows completed - processing finished",
            "timestamp": timestamp
        })
        print("✅ ALL ROWS COMPLETED - Processing finished")
    
    print(f"[{timestamp}] Completed rows updated: {rows_completed}/{rows_count}")
    if completed_data.row_number:
        print(f"  Row Number: {completed_data.row_number}")
    if completed_data.gen_col:
        print(f"  Gen-col: {completed_data.gen_col}")
    
    # Broadcast to all connected clients
    if active_connections:
        percentage = (rows_completed / rows_count * 100) if rows_count > 0 else 0
        message_text = completed_data.message or f"Completed {rows_completed}/{rows_count} rows"
        if completed_data.row_number and completed_data.gen_col:
            message_text += f" (Row {completed_data.row_number}, Gen-col: {completed_data.gen_col})"
        
        await broadcast_status_update("rows_completed_updated", {
            "total_rows": rows_count,
            "rows_completed": rows_completed,
            "percentage": round(percentage, 1),
            "row_number": completed_data.row_number,
            "gen_col": completed_data.gen_col,
            "message": message_text,
            "timestamp": timestamp
        })
    
    return {
        "status": "success", 
        "total_rows": rows_count,
        "rows_completed": rows_completed,
        "percentage": round(percentage, 1) if rows_count > 0 else 0,
        "timestamp": timestamp
    }

@app.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs (filtered)"""
    # Filter out hidden logs
    visible_logs = [log for log in logs if not log.get('hidden', False)]
    return {
        "logs": visible_logs[-limit:] if limit > 0 else visible_logs, 
        "total": len(visible_logs),
        "total_including_hidden": len(logs),
        "workflow_completed": workflow_completed
    }

@app.delete("/logs")
async def clear_logs():
    """Clear all logs and reset workflow completion status"""
    global logs, workflow_completed, is_processing, has_error, processing_started, workflow_triggered, rows_completed
    
    logs.clear()
    workflow_completed = False
    is_processing = False
    has_error = False
    processing_started = False
    workflow_triggered = False
    rows_completed = 0
    
    # Broadcast clear event to all connected clients
    await broadcast_status_update("logs_cleared", {
        "message": "All logs cleared and status reset",
        "timestamp": datetime.now().isoformat()
    })
    
    print("All logs cleared and all statuses reset")
    return {"status": "success", "message": "All logs cleared and all statuses reset"}

@app.post("/reset")
async def reset_workflow_status():
    """Reset workflow completion status without clearing logs"""
    global workflow_completed, is_processing, has_error, processing_started, workflow_triggered
    
    workflow_completed = False
    is_processing = False
    has_error = False
    processing_started = False
    workflow_triggered = False
    
    # Broadcast reset event to all connected clients
    await broadcast_status_update("workflow_reset", {
        "message": "Workflow status reset - logging resumed",
        "timestamp": datetime.now().isoformat()
    })
    
    print("🔄 Workflow completion status reset - logging resumed")
    return {"status": "success", "message": "Workflow status reset - logging resumed"}

@app.get("/status")
async def get_status():
    """Get current workflow status"""
    return {
        "workflow_completed": workflow_completed,
        "workflow_triggered": workflow_triggered,
        "processing_started": processing_started,
        "is_processing": is_processing,
        "has_error": has_error,
        "total_logs": len(logs),
        "visible_logs": len([log for log in logs if not log.get('hidden', False)]),
        "active_connections": len(active_connections),
        "rows_completed": rows_completed
    }


@app.post("/rows/set")
async def set_rows_count(rows_data: RowsData):
    global rows_count  # ✅ Only need this
    
    rows_count = rows_data.total_rows
    

@app.get("/rows")
async def get_rows_count():

    return {
        
        "total_rows": rows_count,
        "completed_rows": rows_completed,
        "completed_percentage": round(completed_percentage, 1),
    }

@app.delete("/rows")
async def reset_rows_count():
    """Reset rows count (usually when workflow starts fresh)"""
    global rows_count, rows_completed
    
    rows_count = 0
    rows_completed = 0
    
    timestamp = datetime.now().isoformat()
    
    # Broadcast reset to all connected clients
    await broadcast_status_update("rows_reset", {
        "message": "Rows count reset for new workflow",
        "timestamp": timestamp
    })
    
    print(f"[{timestamp}] Rows count reset")
    return {"status": "success", "message": "Rows count reset", "timestamp": timestamp}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)