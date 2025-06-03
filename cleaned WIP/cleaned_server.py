from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware 
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from contextlib import asynccontextmanager
from datetime import datetime
import asyncio
import json
import logging
import uuid

# Set up proper logging instead of print statements
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for logs
logs: List[Dict] = []

# WebSocket connections for real-time updates
active_connections: List[WebSocket] = []

# Simple workflow state - only track if completed
workflow_completed = False
current_workflow_id: Optional[str] = None

# Row tracking
rows_count = 0
rows_completed = 0

# Task tracking for auto-reset
auto_reset_task: Optional[asyncio.Task] = None
# Background task for cleanup
cleanup_task: Optional[asyncio.Task] = None


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


async def broadcast_to_clients(message_type: str, data: Dict):
    """Broadcast message to all connected WebSocket clients"""
    if not active_connections:
        return
    
    message = json.dumps({"type": message_type, **data})
    disconnected_clients = []
    
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except Exception as e:
            logger.error(f"Error sending to client: {e}")
            disconnected_clients.append(connection)
    
    # Remove disconnected clients
    for client in disconnected_clients:
        if client in active_connections:
            active_connections.remove(client)


async def cleanup_dead_connections():
    """Periodically check and remove dead WebSocket connections"""
    while True:
        await asyncio.sleep(60)  # Check every minute
        
        if not active_connections:
            continue
            
        logger.info(f"Checking {len(active_connections)} WebSocket connections...")
        disconnected_clients = []
        
        for connection in active_connections:
            try:
                # Send a ping message
                await connection.send_text(json.dumps({"type": "ping"}))
            except Exception:
                disconnected_clients.append(connection)
        
        # Remove dead connections
        for client in disconnected_clients:
            if client in active_connections:
                active_connections.remove(client)
                logger.info(f"Removed dead connection. Active connections: {len(active_connections)}")


async def auto_reset_workflow(workflow_id: str):
    """Automatically reset workflow status after 2 seconds"""
    global workflow_completed, current_workflow_id
    
    await asyncio.sleep(2)
    
    # Only reset if we're still in the same workflow completion state
    if workflow_completed and current_workflow_id == workflow_id:
        workflow_completed = False
        current_workflow_id = None
        
        await broadcast_to_clients("workflow_reset", {
            "message": "Workflow status auto-reset - logging resumed",
            "timestamp": datetime.now().isoformat()
        })
        
        logger.info(f"Workflow {workflow_id} completion status auto-reset - logging resumed")
    else:
        logger.info(f"Skip reset for workflow {workflow_id} - state changed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    global cleanup_task
    
    # Startup
    cleanup_task = asyncio.create_task(cleanup_dead_connections())
    logger.info("Started WebSocket connection cleanup task")
    
    yield
    
    # Shutdown
    global auto_reset_task
    
    # Cancel cleanup task
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    
    # Cancel auto-reset task if running
    if auto_reset_task and not auto_reset_task.done():
        auto_reset_task.cancel()
        try:
            await auto_reset_task
        except asyncio.CancelledError:
            pass
        logger.info("Cancelled auto-reset task")
    
    # Close all WebSocket connections
    for connection in active_connections:
        try:
            await connection.close()
        except Exception:
            pass
    
    logger.info("Server shutdown - cleaned up connections")


# Create FastAPI app with lifespan handler
app = FastAPI(
    title="n8n Workflow Logger", 
    description="Real-time logging server for n8n workflows",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"New WebSocket connection. Total connections: {len(active_connections)}")
    
    try:
        # Send existing logs to new client
        await websocket.send_text(json.dumps({
            "type": "all_logs",
            "logs": logs
        }))
        
        # Send current row status
        await websocket.send_text(json.dumps({
            "type": "rows_updated",
            "total_rows": rows_count,
            "processed_rows": 0,
            "message": f"{rows_count} rows ready to process" if rows_count > 0 else "No rows loaded"
        }))
        
        # Send completed rows status
        if rows_completed > 0:
            percentage = (rows_completed / rows_count * 100) if rows_count > 0 else 0
            await websocket.send_text(json.dumps({
                "type": "rows_completed_updated",
                "rows_completed": rows_completed,
                "total_rows": rows_count,
                "percentage": round(percentage, 1)
            }))
        
        # Keep connection alive
        while True:
            message = await websocket.receive_text()
            # Handle ping responses
            if message == "pong":
                continue
            
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(active_connections)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)


@app.post("/log")
async def receive_log(log_entry: LogEntry):
    """Receive log entry from n8n workflow"""
    global workflow_completed, current_workflow_id, auto_reset_task
    
    # If workflow is completed, ignore new logs
    if workflow_completed:
        logger.info(f"[IGNORED] Workflow completed. Ignoring: {log_entry.level}: {log_entry.message}")
        return {"status": "ignored", "message": "Workflow already completed"}
    
    timestamp = datetime.now().isoformat()
    
    # Set current workflow ID if provided
    if log_entry.workflow_id and not current_workflow_id:
        current_workflow_id = log_entry.workflow_id
    
    # Create log entry
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
    
    # Keep only last 1000 logs
    if len(logs) > 1000:
        logs.pop(0)
    
    # Log to console
    logger.info(f"{log_entry.level.upper()}: {log_entry.message}")
    if log_entry.workflow_id:
        logger.info(f"  Workflow: {log_entry.workflow_name or log_entry.workflow_id}")
    
    # Check for errors (more precise checking)
    is_error = False
    if log_entry.level and "error" in log_entry.level.lower():
        is_error = True
    elif any(word in log_entry.message.lower() for word in ["error", "failed", "exception"]):
        is_error = True
    
    if is_error:
        await broadcast_to_clients("error_detected", {
            "message": "Error detected in workflow",
            "timestamp": timestamp
        })
    
    # Check for workflow completion
    if "workflow completed" in log_entry.level.lower() or "workflow completed" in log_entry.message.lower():
        workflow_completed = True
        logger.info("Workflow completed - future logs will be ignored for 2 seconds")
        
        await broadcast_to_clients("workflow_completed", {
            "message": "Workflow completed",
            "timestamp": timestamp
        })
        
        # Cancel previous auto-reset if exists
        if auto_reset_task and not auto_reset_task.done():
            auto_reset_task.cancel()
        
        # Schedule automatic reset with workflow ID
        workflow_id_for_reset = current_workflow_id or str(uuid.uuid4())
        auto_reset_task = asyncio.create_task(auto_reset_workflow(workflow_id_for_reset))
    
    # Broadcast log to all clients
    await broadcast_to_clients("new_log", {"log": log_data})
    
    return {"status": "success", "message": "Log received", "timestamp": timestamp}


@app.post("/workflow/triggered")
async def workflow_triggered():
    """Called when workflow is manually triggered"""
    global current_workflow_id
    
    # Generate new workflow ID for this run
    current_workflow_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    await broadcast_to_clients("workflow_triggered", {
        "message": "Workflow triggered",
        "workflow_id": current_workflow_id,
        "timestamp": timestamp
    })
    
    logger.info(f"Workflow triggered with ID: {current_workflow_id}")
    return {
        "status": "success", 
        "message": "Workflow trigger acknowledged", 
        "workflow_id": current_workflow_id,
        "timestamp": timestamp
    }


@app.post("/rows/set")
async def set_rows_count(rows_data: RowsData):
    """Set the total number of rows to process"""
    global rows_count
    
    # Validate rows count
    rows_count = max(0, rows_data.total_rows)
    timestamp = datetime.now().isoformat()
    
    logger.info(f"Rows count set to: {rows_count}")
    
    await broadcast_to_clients("rows_updated", {
        "total_rows": rows_count,
        "processed_rows": rows_data.processed_rows or 0,
        "message": rows_data.message or f"{rows_count} rows ready to process",
        "timestamp": timestamp
    })
    
    return {
        "status": "success",
        "total_rows": rows_count,
        "timestamp": timestamp
    }


@app.post("/rows/completed")
async def update_completed_rows(completed_data: CompletedRowData):
    """Update the number of completed rows"""
    global rows_completed
    
    # Validate completed rows (ensure it's between 0 and rows_count)
    rows_completed = max(0, min(completed_data.completed_rows, rows_count))
    
    timestamp = datetime.now().isoformat()
    percentage = (rows_completed / rows_count * 100) if rows_count > 0 else 0
    
    logger.info(f"Completed rows: {rows_completed}/{rows_count} ({percentage:.1f}%)")
    if completed_data.row_number:
        logger.info(f"  Row Number: {completed_data.row_number}")
    if completed_data.gen_col:
        logger.info(f"  Gen-col: {completed_data.gen_col}")
    
    # Check if all rows are completed (only broadcast once)
    if rows_completed >= rows_count and rows_count > 0:
        # Only send if we haven't already marked workflow as completed
        if not workflow_completed:
            await broadcast_to_clients("processing_completed", {
                "message": "All rows completed",
                "timestamp": timestamp
            })
    
    # Broadcast update
    await broadcast_to_clients("rows_completed_updated", {
        "rows_completed": rows_completed,
        "total_rows": rows_count,
        "percentage": round(percentage, 1),
        "row_number": completed_data.row_number,
        "gen_col": completed_data.gen_col,
        "message": completed_data.message,
        "timestamp": timestamp
    })
    
    return {
        "status": "success",
        "rows_completed": rows_completed,
        "total_rows": rows_count,
        "percentage": round(percentage, 1),
        "timestamp": timestamp
    }


@app.get("/rows")
async def get_rows_count():
    """Get current rows count and completion status"""
    percentage = (rows_completed / rows_count * 100) if rows_count > 0 else 0
    
    return {
        "total_rows": rows_count,
        "completed_rows": rows_completed,
        "completed_percentage": round(percentage, 1)
    }


@app.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    return {
        "logs": logs[-limit:] if limit > 0 else logs,
        "total": len(logs),
        "workflow_completed": workflow_completed,
        "current_workflow_id": current_workflow_id
    }


@app.delete("/logs")
async def clear_logs():
    """Clear all logs and reset status"""
    global logs, workflow_completed, rows_completed, current_workflow_id, auto_reset_task
    
    # Cancel auto-reset task if running
    if auto_reset_task and not auto_reset_task.done():
        auto_reset_task.cancel()
    
    logs.clear()
    workflow_completed = False
    rows_completed = 0
    current_workflow_id = None
    
    await broadcast_to_clients("logs_cleared", {
        "message": "All logs cleared",
        "timestamp": datetime.now().isoformat()
    })
    
    logger.info("All logs cleared and status reset")
    return {"status": "success", "message": "All logs cleared"}


@app.delete("/rows")
async def reset_rows_count():
    """Reset rows count"""
    global rows_count, rows_completed
    
    rows_count = 0
    rows_completed = 0
    
    await broadcast_to_clients("rows_reset", {
        "message": "Rows count reset",
        "timestamp": datetime.now().isoformat()
    })
    
    logger.info("Rows count reset")
    return {"status": "success", "message": "Rows count reset"}


@app.get("/status")
async def get_status():
    """Get current system status"""
    return {
        "workflow_completed": workflow_completed,
        "current_workflow_id": current_workflow_id,
        "total_logs": len(logs),
        "active_connections": len(active_connections),
        "rows_count": rows_count,
        "rows_completed": rows_completed,
        "auto_reset_pending": auto_reset_task and not auto_reset_task.done() if auto_reset_task else False
    }


# Mount static files (for serving HTML) - COMMENTED OUT AS REQUESTED
# app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)