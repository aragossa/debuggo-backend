import os
import uuid
import json
from datetime import timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, BackgroundTasks, Response, Query, File, UploadFile, Body
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Dict, List, Optional
from pydantic import BaseModel, UUID4
from datetime import datetime
import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
import jwt
import redis
from kafka import KafkaProducer, KafkaConsumer
import threading
from threading import Thread
import time
import sys
import logging
import traceback
from pathlib import Path
import requests
from auroqa.models.user import User, UserCreate, UserLogin, Token, OAuthUserInfo
from auroqa.models.client import Client, ClientCreate
from auroqa.models.test import GenerateStepsRequest
from auroqa.Utils.System import System
import os as env_os

# Phase 3 Integration: Use wrapper classes if enabled
if env_os.getenv('USE_PHASE3', 'true').lower() == 'true':
    from auroqa.Utils.BrowserAutomation.EnhancedTestRunner import EnhancedTestRunner as TestRunner
    from auroqa.Utils.AIHelper.EnhancedAIHelper import EnhancedAIHelper as AIHelper
    logger_init = logging.getLogger(__name__)
    logger_init.info("✓ Phase 3 integration enabled: Using EnhancedTestRunner and EnhancedAIHelper")
else:
    from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
    logger_init = logging.getLogger(__name__)
    logger_init.info("⊘ Phase 3 integration disabled: Using standard TestRunner")

from auroqa.Utils.BrowserAutomation.BrowserAutomation import BrowserAutomation
from auroqa.Utils.Connectors.KafkaMessageConsumer import KafkaMessageConsumer
from auroqa.Utils.Connectors.KafkaMessageProducer import KafkaMessageProducer
from auroqa.Utils.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from auroqa.Utils.oauth import oauth, google, get_user_info_from_google
from auroqa.models.crud import create_user, get_user_by_email, get_client_test_cases
from auroqa.fetch_test_steps import get_test_data_from_db_helper
from auroqa.test_case_builder import get_tests_tree, build_tree
from jose import JWTError, jwt
import asyncio
from auroqa.Utils.Connectors.db_utils import get_db_connection, return_db_connection, init_db_pool, get_db_connection_context, get_pool_status, close_db_pool
from auroqa.Services.AgentMonitoring import AgentMonitoring
from auroqa.Services.TestExecutionService import TestExecutionService
from auroqa.Services.PerformanceOptimizer import PerformanceOptimizer
from auroqa.Services.FineTuningService import FineTuningService, FineTuningDataCollector
from auroqa.Services.ContinuousImprovement import ContinuousImprovement
from auroqa.Services.PlanningCollector import PlanningCollector
from auroqa.Services.GenerationCostAnalytics import GenerationCostAnalytics
from auroqa.api.suite_endpoints import router as suite_router
from auroqa.api.variable_endpoints import router as variable_router
from auroqa.api.execution_plan_endpoints import router as execution_plan_router
from auroqa.api.scheduler_endpoints import router as scheduler_router
from auroqa.api.execution_endpoints import router as execution_router
from auroqa.api.retry_endpoints import router as retry_router
from auroqa.api.metrics_endpoints import router as metrics_router
from auroqa.api.quick_run_endpoints import router as quick_run_router
import signal
import atexit

# Initialize connection pool
db_pool = None

# Initialize logger
logger = logging.getLogger(__name__)

# Configure logging
handlers = [logging.StreamHandler(sys.stdout)]

# Add file logging only for local environment
if os.getenv('ENVIRONMENT', 'development') != 'production':
    # Use 'w' mode to overwrite log file on restart
    file_handler = logging.FileHandler('auroqa.log', mode='w')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    handlers.append(file_handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers,
    force=True  # Force reconfiguration
)

# Global shutdown flag
shutdown_flag = False

def cleanup_resources():
    """Clean up all resources before shutdown."""
    global shutdown_flag
    if shutdown_flag:
        return  # Already cleaning up
    
    shutdown_flag = True
    logger.info("🧹 Starting graceful shutdown and resource cleanup...")
    
    try:
        # Close database pool
        logger.info("📦 Closing database connection pool...")
        close_db_pool()
        
        # TODO: Add Kafka consumer shutdown here
        # if hasattr(app.state, 'kafka_consumer'):
        #     app.state.kafka_consumer.stop()
        
        # TODO: Cancel any background tasks
        # for task in asyncio.all_tasks():
        #     task.cancel()
        
        logger.info("✅ Resource cleanup completed successfully")
    except Exception as e:
        logger.error(f"❌ Error during cleanup: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals from Docker/system."""
    logger.info(f"🚨 Received signal {signum} ({'SIGTERM' if signum == 15 else 'SIGINT'}), initiating graceful shutdown")
    cleanup_resources()
    logger.info("👋 Exiting application")
    sys.exit(0)

# Register signal handlers for proper Docker shutdown
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Docker stop
atexit.register(cleanup_resources)             # Fallback cleanup

class UpdateTestStepAction(BaseModel):
    action: Optional[str] = None
    value: Optional[str] = None
    element_path: Optional[str] = None
    css_selector: Optional[str] = None
    description: Optional[str] = None

class StepOrderUpdate(BaseModel):
    test_case_id: int
    step_orders: List[Dict[str, int]]

class UserClientUpdate(BaseModel):
    client_id: Optional[str] = None

class TestElementLocatorRequest(BaseModel):
    element_path: str
    environment_id: Optional[str] = None
    test_case_id: Optional[int] = None

class CreateTestStepRequest(BaseModel):
    test_case_id: int
    description: str
    action: str
    element_path: Optional[str] = None
    value: Optional[str] = None
    path_type: Optional[str] = "xpath"
    expected_result: Optional[str] = None

class CreateTestGroupRequest(BaseModel):
    name: str
    parent_id: Optional[int] = None
    project_id: Optional[UUID4] = None

class UpdateTestGroupRequest(BaseModel):
    name: str

class MoveTestCaseRequest(BaseModel):
    test_case_id: int
    target_group_id: Optional[int] = None

class CreateTestCaseRequest(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    project_id: Optional[UUID4] = None
    test_type: str = 'ui'  # Default to 'ui' type

class UpdateTestCaseRequest(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    test_type: Optional[str] = None

class CreateTestExecutionRequest(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: UUID4

class UpdateTestExecutionStatusRequest(BaseModel):
    status: str

class AssignTestRunRequest(BaseModel):
    test_run_id: int
    execution_id: int

class CreateUserRequestRequest(BaseModel):
    title: str
    description: str
    request_type: str  # bug, feature, improvement, question
    priority: Optional[str] = 'medium'  # low, medium, high, critical
    browser_info: Optional[str] = None
    page_url: Optional[str] = None

class UpdateUserRequestStatusRequest(BaseModel):
    status: str  # new, in_progress, resolved, closed, rejected
    admin_notes: Optional[str] = None
    priority: Optional[str] = None

from auroqa.dependencies import get_current_user, oauth2_scheme

# app = FastAPI()
kafka_consumer = None
consumer_thread = None
UPLOAD_DIRECTORY = "./uploaded_files"
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

# Add CORS middleware
origins = [
    "http://localhost",
    "http://18.194.44.160:3000",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:9000",
    "http://18.184.65.241",
    "http://95.217.211.91",
    "http://debuggo.app",
    "https://debuggo.app",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global db_pool, kafka_consumer, consumer_thread
    system = System()
    
    # Initialize database pool using db_utils
    try:
        # Set environment variables for db_utils
        os.environ["DB_HOST"] = system.db_host
        os.environ["DB_NAME"] = system.db_name
        os.environ["DB_USER"] = system.db_user
        os.environ["DB_PASSWORD"] = system.db_password
        os.environ["DB_PORT"] = system.db_port
        
        # Initialize the database pool
        init_db_pool()
        
        # Get the db_pool reference from db_utils
        from auroqa.Utils.Connectors.db_utils import db_pool as utils_db_pool
        db_pool = utils_db_pool
    except Exception as e:
        logger.info(f"Failed to initialize database pool: {e}")
        raise

    # Initialize Kafka consumer
    kafka_bootstrap_servers = f"{system.kafka_host}:{system.kafka_port}"
    logger.info(f"🐛 DEBUG: Initializing Kafka with bootstrap_servers: {kafka_bootstrap_servers}")
    logger.info(f"🐛 DEBUG: system.kafka_host = {system.kafka_host}")
    logger.info(f"🐛 DEBUG: system.kafka_port = {system.kafka_port}")
    
    try:
        kafka_consumer = KafkaMessageConsumer(kafka_bootstrap_servers, 'user_requests', 'debuggo-group')
        consumer_thread = Thread(target=kafka_consumer.consume_messages, daemon=True)
        consumer_thread.start()
        logger.info(f"Kafka consumer initialized and connected to {kafka_bootstrap_servers}")
    except Exception as e:
        logger.error(f"Warning: Failed to initialize Kafka consumer: {e}")
        logger.error("Application will continue without Kafka integration")
        kafka_consumer = None
        consumer_thread = None
    
    # Initialize TestRunner singleton
    try:
        TestRunner()  # This will initialize the Redis connection
    except Exception as e:
        logger.error(f"Failed to initialize TestRunner: {e}")
        raise
    
    # Initialize Execution Scheduler
    try:
        from auroqa.Services.ExecutionScheduler import start_scheduler
        start_scheduler()
        logger.info("✓ Execution scheduler started")
    except Exception as e:
        logger.error(f"Failed to start execution scheduler: {e}")
        # Don't raise - app can work without scheduler
    
    yield

    # Shutdown
    # Stop scheduler
    try:
        from auroqa.Services.ExecutionScheduler import stop_scheduler
        stop_scheduler()
        logger.info("Execution scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
    
    if kafka_consumer:
        kafka_consumer.stop()
    if consumer_thread:
        consumer_thread.join(timeout=1.0)
    # Close the database pool using db_utils
    from auroqa.Utils.Connectors.db_utils import close_db_pool
    close_db_pool()

app = FastAPI(lifespan=lifespan)

# Custom middleware to filter successful GET request logs
@app.middleware("http")
async def log_only_errors_middleware(request: Request, call_next):
    """
    Middleware to suppress logging for successful GET requests.
    Only logs failed requests (4xx, 5xx status codes).
    """
    response = await call_next(request)
    
    # Log only if:
    # 1. Request failed (status >= 400), OR
    # 2. Request is not GET, OR
    # 3. Request took unusually long (optional)
    if response.status_code >= 400:
        logger.warning(
            f"{request.client.host}:{request.client.port} - "
            f'"{request.method} {request.url.path}" {response.status_code}'
        )
    
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add SessionMiddleware for OAuth
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Include OAuth routes
from auroqa.routes.oauth_routes import router as oauth_router
app.include_router(oauth_router, prefix="/api", tags=["oauth"])

# Include Test Suite Management routes
from auroqa.api.suite_endpoints import set_get_current_user
set_get_current_user(get_current_user)
app.include_router(suite_router, tags=["test-suites"])

# Include Variable Management routes
from auroqa.api.variable_endpoints import set_get_current_user as set_variable_user
set_variable_user(get_current_user)
app.include_router(variable_router, tags=["variables"])

# Include Execution Plan Management routes
from auroqa.api.execution_plan_endpoints import set_get_current_user as set_exec_plan_user
set_exec_plan_user(get_current_user)
app.include_router(execution_plan_router, tags=["execution-plans"])

# Include Scheduler Management routes
from auroqa.api.scheduler_endpoints import set_get_current_user as set_scheduler_user
set_scheduler_user(get_current_user)
app.include_router(scheduler_router, tags=["scheduler"])

# Include Execution Management routes
from auroqa.api.execution_endpoints import set_get_current_user as set_execution_user
set_execution_user(get_current_user)
app.include_router(execution_router, tags=["execution"])

# Include Retry Management routes
from auroqa.api.retry_endpoints import set_get_current_user as set_retry_user
set_retry_user(get_current_user)
app.include_router(retry_router, tags=["retry"])

# Include Metrics & Analytics routes
from auroqa.api.metrics_endpoints import set_get_current_user as set_metrics_user
set_metrics_user(get_current_user)
app.include_router(metrics_router, tags=["metrics"])

# Include Quick Run routes (replaces test_executions for manual runs)
app.include_router(quick_run_router, tags=["quick-run"])

# Include Requirements Traceability routes
from auroqa.api.requirements_endpoints import router as requirements_router
from auroqa.api.requirements_endpoints import set_get_current_user as set_requirements_user
set_requirements_user(get_current_user)
app.include_router(requirements_router, tags=["requirements"])

# Include Jira routes
from auroqa.routes.jira_routes import router as jira_router
app.include_router(jira_router, prefix="/api", tags=["jira"])

# NOTE: Scheduler is now initialized in the lifespan context manager above
# The @app.on_event decorators are deprecated and ignored when lifespan is used

def get_db_dependencies():
    return {
        "get_conn": get_db_connection,
        "return_conn": return_db_connection
    }

@app.post("/api/register", response_model=User)
async def register_user(user_data: UserCreate):
    with get_db_connection_context() as conn:
        return create_user(conn, user_data)

@app.post("/api/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    with get_db_connection_context() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, full_name, profile_picture, role, client_id, password_hash FROM users WHERE email = %s",
            (form_data.username,)
        )
        user = cur.fetchone()
        cur.close()

        if not user or not user[6] or not verify_password(form_data.password, user[6]):  
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user[1]}, expires_delta=access_token_expires  
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_info": {
                "id": user[0],
                "email": user[1],
                "full_name": user[2],
                "profile_picture": user[3],
                "role": user[4]
            }
        }

# Refresh token endpoint removed to simplify authentication

@app.get("/api/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.get("/api/users")
async def get_users(current_user: User = Depends(get_current_user)):
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can view all users"
        )
    
    with get_db_connection_context() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.email, u.full_name, u.profile_picture, u.role, u.client_id, c.name as client_name
                FROM users u
                LEFT JOIN clients c ON u.client_id = c.id
                ORDER BY u.email
            """)
            users = cur.fetchall()
            
            users_list = []
            for user in users:
                users_list.append({
                    "id": user[0],
                    "email": user[1],
                    "full_name": user[2],
                    "profile_picture": user[3],
                    "role": user[4],
                    "client_id": user[5],
                    "client_name": user[6] if user[6] else None
                })
                
            return users_list

@app.post("/api/generate_test_cases_from_data", response_model=Dict)
async def generate_test_cases(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    if not current_user.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any client"
        )
    
    # Get form data
    form = await request.form()
    project_id = form.get("project_id")
        
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project ID is required"
        )

    file_path = None
    try:
        # Save uploaded file
        file_path = os.path.join(UPLOAD_DIRECTORY, file.filename)
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Initialize Kafka producer with required parameters
        system = System()
        bootstrap_servers = f"{system.kafka_host}:{system.kafka_port}"
        logger.info(f"🐛 DEBUG: Producer bootstrap_servers: {bootstrap_servers}")
        topic = 'user_requests'

        # Send message to Kafka
        producer = KafkaMessageProducer(bootstrap_servers=bootstrap_servers, topic=topic)
        message = {
            'file_path': file_path,
            'file_name': file.filename,
            'attachment_type': 'image' if file.filename.endswith('.png') else 'text',
            'request_type': 'generate_test_cases',
            'client_id': str(current_user.client_id),
            'project_id': project_id  # Add project_id to the message
        }
        producer.send_message(message)
        producer.close()

        return {"message": "File uploaded and processing started", "file_name": file.filename}
    except Exception as e:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}"
        )

@app.get("/api/tests/tree")
async def get_tests_tree(current_user: User = Depends(get_current_user)):
    with get_db_connection_context() as conn:
        with conn.cursor() as cur:
            # Convert UUID to string for the query
            client_id = str(current_user.client_id) if current_user.client_id else None
            # Get project_id from request query params if available
            project_id = None
            
            if current_user.role == 'admin':
                cur.execute(
                    """
                    WITH RECURSIVE TestCaseHierarchy AS (
                        SELECT id, name, description, parent_id, type, "order", client_id, project_id, created_at, updated_at, test_type
                        FROM test_cases
                        WHERE parent_id IS NULL
                        
                        UNION ALL
                        
                        SELECT tc.id, tc.name, tc.description, tc.parent_id, tc.type, tc."order", tc.client_id, tc.project_id, tc.created_at, tc.updated_at, tc.test_type
                        FROM test_cases tc
                        JOIN TestCaseHierarchy tch ON tc.parent_id = tch.id
                    )
                    SELECT 
                        t.id,
                        t.name,
                        t.description,
                        t.parent_id,
                        t.type,
                        t."order",
                        t.created_at,
                        t.updated_at,
                        c.id as client_id,
                        c.name as client_name,
                        t.project_id,
                        t.test_type
                    FROM TestCaseHierarchy t
                    JOIN clients c ON t.client_id = c.id
                    ORDER BY t.parent_id NULLS FIRST, t."order"
                    """
                )
            else:
                cur.execute(
                    """
                    WITH RECURSIVE TestCaseHierarchy AS (
                        SELECT id, name, description, parent_id, type, "order", client_id, project_id, created_at, updated_at, test_type
                        FROM test_cases
                        WHERE parent_id IS NULL AND client_id = %s AND project_id = %s
                        
                        UNION ALL
                        
                        SELECT tc.id, tc.name, tc.description, tc.parent_id, tc.type, tc."order", tc.client_id, tc.project_id, tc.created_at, tc.updated_at, tc.test_type
                        FROM test_cases tc
                        JOIN TestCaseHierarchy tch ON tc.parent_id = tch.id
                        WHERE tc.client_id = %s AND tc.project_id = %s
                    )
                    SELECT 
                        t.id,
                        t.name,
                        t.description,
                        t.parent_id,
                        t.type,
                        t."order",
                        t.created_at,
                        t.updated_at,
                        c.id as client_id,
                        c.name as client_name,
                        t.project_id,
                        t.test_type
                    FROM TestCaseHierarchy t
                    JOIN clients c ON t.client_id = c.id
                    WHERE c.id = %s
                    ORDER BY t.parent_id NULLS FIRST, t."order"
                    """,
                    (client_id, project_id, client_id, project_id, client_id)
                )

            rows = cur.fetchall()
            
            # Convert rows to list of dictionaries for build_tree function
            test_cases_list = []
            for row in rows:
                test_cases_list.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2],
                    'parent_id': row[3],
                    'type': row[4],
                    'order': row[5],
                    'created_at': row[6].isoformat() if row[6] else None,
                    'updated_at': row[7].isoformat() if row[7] else None,
                    'client_id': row[8],
                    'client_name': row[9],
                    'project_id': row[10],
                    'test_type': row[11]
                })
            
            # Use the build_tree function from test_case_builder
            tree_data = build_tree(test_cases_list)
            
            # Group by test type with recursive handling of groups
            def categorize_items(items):
                """Recursively categorize items into UI and API groups"""
                ui_items = []
                api_items = []
                
                for item in items:
                    if item.get('type') == 'test':
                        # Individual test case - categorize by test_type
                        if item.get('test_type') == 'api':
                            api_items.append(item)
                        else:  # Default to UI for backward compatibility
                            ui_items.append(item)
                    elif item.get('type') == 'group':
                        # Group - analyze its children to determine placement
                        if 'children' in item and item['children']:
                            ui_children, api_children = categorize_items(item['children'])
                            
                            # Create copies of the group for each type that has children
                            if ui_children:
                                ui_group_copy = {
                                    **item,
                                    'children': ui_children
                                }
                                ui_items.append(ui_group_copy)
                            
                            if api_children:
                                api_group_copy = {
                                    **item, 
                                    'children': api_children
                                }
                                api_items.append(api_group_copy)
                        else:
                            # Empty group - default to UI
                            ui_items.append(item)
                    else:
                        # Other types (root, etc.) - default to UI
                        ui_items.append(item)
                
                return ui_items, api_items
            
            ui_cases, api_cases = categorize_items(tree_data)
            
            # Create type-based groups
            grouped_items = []
            
            if ui_cases:
                ui_group = {
                    'id': 'ui_group',
                    'name': 'UI Tests',
                    'type': 'type_group',
                    'test_type': 'ui',
                    'children': ui_cases
                }
                grouped_items.append(ui_group)
            
            if api_cases:
                api_group = {
                    'id': 'api_group', 
                    'name': 'API Tests',
                    'type': 'type_group',
                    'test_type': 'api',
                    'children': api_cases
                }
                grouped_items.append(api_group)
            
            return grouped_items

@app.get("/api/get_test_cases/{id}")
async def get_test_cases(id: int, current_user: User = Depends(get_current_user)):
    if not current_user.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any client"
        )
    with get_db_connection_context() as conn:
        from auroqa.fetch_test_steps import get_test_data_from_db_helper
        return get_test_data_from_db_helper(conn, id, str(current_user.client_id))

@app.get("/api/get_test_runs/{test_case_id}")
async def get_test_runs(test_case_id: int, current_user: User = Depends(get_current_user)):
    """Get all test runs for a specific test case."""
    if not current_user.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any client"
        )
    
    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                # Verify test case belongs to user's client
                cursor.execute(
                    """
                    SELECT id FROM test_cases 
                    WHERE id = %s AND client_id = %s
                    """,
                    (test_case_id, str(current_user.client_id))
                )
                if not cursor.fetchone():
                    raise HTTPException(
                        status_code=404,
                        detail="Test case not found or access denied"
                    )
                
                # Fetch test runs
                cursor.execute(
                    """
                    SELECT id, run_date, result, exception, duration, 
                           stdout, stderr, additional_info
                    FROM test_runs
                    WHERE test_case_id = %s
                    ORDER BY run_date DESC
                    """,
                    (test_case_id,)
                )
                
                runs = []
                for row in cursor.fetchall():
                    runs.append({
                        'id': row[0],
                        'run_date': row[1].isoformat() if row[1] else None,
                        'result': row[2],
                        'exception': row[3],
                        'duration': row[4],
                        'stdout': row[5],
                        'stderr': row[6],
                        'additional_info': row[7]
                    })
                
                return runs
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching test runs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch test runs: {str(e)}"
        )

@app.post("/api/run_test_case/{id}", response_model=Dict)
async def run_test_case(
    id: int, 
    request_data: dict = None,
    current_user: User = Depends(get_current_user)
):
    """
    Endpoint to start test execution asynchronously and return test_run_id immediately.
    Routes to appropriate executor based on test case type (UI or API).
    If environment_id is provided, the test will use the environment variables.
    If execution_id is provided, the test run will be linked to that execution.
    """
    conn = None
    try:
        # First, check the test case type to determine which executor to use
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT test_type, project_id
                    FROM test_cases
                    WHERE id = %s AND client_id = %s
                    """,
                    (id, str(current_user.client_id))
                )
                test_case_data = cursor.fetchone()
                
                if not test_case_data:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Test case {id} not found or access denied"
                    )
                
                test_type = test_case_data[0] or 'ui'  # Default to 'ui' for backward compatibility
                project_id = test_case_data[1]
        
        environment_vars = {}
        execution_id = None
        quick_run_id = None
        
        # Extract execution_id and quick_run_id from request data
        if request_data:
            execution_id = request_data.get("execution_id")
            quick_run_id = request_data.get("quick_run_id")
        
        # If environment_id is provided, fetch environment variables
        if request_data and "environment_id" in request_data:
            environment_id_param = request_data.get("environment_id")
            with get_db_connection_context() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT e.base_url, e.login, e.password, e.custom_variables
                        FROM environments e
                        JOIN projects p ON e.project_id = p.id
                        WHERE e.id = %s AND p.client_id = %s
                        """,
                        (environment_id_param, str(current_user.client_id))
                    )
                    env_data = cursor.fetchone()
                    
                    if env_data:
                        environment_vars = {
                            "base_url": env_data[0],
                            "login": env_data[1],
                            "password": env_data[2],
                            "custom_variables": env_data[3] or {}
                        }
        
        # Route to appropriate executor based on test type
        if test_type == 'api' or test_type == 'api_test':
            # Use API test executor
            from auroqa.Services.ApiTestExecutor import ApiTestExecutor
            
            if not environment_vars:
                raise HTTPException(
                    status_code=400,
                    detail="API tests require an environment to be selected"
                )
            
            executor = ApiTestExecutor(
                test_case_id=id,
                environment_vars=environment_vars
            )
            
            # Execute API test synchronously (can be made async later)
            result = executor.execute_test_case(execution_id=execution_id)
            
            return JSONResponse(content={
                "success": result['success'],
                "test_run_id": result.get('test_run_id'),
                "message": "API test execution completed",
                "error": result.get('error')
            })
        else:
            # Use UI test runner (existing implementation)
            runner = TestRunner(user_id=str(current_user.id), test_case_id=id)
            
            # Start test execution asynchronously and get test_run_id immediately
            # Pass quick_run_id if provided for logging to execution_suite_plan_test_runs
            result = runner.start_test_case_async(
                id, 
                environment_vars, 
                execution_id,
                quick_run_id=quick_run_id
            )
            return JSONResponse(content=result)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run test case: {str(e)}"
        )

@app.get("/api/running-tests")
async def get_running_tests(current_user: User = Depends(get_current_user)):
    """
    Get all currently running test cases and executions for the user's client.
    Uses database as single source of truth for running tests.
    """
    with get_db_connection_context() as conn:
        cursor = conn.cursor()
        running_tests = []
        
        # Get all running test runs from database (single source of truth)
        cursor.execute("""
            SELECT tr.id, tr.test_case_id, tc.name, tc.description, 
                   tr.run_date, tr.execution_id, te.name as execution_name
            FROM test_runs tr
            JOIN test_cases tc ON tr.test_case_id = tc.id
            LEFT JOIN test_executions te ON tr.execution_id = te.id
            WHERE tr.result = 'running' AND tc.client_id = %s
            ORDER BY tr.run_date DESC
        """, (str(current_user.client_id),))
        
        for row in cursor.fetchall():
            running_tests.append({
                "test_case_id": row[1],
                "test_case_name": row[2], 
                "test_case_description": row[3],
                "test_run_id": row[0],
                "started_at": row[4].isoformat() if row[4] else None,
                "execution_id": row[5],
                "execution_name": row[6],
                "status": "running"
            })
        
        return {"running_tests": running_tests}

@app.get("/api/test_run/{test_run_id}/status")
async def get_test_run_status(
    test_run_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get the current status of a test run.
    Returns test run details, completion status, and step execution results.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify that the test run belongs to the current user's client
            cursor.execute(
                """
                SELECT tr.id, tr.test_case_id, tr.result, tr.exception, tr.duration, 
                       tr.stdout, tr.stderr, tr.run_date, tr.execution_id,
                       tc.name as test_case_name, tc.description as test_case_description
                FROM test_runs tr
                JOIN test_cases tc ON tr.test_case_id = tc.id
                WHERE tr.id = %s AND tc.client_id = %s
                """,
                (test_run_id, str(current_user.client_id))
            )
            test_run = cursor.fetchone()
            
            if not test_run:
                raise HTTPException(
                    status_code=404,
                    detail="Test run not found"
                )
            
            # Get step execution results
            cursor.execute(
                """
                SELECT tser.test_step_id, tser.step_order, tser.status, tser.error_message,
                       tser.execution_time_ms, tser.started_at, tser.completed_at,
                       ts.description, ts.action, ts.element_path, ts.value
                FROM test_step_execution_results tser
                JOIN test_steps ts ON tser.test_step_id = ts.id
                WHERE tser.test_run_id = %s
                ORDER BY tser.step_order
                """,
                (test_run_id,)
            )
            step_results = cursor.fetchall()
            
            # Calculate completion status
            is_running = test_run[2] == "running"  # result field
            is_completed = test_run[2] in ["completed", "failed", "stopped"]
            
            # Format step results
            formatted_steps = []
            for step in step_results:
                formatted_steps.append({
                    "test_step_id": step[0],
                    "step_order": step[1],
                    "status": step[2],
                    "error_message": step[3],
                    "execution_time_ms": step[4],
                    "started_at": step[5].isoformat() if step[5] else None,
                    "completed_at": step[6].isoformat() if step[6] else None,
                    "description": step[7],
                    "action": step[8],
                    "element_path": step[9],
                    "value": step[10]
                })
            
            return {
                "test_run_id": test_run[0],
                "test_case_id": test_run[1],
                "test_case_name": test_run[9],
                "test_case_description": test_run[10],
                "status": test_run[2],
                "exception": test_run[3],
                "duration": test_run[4],
                "stdout": test_run[5],
                "stderr": test_run[6],
                "run_date": test_run[7].isoformat() if test_run[7] else None,
                "execution_id": test_run[8],
                "is_running": is_running,
                "is_completed": is_completed,
                "steps": formatted_steps,
                "total_steps": len(formatted_steps)
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get test run status: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/generate_steps/{id}", response_model=Dict)
async def generate_steps(
    id: int, 
    request_data: GenerateStepsRequest = None,
    current_user: User = Depends(get_current_user)
):
    """
    Endpoint to generate test steps for a test case.
    If project_id is provided, the test case will be associated with that project.
    If environment_id is provided, the test will use the environment variables.
    """
    conn = None
    try:
        # If project_id is provided, update the test case's project_id
        if request_data and request_data.project_id:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                # Verify the test case exists
                cursor.execute(
                    "SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                    (id, str(current_user.client_id))
                )
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="Test case not found")
                
                # Update the project_id
                cursor.execute(
                    "UPDATE test_cases SET project_id = %s WHERE id = %s",
                    (str(request_data.project_id), id)
                )
                conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error updating test case project: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update test case project: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)
    
    try:
        # Delete all existing test steps before generating new ones
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # Verify the test case exists
                cursor.execute(
                    "SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                    (id, str(current_user.client_id))
                )
                if not cursor.fetchone():
                    raise HTTPException(status_code=404, detail="Test case not found")
                
                # Delete all test steps
                cursor.execute(
                    "DELETE FROM test_steps WHERE test_case_id = %s",
                    (id,)
                )
                deleted_count = cursor.rowcount
                conn.commit()
                logger.info(f"🗑️ Deleted {deleted_count} existing test steps for test case {id}")
        finally:
            if conn:
                return_db_connection(conn)
        
        # Get the singleton instance of TestRunner
        runner = TestRunner(user_id=str(current_user.id), test_case_id=id)
        
        # Set up environment variables if environment_id is provided
        environment_vars = {}
        if request_data and request_data.environment_id:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT e.base_url, e.login, e.password
                        FROM environments e
                        JOIN projects p ON e.project_id = p.id
                        WHERE e.id = %s AND p.client_id = %s
                        """,
                        (request_data.environment_id, str(current_user.client_id))
                    )
                    env_data = cursor.fetchone()
                    
                    if env_data:
                        environment_vars = {
                            "base_url": env_data[0],
                            "login": env_data[1],
                            "password": env_data[2]
                        }
            finally:
                if conn:
                    return_db_connection(conn)
        
        # Get the AI model ID and VLM setting to use
        ai_model_id = None
        vlm_enabled = False  # Default to False
        
        if request_data and request_data.ai_model_id:
            # Use the model specified in the request
            ai_model_id = request_data.ai_model_id
            # If passed in request, we might want to support vlm_enabled there too, 
            # but for now let's fetch user preference if not explicitly passed (or just use default)
            # Assuming request_data doesn't have vlm_enabled yet, so we fetch from DB or default
            
            # Ideally we should fetch the user's VLM preference even if model is passed
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT vlm_enabled FROM user_ai_models WHERE user_id = %s
                        """,
                        (current_user.id,)
                    )
                    user_pref = cursor.fetchone()
                    if user_pref:
                        vlm_enabled = user_pref[0]
            finally:
                if conn:
                    return_db_connection(conn)
        else:
            # Check if the user has a preferred model
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT ai_model_id, vlm_enabled FROM user_ai_models WHERE user_id = %s
                        """,
                        (current_user.id,)
                    )
                    user_model = cursor.fetchone()
                    if user_model:
                        ai_model_id = user_model[0]
                        vlm_enabled = user_model[1]
                    else:
                        # Use the default model
                        cursor.execute(
                            """
                            SELECT id FROM ai_models WHERE is_default = TRUE AND is_active = TRUE
                            """
                        )
                        default_model = cursor.fetchone()
                        if default_model:
                            ai_model_id = default_model[0]
                            # vlm_enabled remains False (default)
            finally:
                if conn:
                    return_db_connection(conn)
        # Start the test step generation in a separate thread
        thread = Thread(target=runner.generate_test_steps, args=(id, environment_vars, ai_model_id, vlm_enabled))
        thread.daemon = True
        thread.start()
        
        return {"status": "started"}
    except Exception as e:
        logger.error(f"Error generating test steps: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate test steps: {str(e)}"
        )

@app.post("/api/confirm_generate_steps/{id}", response_model=Dict)
async def confirm_generate_steps(
    id: int, 
    request_data: GenerateStepsRequest = None,
    current_user: User = Depends(get_current_user)
):
    """
    Endpoint to confirm and regenerate test steps for a test case.
    If project_id is provided, the test case will be associated with that project.
    If environment_id is provided, the test will use the environment variables.
    """
    conn = None
    try:
        # First, delete existing steps
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify the test case exists
            cursor.execute(
                "SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                (id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Test case not found")
            
            # Delete all test steps - execution results are now preserved independently
            cursor.execute(
                "DELETE FROM test_steps WHERE test_case_id = %s",
                (id,)
            )
            
            # If project_id is provided, update the test case's project_id
            if request_data and request_data.project_id:
                cursor.execute(
                    "UPDATE test_cases SET project_id = %s WHERE id = %s",
                    (str(request_data.project_id), id)
                )
            
            conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error deleting existing test steps: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete existing test steps: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)
    
    try:
        # Get the singleton instance of TestRunner
        runner = TestRunner(user_id=str(current_user.id), test_case_id=id)
        
        # Set up environment variables if environment_id is provided
        environment_vars = {}
        if request_data and request_data.environment_id:
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT e.base_url, e.login, e.password
                        FROM environments e
                        JOIN projects p ON e.project_id = p.id
                        WHERE e.id = %s AND p.client_id = %s
                        """,
                        (request_data.environment_id, str(current_user.client_id))
                    )
                    env_data = cursor.fetchone()
                    
                    if env_data:
                        environment_vars = {
                            "base_url": env_data[0],
                            "login": env_data[1],
                            "password": env_data[2]
                        }
            finally:
                if conn:
                    return_db_connection(conn)
        
        # Get the AI model ID and VLM setting to use
        ai_model_id = None
        vlm_enabled = False  # Default to False
        
        if request_data and request_data.ai_model_id:
            # Use the model specified in the request
            ai_model_id = request_data.ai_model_id
            # If passed in request, we might want to support vlm_enabled there too, 
            # but for now let's fetch user preference if not explicitly passed (or just use default)
            # Assuming request_data doesn't have vlm_enabled yet, so we fetch from DB or default
            
            # Ideally we should fetch the user's VLM preference even if model is passed
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT vlm_enabled FROM user_ai_models WHERE user_id = %s
                        """,
                        (current_user.id,)
                    )
                    user_pref = cursor.fetchone()
                    if user_pref:
                        vlm_enabled = user_pref[0]
            finally:
                if conn:
                    return_db_connection(conn)
        else:
            # Check if the user has a preferred model
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT ai_model_id, vlm_enabled FROM user_ai_models WHERE user_id = %s
                        """,
                        (current_user.id,)
                    )
                    user_model = cursor.fetchone()
                    if user_model:
                        ai_model_id = user_model[0]
                        vlm_enabled = user_model[1]
                    else:
                        # Use the default model
                        cursor.execute(
                            """
                            SELECT id FROM ai_models WHERE is_default = TRUE AND is_active = TRUE
                            """
                        )
                        default_model = cursor.fetchone()
                        if default_model:
                            ai_model_id = default_model[0]
                            # vlm_enabled remains False (default)
            finally:
                if conn:
                    return_db_connection(conn)
        # Start the test step generation in a separate thread
        thread = Thread(target=runner.generate_test_steps, args=(id, environment_vars, ai_model_id, vlm_enabled))
        thread.daemon = True
        thread.start()
        
        return {"status": "started"}
    except Exception as e:
        logger.error(f"Error generating test steps: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate test steps: {str(e)}"
        )

@app.post("/api/test-cases/{test_case_id}/generate-api-steps")
async def generate_api_test_steps(
    test_case_id: int,
    request_data: dict = Body(...),
    current_user: User = Depends(get_current_user)
):
    """
    Generate API test steps for a test case using AI asynchronously via Kafka.
    This endpoint is specifically for API test cases.
    """
    try:
        # Extract environment_id from request body
        environment_id = request_data.get('environment_id') if request_data else None
        
        # Verify test case exists and is an API test
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT tc.test_type, tc.project_id, tc.name, tc.description
                    FROM test_cases tc
                    WHERE tc.id = %s AND tc.client_id = %s
                """, (test_case_id, str(current_user.client_id)))
                
                test_case = cursor.fetchone()
                if not test_case:
                    raise HTTPException(
                        status_code=404,
                        detail="Test case not found or access denied"
                    )
                
                test_type = test_case[0]
                project_id = test_case[1]
                test_name = test_case[2]
                test_description = test_case[3]
                
                if test_type not in ['api', 'api_test']:
                    raise HTTPException(
                        status_code=400,
                        detail="This endpoint is only for API test cases"
                    )
        
        # Try to get the API schema for this project from database
        schema_content = None
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT content, name, schema_type
                    FROM api_schemas
                    WHERE project_id = %s AND client_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (project_id, str(current_user.client_id)))
                
                schema_row = cursor.fetchone()
                if schema_row:
                    schema_content = schema_row[0]
                    schema_name = schema_row[1]
                    schema_type = schema_row[2]
                    logger.info(f"Using API schema '{schema_name}' ({schema_type}) for project {project_id}")
        
        # If no schema found, use test case description
        if not schema_content:
            logger.info(f"No API schema found for project {project_id}, using test case description")
            schema_content = f"""
Test Case: {test_name}
Description: {test_description}

Generate API test steps for this test case based on the description.
Analyze the test case description to determine the correct endpoints and methods.
Include authentication steps if mentioned in the description.

Important: Use the exact endpoint paths mentioned in the test case description.
If no specific endpoint is mentioned, use standard REST patterns.
"""
        
        # Send message to Kafka for async processing
        from kafka import KafkaProducer
        import json
        from auroqa.Utils.System import System
        
        # Use System configuration which handles Docker vs local environments
        system = System()
        kafka_bootstrap_servers = f"{system.kafka_host}:{system.kafka_port}"
        producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        
        message = {
            'request_type': 'generate_api_test_steps',
            'test_case_id': test_case_id,
            'schema_content': schema_content,
            'client_id': str(current_user.client_id),
            'project_id': str(project_id),
            'environment_id': environment_id
        }
        
        producer.send('user_requests', value=message)
        producer.flush()
        producer.close()
        
        # Mark test case as generating in Redis with shorter TTL to avoid stale flags
        from auroqa.Utils.System import System
        system = System()
        try:
            r = redis.Redis(host=system.redis_host, port=system.redis_port, db=0, decode_responses=True)
            # Use shorter TTL (5 minutes) to prevent stale generation flags
            r.setex(f"api_test_generating:{test_case_id}", 300, test_name)  # Expire after 5 minutes
            logger.info(f"Marked test case {test_case_id} as generating in Redis (TTL: 5 min)")
        except Exception as redis_error:
            logger.error(f"Redis error: {redis_error}")
        
        logger.info(f"Sent API test steps generation request to Kafka for test case {test_case_id}")
        
        return JSONResponse(content={
            "success": True,
            "message": "API test steps generation started. Steps will be generated asynchronously.",
            "test_case_id": test_case_id
        })
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queuing API test steps generation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue API test steps generation: {str(e)}"
        )

# ==================== API Conflict Notification Endpoints ====================

@app.get("/api/conflict-notifications/pending")
async def get_pending_conflict_notifications(
    current_user: User = Depends(get_current_user)
):
    """
    Get all pending conflict notifications for the current user.
    These are conflicts between API documentation and actual behavior that require user decision.
    """
    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        cn.id,
                        cn.test_case_id,
                        tc.name as test_case_name,
                        cn.step_number,
                        cn.conflict_type,
                        cn.request_method,
                        cn.request_endpoint,
                        cn.request_body,
                        cn.expected_status,
                        cn.actual_status,
                        cn.actual_response,
                        cn.conflict_description,
                        cn.suggested_resolution,
                        cn.corrected_expected_status,
                        cn.corrected_expected_response,
                        cn.created_at
                    FROM api_conflict_notifications cn
                    JOIN test_cases tc ON cn.test_case_id = tc.id
                    WHERE cn.user_id = %s 
                      AND cn.client_id = %s
                      AND cn.status = 'pending'
                    ORDER BY cn.created_at DESC
                """, (current_user.id, str(current_user.client_id)))
                
                notifications = []
                for row in cursor.fetchall():
                    notifications.append({
                        'id': row[0],
                        'test_case_id': row[1],
                        'test_case_name': row[2],
                        'step_number': row[3],
                        'conflict_type': row[4],
                        'request': {
                            'method': row[5],
                            'endpoint': row[6],
                            'body': row[7]
                        },
                        'expected_status': row[8],
                        'actual_status': row[9],
                        'actual_response': row[10],
                        'conflict_description': row[11],
                        'suggested_resolution': row[12],
                        'corrected_expected_status': row[13],
                        'corrected_expected_response': row[14],
                        'created_at': row[15].isoformat() if row[15] else None
                    })
                
                return JSONResponse(content={
                    'success': True,
                    'notifications': notifications,
                    'count': len(notifications)
                })
                
    except Exception as e:
        logger.error(f"Error fetching conflict notifications: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch conflict notifications: {str(e)}"
        )

@app.post("/api/conflict-notifications/{notification_id}/approve")
async def approve_conflict_resolution(
    notification_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Approve a conflict resolution and resume test generation with corrected expected result.
    """
    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                # Verify notification exists and belongs to user
                cursor.execute("""
                    SELECT test_case_id, status
                    FROM api_conflict_notifications
                    WHERE id = %s AND user_id = %s AND client_id = %s
                """, (notification_id, current_user.id, str(current_user.client_id)))
                
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail="Conflict notification not found or access denied"
                    )
                
                test_case_id, current_status = result
                
                if current_status != 'pending':
                    raise HTTPException(
                        status_code=400,
                        detail=f"Notification already {current_status}"
                    )
                
                # Update notification status to approved
                cursor.execute("""
                    UPDATE api_conflict_notifications
                    SET status = 'approved',
                        resolved_at = CURRENT_TIMESTAMP,
                        user_decision = 'approved'
                    WHERE id = %s
                """, (notification_id,))
                
                conn.commit()
                
                # Trigger test generation to resume
                from auroqa.Services.ApiSchemaService import ApiSchemaService
                from kafka import KafkaProducer
                import json
                
                # Get schema content for this test case
                cursor.execute("""
                    SELECT s.content, tc.project_id
                    FROM test_cases tc
                    JOIN api_schemas s ON s.project_id = tc.project_id
                    WHERE tc.id = %s AND tc.client_id = %s
                    ORDER BY s.created_at DESC
                    LIMIT 1
                """, (test_case_id, str(current_user.client_id)))
                
                schema_row = cursor.fetchone()
                if schema_row:
                    # Send message to Kafka to resume generation
                    system = System()
                    producer = KafkaProducer(
                        bootstrap_servers=f'{system.kafka_host}:{system.kafka_port}',
                        value_serializer=lambda v: json.dumps(v).encode('utf-8')
                    )
                    
                    message = {
                        'request_type': 'generate_api_test_steps',
                        'test_case_id': test_case_id,
                        'schema_content': schema_row[0],
                        'project_id': str(schema_row[1]),
                        'client_id': str(current_user.client_id)
                    }
                    
                    producer.send('user_requests', value=message)
                    producer.flush()
                    producer.close()
                    
                    logger.info(f"Resumed test generation for test case {test_case_id} after conflict resolution")
                
                return JSONResponse(content={
                    'success': True,
                    'message': 'Conflict resolution approved. Test generation will resume.',
                    'notification_id': notification_id,
                    'test_case_id': test_case_id
                })
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving conflict resolution: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to approve conflict resolution: {str(e)}"
        )

@app.post("/api/conflict-notifications/{notification_id}/reject")
async def reject_conflict_resolution(
    notification_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Reject a conflict resolution and cancel test generation for this test case.
    """
    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                # Verify notification exists and belongs to user
                cursor.execute("""
                    SELECT test_case_id, status
                    FROM api_conflict_notifications
                    WHERE id = %s AND user_id = %s AND client_id = %s
                """, (notification_id, current_user.id, str(current_user.client_id)))
                
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(
                        status_code=404,
                        detail="Conflict notification not found or access denied"
                    )
                
                test_case_id, current_status = result
                
                if current_status != 'pending':
                    raise HTTPException(
                        status_code=400,
                        detail=f"Notification already {current_status}"
                    )
                
                # Update notification status to rejected/cancelled
                cursor.execute("""
                    UPDATE api_conflict_notifications
                    SET status = 'cancelled',
                        resolved_at = CURRENT_TIMESTAMP,
                        user_decision = 'rejected'
                    WHERE id = %s
                """, (notification_id,))
                
                conn.commit()
                
                logger.info(f"Test generation cancelled for test case {test_case_id} - user rejected conflict resolution")
                
                return JSONResponse(content={
                    'success': True,
                    'message': 'Conflict resolution rejected. Test generation cancelled.',
                    'notification_id': notification_id,
                    'test_case_id': test_case_id
                })
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting conflict resolution: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reject conflict resolution: {str(e)}"
        )

@app.post("/api/projects/{project_id}/api-schemas/upload")
async def upload_api_schema(
    project_id: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(None),
    schema_type: str = Form("openapi"),
    current_user: User = Depends(get_current_user)
):
    """
    Upload an API schema (OpenAPI, Swagger, Postman) for a project.
    The schema will be used to generate accurate API test steps.
    """
    try:
        # Verify project exists and user has access
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id FROM projects
                    WHERE id = %s AND client_id = %s
                """, (project_id, str(current_user.client_id)))
                
                if not cursor.fetchone():
                    raise HTTPException(
                        status_code=404,
                        detail="Project not found or access denied"
                    )
        
        # Read file content
        content = await file.read()
        content_str = content.decode('utf-8')
        
        # Validate JSON
        try:
            json.loads(content_str)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON format"
            )
        
        # Save to database
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO api_schemas (
                        project_id, client_id, name, description, 
                        schema_type, content, created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    project_id,
                    str(current_user.client_id),
                    name,
                    description,
                    schema_type,
                    content_str,
                    current_user.id
                ))
                
                schema_id = cursor.fetchone()[0]
                conn.commit()
        
        logger.info(f"Uploaded API schema {schema_id} for project {project_id}")
        
        return JSONResponse(content={
            "success": True,
            "schema_id": schema_id,
            "message": f"API schema '{name}' uploaded successfully"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading API schema: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload API schema: {str(e)}"
        )

@app.get("/api/projects/{project_id}/api-schemas")
async def list_api_schemas(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """List all API schemas for a project."""
    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, description, schema_type, created_at
                    FROM api_schemas
                    WHERE project_id = %s AND client_id = %s
                    ORDER BY created_at DESC
                """, (project_id, str(current_user.client_id)))
                
                rows = cursor.fetchall()
                schemas = []
                for row in rows:
                    schemas.append({
                        "id": row[0],
                        "name": row[1],
                        "description": row[2],
                        "schema_type": row[3],
                        "created_at": row[4].isoformat() if row[4] else None
                    })
                
                return JSONResponse(content={"schemas": schemas})
                
    except Exception as e:
        logger.error(f"Error listing API schemas: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list API schemas: {str(e)}"
        )

@app.delete("/api/api-schemas/{schema_id}")
async def delete_api_schema(
    schema_id: int,
    current_user: User = Depends(get_current_user)
):
    """Delete an API schema."""
    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM api_schemas
                    WHERE id = %s AND client_id = %s
                """, (schema_id, str(current_user.client_id)))
                
                conn.commit()
                
                return JSONResponse(content={
                    "success": True,
                    "message": "API schema deleted successfully"
                })
                
    except Exception as e:
        logger.error(f"Error deleting API schema: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete API schema: {str(e)}"
        )

@app.patch("/api/update_test_step/{id}")
async def update_test_step(
    id: int,
    update_data: UpdateTestStepAction,
    current_user: User = Depends(get_current_user)
):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify the test step exists
            cursor.execute("SELECT id FROM test_steps WHERE id = %s", (id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Test step not found")
            
            # Map AI-generated specific actions to database-valid actions  
            action_mapping = {
                'assert_text_equals': 'assert',
                'assert_element_visible': 'assert',
                'assert_element_present': 'assert',
                'assert_element_not_present': 'assert',
                'assert_url_contains': 'assert',
                'assert_title_contains': 'assert',
                'verify_text': 'assert',
                'verify_element': 'assert',
                'check_text': 'assert',
                'check_element': 'assert'
            }
            
            # Build update query based on provided fields
            update_fields = []
            params = []
            if update_data.action is not None:
                # Apply action mapping if needed
                mapped_action = action_mapping.get(update_data.action, update_data.action)
                update_fields.append("action = %s")
                params.append(mapped_action)
            if update_data.value is not None:
                update_fields.append("value = %s")
                params.append(update_data.value)
            if update_data.element_path is not None:
                update_fields.append("element_path = %s")
                params.append(update_data.element_path)
            if update_data.css_selector is not None:
                update_fields.append("css_selector = %s")
                params.append(update_data.css_selector)
            if update_data.description is not None:
                update_fields.append("description = %s")
                params.append(update_data.description)
            
            if not update_fields:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            # Update the fields
            query = f"UPDATE test_steps SET {', '.join(update_fields)} WHERE id = %s"
            params.append(id)
            cursor.execute(query, tuple(params))
            conn.commit()
            
            # Return connection before response
            if conn:
                return_db_connection(conn)
                conn = None
            
            return JSONResponse(
                content={"message": "Test step updated successfully"},
                status_code=200
            )
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error updating test step: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            return_db_connection(conn)

@app.patch("/api/update_step_orders")
async def update_step_orders(
    update_data: StepOrderUpdate,
    current_user: User = Depends(get_current_user)
):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify test case exists
            cursor.execute(
                "SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                (update_data.test_case_id, str(current_user.client_id))  # Convert UUID to string
            )
            if not cursor.fetchone():
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Test case {update_data.test_case_id} not found"}
                )
            
            # Update step orders
            for step in update_data.step_orders:
                cursor.execute(
                    "UPDATE test_steps SET step_order = %s WHERE id = %s AND test_case_id = %s",
                    (step["step_order"], step["id"], update_data.test_case_id)
                )
            
            conn.commit()
            return JSONResponse(content={"message": "Step orders updated successfully"})
            
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error updating step orders: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to update step orders: {str(e)}"}
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/create_test_step")
async def create_test_step(
    request_data: CreateTestStepRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new test step manually.
    """
    conn = None
    try:
        conn = get_db_connection()
        
        # Verify test case exists and belongs to the user's client
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM test_cases WHERE id = %s",
                (request_data.test_case_id,)
            )
            test_case = cursor.fetchone()
            if not test_case:
                raise HTTPException(status_code=404, detail="Test case not found")
        
        # Get the current highest step order
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(step_order), 0) FROM test_steps WHERE test_case_id = %s",
                (request_data.test_case_id,)
            )
            max_order = cursor.fetchone()[0]
            new_order = max_order + 1
        
        # Map AI-generated specific actions to database-valid actions
        action_mapping = {
            'assert_text_equals': 'assert',
            'assert_element_visible': 'assert',
            'assert_element_present': 'assert',
            'assert_element_not_present': 'assert',
            'assert_url_contains': 'assert',
            'assert_title_contains': 'assert',
            'verify_text': 'assert',
            'verify_element': 'assert',
            'check_text': 'assert',
            'check_element': 'assert'
        }
        
        # Convert action if it's a specific assertion type
        mapped_action = action_mapping.get(request_data.action, request_data.action)
        
        # Insert the new test step
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO test_steps (
                    test_case_id, step_order, description, action, 
                    element_path, value, path_type, expected_result,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) RETURNING id
            """, (
                request_data.test_case_id,
                new_order,
                request_data.description,
                mapped_action,
                request_data.element_path,
                request_data.value,
                request_data.path_type,
                request_data.expected_result,
                datetime.now(),
                datetime.now()
            ))
            new_step_id = cursor.fetchone()[0]
            conn.commit()
        
        # Fetch the newly created step to return
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("""
                SELECT id, test_case_id, step_order, description, action, 
                       element_path, value, path_type, expected_result
                FROM test_steps
                WHERE id = %s
            """, (new_step_id,))
            new_step = cursor.fetchone()
        
        return dict(new_step)
        
    except Exception as e:
        if conn:
            conn.rollback()
        logging.error(f"Error creating test step: {str(e)}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to create test step: {str(e)}")
    finally:
        if conn:
            return_db_connection(conn)

def check_admin_role(user: User):
    if user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can access this endpoint"
        )

@app.get("/api/clients")
async def list_clients(current_user: User = Depends(get_current_user)):
    check_admin_role(current_user)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, created_at, updated_at
                FROM clients
                ORDER BY name
                """
            )
            clients = cur.fetchall()
            return [
                {
                    "id": str(client[0]),
                    "name": client[1],
                    "created_at": client[2].isoformat(),
                    "updated_at": client[3].isoformat()
                }
                for client in clients
            ]
    finally:
        return_db_connection(conn)

@app.get("/api/clients/for-user-management")
async def list_clients_for_user_management(current_user: User = Depends(get_current_user)):
    """
    List all clients for user management purposes.
    This endpoint is accessible to all authenticated users.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, created_at, updated_at
                FROM clients
                ORDER BY name
                """
            )
            clients = cur.fetchall()
            return [
                {
                    "id": str(client[0]),
                    "name": client[1],
                    "created_at": client[2].isoformat() if client[2] else None,
                    "updated_at": client[3].isoformat() if client[3] else None
                }
                for client in clients
            ]
    finally:
        return_db_connection(conn)

@app.post("/api/clients", response_model=Client)
async def create_client(
    client_data: ClientCreate,
    current_user: User = Depends(get_current_user)
):
    check_admin_role(current_user)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO clients (name)
                VALUES (%s)
                RETURNING id, name, created_at, updated_at
                """,
                (client_data.name,)
            )
            client_data = cur.fetchone()
            conn.commit()
            
            return Client(
                id=client_data[0],
                name=client_data[1],
                created_at=client_data[2],
                updated_at=client_data[3]
            )
    finally:
        return_db_connection(conn)

@app.delete("/api/clients/{client_id}")
async def delete_client(client_id: str, current_user: User = Depends(get_current_user)):
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can delete clients"
        )
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # First check if the client exists
            cur.execute(
                "SELECT id FROM clients WHERE id = %s",
                (client_id,)
            )
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Client not found"
                )
            
            # Check if there are any test cases for this client
            cur.execute(
                "SELECT COUNT(*) FROM test_cases WHERE client_id = %s",
                (client_id,)
            )
            test_case_count = cur.fetchone()[0]
            
            if test_case_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot delete client because it has {test_case_count} test case(s). Please delete all test cases first."
                )

            # Check if there are any users associated with this client
            cur.execute(
                "SELECT COUNT(*) FROM users WHERE client_id = %s",
                (client_id,)
            )
            user_count = cur.fetchone()[0]
            
            if user_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot delete client because it has {user_count} associated user(s). Please reassign or remove all users first."
                )
            
            # Delete the client
            cur.execute(
                "DELETE FROM clients WHERE id = %s",
                (client_id,)
            )
            conn.commit()
            
            return {"message": "Client deleted successfully"}
    finally:
        return_db_connection(conn)

@app.put("/api/users/{user_id}/client")
async def update_user_client(
    user_id: str,
    update_data: UserClientUpdate,
    current_user: User = Depends(get_current_user)
):
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can update user's client"
        )
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # First check if the user exists
            cur.execute(
                "SELECT id FROM users WHERE id = %s",
                (user_id,)
            )
            if not cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # If client_id is provided, check if it exists
            if update_data.client_id:
                cur.execute(
                    "SELECT id FROM clients WHERE id = %s",
                    (update_data.client_id,)
                )
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Client not found"
                    )
            
            # Update the user's client
            cur.execute(
                "UPDATE users SET client_id = %s WHERE id = %s",
                (update_data.client_id, user_id)
            )
            conn.commit()
            
            return {"message": "User's client updated successfully"}
    finally:
        return_db_connection(conn)

@app.get("/api/projects")
async def list_projects(current_user: User = Depends(get_current_user)):
    """
    List all projects for the current user's client.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if user has a client_id
            if current_user.client_id is None:
                # If no client_id, return empty list or handle as appropriate
                return []
            
            # Convert UUID to string for database query
            client_id_str = str(current_user.client_id)
            
            cursor.execute(
                """
                SELECT id, name, description, created_at, updated_at
                FROM projects
                WHERE client_id = %s
                ORDER BY name
                """,
                (client_id_str,)
            )
            projects = cursor.fetchall()
            
            return [
                {
                    "id": str(project[0]),  # Convert UUID to string
                    "name": project[1],
                    "description": project[2],
                    "created_at": project[3].isoformat() if project[3] else None,
                    "updated_at": project[4].isoformat() if project[4] else None
                }
                for project in projects
            ]
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list projects: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/projects")
async def create_project(
    project_data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new project for the current user's client.
    """
    if not project_data.get("name"):
        raise HTTPException(
            status_code=400,
            detail="Project name is required"
        )
    
    # If user is not admin, force client_id to current user's client
    if current_user.role == 'user':
        # Handle None client_id properly
        if current_user.client_id is None:
            project_data["client_id"] = None
        else:
            project_data["client_id"] = str(current_user.client_id)
    elif not project_data.get("client_id"):
        # For admins, client_id must be provided
        raise HTTPException(
            status_code=400,
            detail="Client is required for project creation"
        )
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO projects (name, description, client_id)
                VALUES (%s, %s, %s)
                RETURNING id, name, description, client_id, created_at, updated_at
                """,
                (
                    project_data["name"],
                    project_data.get("description"),
                    project_data["client_id"]
                )
            )
            project = cursor.fetchone()
            conn.commit()
            
            return {
                "id": str(project[0]),
                "name": project[1],
                "description": project[2],
                "client_id": str(project[3]) if project[3] else None,
                "created_at": project[4].isoformat() if project[4] else None,
                "updated_at": project[5].isoformat() if project[5] else None
            }
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error creating project: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create project: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.get("/api/projects/{project_id}")
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific project by ID.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, description, client_id, created_at, updated_at
                FROM projects
                WHERE id = %s AND client_id = %s
                """,
                (project_id, str(current_user.client_id))
            )
            project = cursor.fetchone()
            
            if not project:
                raise HTTPException(
                    status_code=404,
                    detail="Project not found"
                )
            
            return {
                "id": str(project[0]),  # Convert UUID to string
                "name": project[1],
                "description": project[2],
                "client_id": str(project[3]) if project[3] else None,
                "created_at": project[4].isoformat() if project[4] else None,
                "updated_at": project[5].isoformat() if project[5] else None
            }
    except Exception as e:
        logger.error(f"Error getting project: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get project: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.put("/api/projects/{project_id}")
async def update_project(
    project_id: str,
    project_data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Update a specific project by ID.
    """
    if not project_data.get("name"):
        raise HTTPException(
            status_code=400,
            detail="Project name is required"
        )
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if project exists and belongs to user's client
            cursor.execute(
                """
                SELECT id FROM projects
                WHERE id = %s AND client_id = %s
                """,
                (project_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Project not found"
                )
            
            # Update project
            cursor.execute(
                """
                UPDATE projects
                SET name = %s, description = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, name, description, client_id, created_at, updated_at
                """,
                (
                    project_data.get("name"),
                    project_data.get("description"),
                    project_id
                )
            )
            project = cursor.fetchone()
            conn.commit()
            
            return {
                "id": str(project[0]),  # Convert UUID to string
                "name": project[1],
                "description": project[2],
                "client_id": str(project[3]) if project[3] else None,
                "created_at": project[4].isoformat() if project[4] else None,
                "updated_at": project[5].isoformat() if project[5] else None
            }
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error updating project: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update project: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a specific project by ID.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if project exists and belongs to user's client
            cursor.execute(
                """
                SELECT id FROM projects
                WHERE id = %s AND client_id = %s
                """,
                (project_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Project not found"
                )
            
            # Delete project
            cursor.execute(
                """
                DELETE FROM projects
                WHERE id = %s
                """,
                (project_id,)
            )
            conn.commit()
            
            return {"message": "Project deleted successfully"}
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error deleting project: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete project: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.get("/api/projects/{project_id}/test_tree")
async def get_project_test_tree(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get the test case tree for a specific project.
    """
    conn = None
    try:
        # Check if user has a client_id
        if current_user.client_id is None:
            # Return empty result or appropriate response for users without a client
            return []
            
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Convert client_id to string for database query
            client_id_str = str(current_user.client_id)
            
            # Check if project exists and belongs to user's client
            cursor.execute(
                """
                SELECT id FROM projects
                WHERE id = %s AND client_id = %s
                """,
                (project_id, client_id_str)
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Project not found"
                )
            
            logger.info(f"Fetching test tree for project_id: {project_id}, client_id: {client_id_str}")
            
            # Let's also check all test cases for this project
            cursor.execute(
                """
                SELECT id, name, parent_id, type, client_id, project_id, test_type
                FROM test_cases
                WHERE project_id = %s
                ORDER BY id
                """,
                (project_id,)
            )
            all_project_test_cases = cursor.fetchall()
            
            # Use a recursive query to get all test cases for this project with proper hierarchy
            cursor.execute(
                """
                WITH RECURSIVE TestCaseHierarchy AS (
                    -- Base case: get all root nodes
                    SELECT id, name, description, parent_id, type, "order", created_at, updated_at, test_type
                    FROM test_cases
                    WHERE parent_id IS NULL AND project_id = %s
                    
                    UNION ALL
                    
                    -- Recursive case: get all children
                    SELECT tc.id, tc.name, tc.description, tc.parent_id, tc.type, tc."order", tc.created_at, tc.updated_at, tc.test_type
                    FROM test_cases tc
                    JOIN TestCaseHierarchy tch ON tc.parent_id = tch.id
                    WHERE tc.project_id = %s
                )
                SELECT id, name, description, parent_id, type, "order", created_at, updated_at, test_type
                FROM TestCaseHierarchy
                ORDER BY parent_id NULLS FIRST, "order", name
                """,
                (project_id, project_id)
            )
            test_cases = cursor.fetchall()
            
            # Convert to hierarchical structure
            test_case_map = {}
            root_items = []
            
            for tc in test_cases:
                test_case = {
                    "id": tc[0],
                    "name": tc[1],
                    "description": tc[2],
                    "parent_id": tc[3],
                    "type": tc[4],
                    "order": tc[5],
                    "created_at": tc[6].isoformat() if tc[6] else None,
                    "updated_at": tc[7].isoformat() if tc[7] else None,
                    "test_type": tc[8],
                    "children": []
                }
                test_case_map[tc[0]] = test_case
                
                if tc[3] is None:  # Root level item
                    root_items.append(test_case)
                else:
                    # Add to parent's children
                    parent = test_case_map.get(tc[3])
                    if parent:
                        parent["children"].append(test_case)
            
            # Group by test type with recursive handling of groups
            def categorize_items(items):
                """Recursively categorize items into UI and API groups"""
                ui_items = []
                api_items = []
                
                for item in items:
                    if item.get('type') == 'test':
                        # Individual test case - categorize by test_type
                        if item.get('test_type') == 'api':
                            api_items.append(item)
                        else:  # Default to UI for backward compatibility
                            ui_items.append(item)
                    elif item.get('type') == 'group':
                        # Group - analyze its children to determine placement
                        if 'children' in item and item['children']:
                            ui_children, api_children = categorize_items(item['children'])
                            
                            # Create copies of the group for each type that has children
                            if ui_children:
                                ui_group_copy = {
                                    **item,
                                    'children': ui_children
                                }
                                ui_items.append(ui_group_copy)
                            
                            if api_children:
                                api_group_copy = {
                                    **item, 
                                    'children': api_children
                                }
                                api_items.append(api_group_copy)
                        else:
                            # Empty group - default to UI
                            ui_items.append(item)
                    else:
                        # Other types (root, etc.) - default to UI
                        ui_items.append(item)
                
                return ui_items, api_items
            
            ui_cases, api_cases = categorize_items(root_items)
            
            # Create type-based groups
            grouped_items = []
            
            if ui_cases:
                ui_group = {
                    'id': 'ui_group',
                    'name': 'UI Tests',
                    'type': 'type_group',
                    'test_type': 'ui',
                    'children': ui_cases
                }
                grouped_items.append(ui_group)
            
            if api_cases:
                api_group = {
                    'id': 'api_group', 
                    'name': 'API Tests',
                    'type': 'type_group',
                    'test_type': 'api',
                    'children': api_cases
                }
                grouped_items.append(api_group)
            
            return grouped_items
    except Exception as e:
        logger.error(f"Error getting project test tree: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get project test tree: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.get("/api/projects/{project_id}/environments")
async def get_project_environments(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all environments for a specific project.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if project exists and belongs to user's client
            cursor.execute(
                """
                SELECT id FROM projects
                WHERE id = %s AND client_id = %s
                """,
                (project_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Project not found"
                )
            
            # Get all environments for this project
            cursor.execute(
                """
                SELECT id, name, base_url, login, password, created_at, updated_at, custom_variables
                FROM environments
                WHERE project_id = %s
                ORDER BY name
                """,
                (project_id,)
            )
            environments = cursor.fetchall()
            
            return [
                {
                    "id": environment[0],
                    "name": environment[1],
                    "base_url": environment[2],
                    "login": environment[3],
                    "password": environment[4],
                    "created_at": environment[5].isoformat() if environment[5] else None,
                    "updated_at": environment[6].isoformat() if environment[6] else None,
                    "custom_variables": environment[7] if environment[7] else []
                }
                for environment in environments
            ]
    except Exception as e:
        logger.error(f"Error getting project environments: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get project environments: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/projects/{project_id}/environments")
async def create_environment(
    project_id: str,
    environment_data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new environment for a specific project.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if project exists and belongs to user's client
            cursor.execute(
                """
                SELECT id FROM projects
                WHERE id = %s AND client_id = %s
                """,
                (project_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Project not found"
                )
            
            # Extract custom variables if provided
            custom_variables = environment_data.get("custom_variables", {})
            
            # Create the environment
            cursor.execute(
                """
                INSERT INTO environments (name, base_url, login, password, project_id, custom_variables)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, name, base_url, login, password, created_at, updated_at, custom_variables
                """,
                (
                    environment_data.get("name"),
                    environment_data.get("base_url"),
                    environment_data.get("login"),
                    environment_data.get("password"),
                    project_id,
                    json.dumps(custom_variables)
                )
            )
            environment = cursor.fetchone()
            conn.commit()
            
            return {
                "id": environment[0],
                "name": environment[1],
                "base_url": environment[2],
                "login": environment[3],
                "password": environment[4],
                "created_at": environment[5].isoformat() if environment[5] else None,
                "updated_at": environment[6].isoformat() if environment[6] else None,
                "custom_variables": environment[7]
            }
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error creating environment: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create environment: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.put("/api/environments/{environment_id}")
async def update_environment(
    environment_id: int,
    environment_data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing environment.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if environment exists and belongs to user's client
            cursor.execute(
                """
                SELECT e.id FROM environments e
                JOIN projects p ON e.project_id = p.id
                WHERE e.id = %s AND p.client_id = %s
                """,
                (environment_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Environment not found"
                )
            
            # Extract custom variables if provided
            custom_variables = environment_data.get("custom_variables", {})
            
            # Update the environment
            cursor.execute(
                """
                UPDATE environments
                SET name = %s, base_url = %s, login = %s, password = %s, custom_variables = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, name, base_url, login, password, project_id, created_at, updated_at, custom_variables
                """,
                (
                    environment_data.get("name"),
                    environment_data.get("base_url"),
                    environment_data.get("login"),
                    environment_data.get("password"),
                    json.dumps(custom_variables),
                    environment_id
                )
            )
            environment = cursor.fetchone()
            conn.commit()
            
            return {
                "id": environment[0],
                "name": environment[1],
                "base_url": environment[2],
                "login": environment[3],
                "password": environment[4],
                "project_id": environment[5],
                "created_at": environment[6].isoformat() if environment[6] else None,
                "updated_at": environment[7].isoformat() if environment[7] else None,
                "custom_variables": environment[8]
            }
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error updating environment: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update environment: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/environments/{environment_id}/select")
async def select_environment(
    environment_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Track environment selection for analytics and potential pre-loading.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify environment exists and belongs to user's client
            cursor.execute(
                """
                SELECT e.id, e.name, e.base_url FROM environments e
                JOIN projects p ON e.project_id = p.id
                WHERE e.id = %s AND p.client_id = %s
                """,
                (environment_id, str(current_user.client_id))
            )
            environment = cursor.fetchone()
            
            if not environment:
                raise HTTPException(
                    status_code=404,
                    detail="Environment not found"
                )
            
            # Log environment selection (optional - can be used for analytics)
            logger.info(f"User {current_user.id} selected environment {environment_id} ({environment[1]})")
            
            return {
                "status": "success",
                "environment_id": environment[0],
                "environment_name": environment[1],
                "base_url": environment[2]
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tracking environment selection: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to track environment selection: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.delete("/api/environments/{environment_id}")
async def delete_environment(
    environment_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Delete an environment.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if environment exists and belongs to user's client
            cursor.execute(
                """
                SELECT e.id FROM environments e
                JOIN projects p ON e.project_id = p.id
                WHERE e.id = %s AND p.client_id = %s
                """,
                (environment_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Environment not found"
                )
            
            # Delete the environment
            cursor.execute(
                """
                DELETE FROM environments
                WHERE id = %s
                RETURNING id
                """,
                (environment_id,)
            )
            deleted = cursor.fetchone()
            conn.commit()
            
            if not deleted:
                raise HTTPException(
                    status_code=404,
                    detail="Environment not found"
                )
            
            return {"message": "Environment deleted successfully"}
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error deleting environment: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete environment: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.delete("/api/delete_test_step/{id}")
async def delete_test_step(
    id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a specific test step by ID.
    """
    conn = get_db_connection()
    try:
        # First, check if the test step exists and belongs to the user's client
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Get the client_id of the current user
        client_id = current_user.client_id
        
        # Check if the test step exists and belongs to the user's client
        cur.execute(
            """
            SELECT ts.id, tc.client_id, ts.test_case_id, ts.step_order
            FROM test_steps ts
            JOIN test_cases tc ON ts.test_case_id = tc.id
            WHERE ts.id = %s
            """,
            (id,)
        )
        
        step = cur.fetchone()
        
        if not step:
            raise HTTPException(status_code=404, detail="Test step not found")
        
        # Debug print statements to understand the values
        logger.info(f"Test step client_id: {step['client_id']}, type: {type(step['client_id'])}")
        logger.info(f"User client_id: {client_id}, type: {type(client_id)}")
        
        # Convert both to string for comparison if they're not already strings
        test_step_client_id = str(step['client_id'])
        user_client_id = str(client_id)
        
        logger.info(f"Comparing: '{test_step_client_id}' == '{user_client_id}'")
        
        # Check if the user has permission to delete this test step
        if test_step_client_id != user_client_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this test step")
        
        # Get the step_order and test_case_id before deleting
        deleted_step_order = step['step_order']
        test_case_id = step['test_case_id']
        
        # Delete the test step
        cur.execute(
            """
            DELETE FROM test_steps
            WHERE id = %s
            """,
            (id,)
        )
        
        # Reorder the remaining steps - decrement step_order for all steps with higher order
        if test_case_id is not None and deleted_step_order is not None:
            cur.execute(
                """
                UPDATE test_steps
                SET step_order = step_order - 1
                WHERE test_case_id = %s AND step_order > %s
                """,
                (test_case_id, deleted_step_order)
            )
        
        conn.commit()
        
        # Clear screenshot cache for the deleted step to prevent "No screenshot found" errors
        try:
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            # Clear the screenshot cache key for this step
            cache_key = f"screenshot:step:{id}"
            r.delete(cache_key)
            logger.info(f"Cleared screenshot cache for deleted step {id}")
            
            # Also clear the test case cache to force refresh
            if test_case_id:
                test_case_cache_key = f"test_case:{test_case_id}"
                r.delete(test_case_cache_key)
                logger.info(f"Cleared test case cache for test case {test_case_id}")
        except Exception as cache_error:
            logger.warning(f"Failed to clear screenshot cache: {cache_error}")
        
        return {"status": "success", "message": "Test step deleted successfully"}
    
    except Exception as e:
        conn.rollback()
        # Include more detailed error information for debugging
        error_detail = f"Failed to delete test step: {e}"
        logger.error(f"Error in delete_test_step: {error_detail}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_detail)
    finally:
        return_db_connection(conn)

@app.delete("/api/delete_test_case/{id}")
async def delete_test_case(
    id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a specific test case by ID.
    """
    conn = get_db_connection()
    try:
        # First, check if the test case exists and belongs to the user's client
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Get the client_id of the current user
        client_id = current_user.client_id
        
        # Check if the test case exists and belongs to the user's client
        cur.execute(
            """
            SELECT id, client_id
            FROM test_cases
            WHERE id = %s
            """,
            (id,)
        )
        
        test_case = cur.fetchone()
        
        if not test_case:
            raise HTTPException(status_code=404, detail="Test case not found")
        
        # Debug print statements to understand the values
        logger.info(f"Test case client_id: {test_case['client_id']}, type: {type(test_case['client_id'])}")
        logger.info(f"User client_id: {client_id}, type: {type(client_id)}")
        
        # Convert both to string for comparison if they're not already strings
        test_case_client_id = str(test_case['client_id'])
        user_client_id = str(client_id)
        
        logger.info(f"Comparing: '{test_case_client_id}' == '{user_client_id}'")
        
        # Check if the user has permission to delete this test case
        if test_case_client_id != user_client_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this test case")
        
        # Delete the test case - the ON DELETE CASCADE constraints will automatically
        # delete associated test_steps and test_runs
        cur.execute(
            """
            DELETE FROM test_cases
            WHERE id = %s
            """,
            (id,)
        )
        
        conn.commit()
        
        return {"status": "success", "message": "Test case deleted successfully"}
    
    except Exception as e:
        conn.rollback()
        # Include more detailed error information for debugging
        error_detail = f"Failed to delete test case: {e}"
        logger.error(f"Error in delete_test_case: {error_detail}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_detail)
    finally:
        return_db_connection(conn)

@app.post("/api/test_element_locator")
async def test_element_locator(
    request_data: TestElementLocatorRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Test if an element locator is valid by attempting to find the element on the page.
    Returns whether the element was found and any relevant messages.
    """
    try:
        conn = get_db_connection()
        
        # Get environment details if provided
        environment = None
        if request_data.environment_id:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(
                "SELECT * FROM environments WHERE id = %s",
                (request_data.environment_id,)
            )
            environment = cursor.fetchone()
            cursor.close()
            
            if not environment:
                return_db_connection(conn)
                raise HTTPException(status_code=404, detail="Environment not found")
        
        # Get test case details if provided
        test_case = None
        if request_data.test_case_id:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(
                "SELECT * FROM test_cases WHERE id = %s",
                (request_data.test_case_id,)
            )
            test_case = cursor.fetchone()
            cursor.close()
            
            if not test_case:
                return_db_connection(conn)
                raise HTTPException(status_code=404, detail="Test case not found")
        
        # Initialize the test runner
        test_runner = TestRunner(user_id=str(current_user.id), test_case_id=request_data.test_case_id if request_data.test_case_id else None)
        
        # Set up environment variables if an environment was provided
        if environment:
            base_url = environment['base_url']
            login = environment.get('login')
            password = environment.get('password')
            
            # Clean up any existing browser instance and create a new one
            test_runner._cleanup_browser()
            test_runner.browser = BrowserAutomation(headless=False)
            
            # Navigate to the base URL
            test_runner.browser.navigate(base_url)
            
            # Try to find the element using the provided locator
            try:
                element = test_runner.browser.find_element(request_data.element_path)
                is_valid = element is not None
                message = "Element found successfully" if is_valid else "Element not found"
            except Exception as e:
                is_valid = False
                message = f"Error finding element: {str(e)}"
            finally:
                # Always clean up the browser
                test_runner._cleanup_browser()
            
            return_db_connection(conn)
            return {
                "valid": is_valid,
                "message": message
            }
        else:
            # If no environment was provided, we can't test the locator
            return_db_connection(conn)
            return {
                "valid": False,
                "message": "No environment selected. Please select an environment to test the locator."
            }
    
    except Exception as e:
        # Log the exception for debugging
        logging.error(f"Error testing element locator: {str(e)}")
        logging.error(traceback.format_exc())
        
        # Return an error response
        raise HTTPException(
            status_code=500,
            detail=f"Error testing element locator: {str(e)}"
        )

@app.get("/api/test_groups")
async def get_test_groups(current_user: User = Depends(get_current_user)):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Get all test groups for the user's client
            cur.execute(
                """
                SELECT id, name, description, parent_id, "order", created_at, updated_at
                FROM test_cases
                WHERE client_id = %s AND type = 'group'
                ORDER BY "order"
                """,
                (str(current_user.client_id),)
            )
            groups = cur.fetchall()
            
            # Format the response
            formatted_groups = []
            for group in groups:
                formatted_group = {
                    "id": group[0],
                    "name": group[1],
                    "description": group[2],
                    "parent_id": group[3],
                    "order": group[4],
                    "created_at": group[5].isoformat() if group[5] else None,
                    "updated_at": group[6].isoformat() if group[6] else None,
                    "children": []
                }
                formatted_groups.append(formatted_group)
            
            # Build the tree structure
            group_map = {group["id"]: group for group in formatted_groups}
            root_groups = []
            
            for group in formatted_groups:
                if group["parent_id"] is None:
                    root_groups.append(group)
                else:
                    parent = group_map.get(group["parent_id"])
                    if parent:
                        parent["children"].append(group)
            
            return root_groups

@app.post("/api/test_groups", status_code=status.HTTP_201_CREATED)
async def create_test_group(
    request_data: CreateTestGroupRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new test group.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if the parent exists and is a valid group or root
            if request_data.parent_id:
                cur.execute(
                    "SELECT type FROM test_cases WHERE id = %s",
                    (request_data.parent_id,)
                )
                parent = cur.fetchone()
                if not parent:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Parent group not found"
                    )
                if parent[0] != 'group' and parent[0] != 'root':
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Parent must be a group or root"
                    )
            
            # Convert UUID to string for database storage
            project_id_str = str(request_data.project_id) if request_data.project_id else None
            client_id_str = str(current_user.client_id) if current_user.client_id else None
            
            logger.info(f"Debug - Request data: {request_data}")
            logger.info(f"Debug - Project ID (raw): {request_data.project_id}, type: {type(request_data.project_id)}")
            logger.info(f"Debug - Project ID (string): {project_id_str}")
            logger.info(f"Debug - Client ID: {client_id_str}")
            
            # Insert the new group
            cur.execute(
                """
                INSERT INTO test_cases (name, parent_id, type, "order", client_id, project_id)
                VALUES (%s, %s, 'group', 1, %s, %s)
                RETURNING id, name, parent_id, type, "order", created_at, updated_at, project_id
                """,
                (
                    request_data.name,
                    request_data.parent_id,
                    client_id_str,
                    project_id_str
                )
            )
            group = cur.fetchone()
            conn.commit()
            
            # Log the created group
            logger.info(f"Debug - Created group: {group}")
            logger.info(f"Debug - Group project_id: {group[7]}")
            
            # Format the response
            return {
                "id": group[0],
                "name": group[1],
                "parent_id": group[2],
                "type": group[3],
                "order": group[4],
                "created_at": group[5].isoformat() if group[5] else None,
                "updated_at": group[6].isoformat() if group[6] else None,
                "project_id": group[7]
            }
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating test group: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create test group: {str(e)}"
        )
    finally:
        return_db_connection(conn)

@app.put("/api/test_groups/{group_id}")
async def update_test_group(
    group_id: int,
    request_data: UpdateTestGroupRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Update a test group's name.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if the group exists and belongs to the user's client
            cur.execute(
                """
                SELECT id, type, client_id 
                FROM test_cases 
                WHERE id = %s
                """,
                (group_id,)
            )
            group = cur.fetchone()
            
            if not group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test group not found"
                )
            
            if group[1] != 'group':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The specified ID is not a test group"
                )
            
            # Convert client_id to string for comparison
            group_client_id = str(group[2]) if group[2] else None
            user_client_id = str(current_user.client_id) if current_user.client_id else None
            
            logger.info(f"Debug - Group client_id: {group_client_id}")
            logger.info(f"Debug - User client_id: {user_client_id}")
            
            # Skip permission check if client_id is None (for development/testing)
            if group_client_id and user_client_id and group_client_id != user_client_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to update this group"
                )
            
            # Update the group name
            cur.execute(
                """
                UPDATE test_cases
                SET name = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, name, parent_id, type, "order", created_at, updated_at
                """,
                (request_data.name, group_id)
            )
            updated_group = cur.fetchone()
            conn.commit()
            
            # Format the response
            return {
                "id": updated_group[0],
                "name": updated_group[1],
                "parent_id": updated_group[2],
                "type": updated_group[3],
                "order": updated_group[4],
                "created_at": updated_group[5].isoformat() if updated_group[5] else None,
                "updated_at": updated_group[6].isoformat() if updated_group[6] else None
            }
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update test group: {str(e)}"
        )
    finally:
        return_db_connection(conn)

@app.delete("/api/test_groups/{group_id}")
async def delete_test_group(
    group_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a test group if it has no test cases.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if the group exists and belongs to the user's client
            cur.execute(
                """
                SELECT id, type, client_id 
                FROM test_cases 
                WHERE id = %s
                """,
                (group_id,)
            )
            group = cur.fetchone()
            
            if not group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test group not found"
                )
            
            if group[1] != 'group':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The specified ID is not a test group"
                )
            
            # Convert client_id to string for comparison
            group_client_id = str(group[2]) if group[2] else None
            user_client_id = str(current_user.client_id) if current_user.client_id else None
            
            logger.info(f"Debug - Group client_id: {group_client_id}")
            logger.info(f"Debug - User client_id: {user_client_id}")
            
            # Skip permission check if client_id is None (for development/testing)
            if group_client_id and user_client_id and group_client_id != user_client_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to delete this group"
                )
            
            # Check if the group has any test cases or subgroups
            cur.execute(
                """
                SELECT COUNT(*) 
                FROM test_cases 
                WHERE parent_id = %s
                """,
                (group_id,)
            )
            count = cur.fetchone()[0]
            
            if count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete a group that contains test cases or subgroups"
                )

            # Delete the group
            cur.execute(
                """
                DELETE FROM test_cases
                WHERE id = %s
                """,
                (group_id,)
            )
            conn.commit()
            
            return {"message": "Test group deleted successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete test group: {str(e)}"
        )
    finally:
        return_db_connection(conn)

@app.post("/api/test_cases", status_code=status.HTTP_201_CREATED)
async def create_test_case(
    request_data: CreateTestCaseRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new test case manually.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if the parent exists and is a valid group or root
            if request_data.parent_id:
                cur.execute(
                    "SELECT type FROM test_cases WHERE id = %s",
                    (request_data.parent_id,)
                )
                parent = cur.fetchone()
                if not parent:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Parent group not found"
                    )
                if parent[0] != 'group' and parent[0] != 'root':
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Parent must be a group or root"
                    )
            
            # Convert UUID to string for database storage
            project_id_str = str(request_data.project_id) if request_data.project_id else None
            client_id_str = str(current_user.client_id) if current_user.client_id else None
            
            logger.info(f"Debug - Project ID: {project_id_str}")
            logger.info(f"Debug - Client ID: {client_id_str}")
            
            # Insert the new test case
            cur.execute(
                """
                INSERT INTO test_cases (name, description, parent_id, type, "order", client_id, project_id, test_type)
                VALUES (%s, %s, %s, 'test', 1, %s, %s, %s)
                RETURNING id, name, description, parent_id, type, "order", created_at, updated_at, project_id, test_type
                """,
                (
                    request_data.name,
                    request_data.description,
                    request_data.parent_id,
                    client_id_str,
                    project_id_str,
                    request_data.test_type
                )
            )
            test_case = cur.fetchone()
            conn.commit()
            
            # Format the response
            return {
                "id": test_case[0],
                "name": test_case[1],
                "description": test_case[2],
                "parent_id": test_case[3],
                "type": test_case[4],
                "order": test_case[5],
                "created_at": test_case[6].isoformat() if test_case[6] else None,
                "updated_at": test_case[7].isoformat() if test_case[7] else None,
                "project_id": test_case[8],
                "test_type": test_case[9]
            }
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating test case: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create test case: {str(e)}"
        )
    finally:
        return_db_connection(conn)

@app.post("/api/test_cases/move")
async def move_test_case(
    request_data: MoveTestCaseRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Move a test case to a different group.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if the test case exists and belongs to the user's client
            cur.execute(
                """
                SELECT id, client_id 
                FROM test_cases 
                WHERE id = %s
                """,
                (request_data.test_case_id,)
            )
            test_case = cur.fetchone()
            
            if not test_case:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test case not found"
                )
            
            # Convert client_id to string for comparison
            test_case_client_id = str(test_case[1]) if test_case[1] else None
            user_client_id = str(current_user.client_id) if current_user.client_id else None
            
            logger.info(f"Debug - Test case client_id: {test_case_client_id}")
            logger.info(f"Debug - User client_id: {user_client_id}")
            
            # Skip permission check if client_id is None (for development/testing)
            if test_case_client_id and user_client_id and test_case_client_id != user_client_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to move this test case"
                )
            
            # Check if the target group exists and is a valid group (ONLY if not moving to root)
            if request_data.target_group_id is not None:
                cur.execute(
                    """
                    SELECT id, type, client_id 
                    FROM test_cases 
                    WHERE id = %s
                    """,
                    (request_data.target_group_id,)
                )
                target_group = cur.fetchone()
                
                if not target_group:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Target group not found"
                    )
                
                if target_group[1] != 'group' and target_group[1] != 'root':
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Target must be a group or root"
                    )
                
                # Convert target group client_id to string for comparison
                target_group_client_id = str(target_group[2]) if target_group[2] else None
                
                logger.info(f"Debug - Target group client_id: {target_group_client_id}")
                
                # Skip permission check if client_id is None (for development/testing)
                if target_group_client_id and user_client_id and target_group_client_id != user_client_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You don't have permission to move to this group"
                    )
            
            # Update the test case's parent_id
            try:
                cur.execute(
                    """
                    UPDATE test_cases
                    SET parent_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, name, parent_id, type, "order"
                    """,
                    (request_data.target_group_id, request_data.test_case_id)
                )
                updated_test_case = cur.fetchone()
                conn.commit()
                
                if not updated_test_case:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Failed to update test case"
                    )
                
                # Return a simplified response without datetime fields
                return {
                    "id": updated_test_case[0],
                    "name": updated_test_case[1],
                    "parent_id": updated_test_case[2],
                    "type": updated_test_case[3],
                    "order": updated_test_case[4],
                    "message": "Test case moved successfully"
                }
            except Exception as sql_error:
                conn.rollback()
                logger.error(f"SQL Error: {str(sql_error)}")
                traceback.print_exc()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database error: {str(sql_error)}"
                )
    except Exception as e:
        conn.rollback()
        logger.error(f"Error in move_test_case: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to move test case: {str(e)}"
        )
    finally:
        return_db_connection(conn)

@app.put("/api/test_cases/{id}")
async def update_test_case(
    id: int,
    request_data: UpdateTestCaseRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing test case's name and description.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if the test case exists and belongs to the user's client
            cur.execute("SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                        (id, str(current_user.client_id)))
            test_case = cur.fetchone()
            if not test_case:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test case not found"
                )
            
            # Update the test case
            if request_data.parent_id is not None:
                update_fields = ["name = %s", "description = %s", "parent_id = %s", "updated_at = NOW()"]
                update_values = [request_data.name, request_data.description, request_data.parent_id]
                
                if request_data.test_type is not None:
                    update_fields.append("test_type = %s")
                    update_values.append(request_data.test_type)
                
                update_values.append(id)
                
                cur.execute(
                    f"""
                    UPDATE test_cases 
                    SET {', '.join(update_fields)}
                    WHERE id = %s
                    RETURNING id, name, description, parent_id, type, "order", created_at, updated_at, project_id, test_type
                    """,
                    update_values
                )
            else:
                update_fields = ["name = %s", "description = %s", "updated_at = NOW()"]
                update_values = [request_data.name, request_data.description]
                
                if request_data.test_type is not None:
                    update_fields.append("test_type = %s")
                    update_values.append(request_data.test_type)
                
                update_values.append(id)
                
                cur.execute(
                    f"""
                    UPDATE test_cases 
                    SET {', '.join(update_fields)}
                    WHERE id = %s
                    RETURNING id, name, description, parent_id, type, "order", created_at, updated_at, project_id, test_type
                    """,
                    update_values
                )
            updated_test_case = cur.fetchone()
            conn.commit()
            
            # Format the response
            return {
                "id": updated_test_case[0],
                "name": updated_test_case[1],
                "description": updated_test_case[2],
                "parent_id": updated_test_case[3],
                "type": updated_test_case[4],
                "order": updated_test_case[5],
                "created_at": updated_test_case[6].isoformat() if updated_test_case[6] else None,
                "updated_at": updated_test_case[7].isoformat() if updated_test_case[7] else None,
                "project_id": updated_test_case[8],
                "test_type": updated_test_case[9]
            }
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating test case: {str(e)}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update test case: {str(e)}"
        )
    finally:
        return_db_connection(conn)

@app.get("/api/test_step_screenshot/{step_id}")
async def get_test_step_screenshot(
    step_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve the screenshot for a specific test step.
    Returns the screenshot as binary PNG data.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify permissions through execution results and test runs instead of test steps
            cursor.execute(
                """
                SELECT tser.screenshot_base64, tser.screenshot_path
                FROM test_step_execution_results tser
                JOIN test_runs tr ON tser.test_run_id = tr.id
                JOIN test_cases tc ON tr.test_case_id = tc.id
                WHERE tser.test_step_id = %s AND tc.client_id = %s
                AND (tser.screenshot_base64 IS NOT NULL OR tser.screenshot_path IS NOT NULL)
                ORDER BY tser.started_at DESC
                LIMIT 1
                """,
                (step_id, str(current_user.client_id))
            )
            result = cursor.fetchone()
            logger.debug(f"Screenshot query result for step {step_id}: {'Found' if result else 'Not found'}")
            
            # Debug: Check if step exists at all
            if not result:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM test_step_execution_results 
                    WHERE test_step_id = %s
                    """,
                    (step_id,)
                )
                count_result = cursor.fetchone()
                logger.debug(f"Total execution results for step {step_id}: {count_result[0] if count_result else 0}")
                
                # Check if any have screenshots
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM test_step_execution_results 
                    WHERE test_step_id = %s AND (screenshot_base64 IS NOT NULL OR screenshot_path IS NOT NULL)
                    """,
                    (step_id,)
                )
                screenshot_count = cursor.fetchone()
                logger.debug(f"Execution results with screenshots for step {step_id}: {screenshot_count[0] if screenshot_count else 0}")
            
            # If not found in new system, try old screenshots table
            if not result:
                # logger.info(f"Screenshot request {step_id} - No result from new system, trying old screenshots table")
                # Try old system
                cursor.execute(
                    """
                    SELECT screenshot, description
                    FROM screenshots
                    WHERE test_step_id = %s
                    LIMIT 1
                    """,
                    (step_id,)
                )
                result = cursor.fetchone()
                # logger.info(f"Screenshot request {step_id} - Old system query result: {'Found' if result else 'Not found'}")
            else:
                # logger.info(f"Screenshot request {step_id} - Found result in new system (test_step_execution_results)")
                pass
            
            if not result:
                logger.debug(f"No screenshot found for step {step_id} with client_id {current_user.client_id}")
                # Return JSON response indicating no screenshot available
                # Add cache headers to prevent repeated requests for missing screenshots
                return JSONResponse(
                    content={
                        "screenshot_available": False,
                        "message": "No screenshot found for this test step"
                    },
                    headers={
                        "X-Screenshot-Available": "false"
                    }
                )
            
            # Check if this is from old system (screenshots table) or new system
            if len(result) == 2 and hasattr(result, '__getitem__'):
                # This is from old system - result[0] is binary/base64, result[1] is description
                screenshot_data = result[0]
                if isinstance(screenshot_data, memoryview):
                    screenshot_data = bytes(screenshot_data)
                
                if isinstance(screenshot_data, bytes):
                    # This is binary data, return directly as StreamingResponse
                    import io
                    # logger.info(f"Screenshot request {step_id} - Returning binary data from old system")
                    return StreamingResponse(
                        io.BytesIO(screenshot_data),
                        media_type="image/png",
                        headers={"Content-Disposition": "inline; filename=screenshot.png"}
                    )
                else:
                    # This is base64 string from old system - set it for processing below
                    # logger.info(f"Screenshot request {step_id} - Processing base64 from old system")
                    screenshot_base64 = screenshot_data
            else:
                # Handle new system format - result[0] is base64 string, result[1] is screenshot_path
                # logger.info(f"Screenshot request {step_id} - Processing data from new system")
                screenshot_base64 = result[0]
                screenshot_path = result[1]
                
                # If no base64 data but we have a path, try to read the file
                if not screenshot_base64 and screenshot_path:
                    try:
                        import os
                        import base64
                        if os.path.exists(screenshot_path):
                            with open(screenshot_path, "rb") as img_file:
                                screenshot_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                    except Exception as file_error:
                        logger.error(f"Error reading screenshot file {screenshot_path}: {file_error}")
                        return JSONResponse(content={
                            "screenshot_available": False,
                            "message": "Screenshot file not accessible"
                        })
                
                # If still no screenshot data, return error
                if not screenshot_base64:
                    return JSONResponse(content={
                        "screenshot_available": False,
                        "message": "No screenshot data available"
                    })
            
            # Decode base64 to binary data for FileResponse
            import base64
            import io
            try:
                # Clean base64 data by removing whitespace and line breaks
                cleaned_base64 = screenshot_base64.replace('\n', '').replace('\r', '').replace(' ', '').strip()
                  
                # Check if base64 data has valid padding
                missing_padding = len(cleaned_base64) % 4
                if missing_padding:
                    cleaned_base64 += '=' * (4 - missing_padding)
 
                screenshot_binary = base64.b64decode(cleaned_base64)
    
                # Check PNG signature (cannot use backslashes in f-string)
                png_signature = b'\x89PNG\r\n\x1a\n'
                is_valid_png = screenshot_binary[:8] == png_signature
 
                # Create a BytesIO object to serve as file-like object
                screenshot_io = io.BytesIO(screenshot_binary)
                
                return StreamingResponse(
                    io.BytesIO(screenshot_binary),
                    media_type="image/png",
                    headers={
                        "Content-Disposition": "inline; filename=screenshot.png",
                        "Content-Length": str(len(screenshot_binary)),
                        "X-Screenshot-Available": "true"
                    }
                )
            except Exception as decode_error:
                logger.error(f"Error decoding base64 screenshot: {decode_error}")
                logger.error(f"Base64 data that failed: {screenshot_base64[:100]}...")
                return JSONResponse(content={
                    "screenshot_available": False,
                    "message": "Error decoding screenshot data"
                })
    except Exception as e:
        # Return JSON response indicating error
        return JSONResponse(content={
            "screenshot_available": False,
            "message": f"Error retrieving screenshot: {str(e)}"
        })
    finally:
        if conn:
            return_db_connection(conn)

@app.get("/api/test_run/{run_id}/steps")
async def get_test_run_steps(
    run_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve all steps for a specific test run with their execution details.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # First verify that the test run belongs to the current user's client
            cursor.execute(
                """
                SELECT tr.id 
                FROM test_runs tr
                JOIN test_cases tc ON tr.test_case_id = tc.id
                WHERE tr.id = %s AND tc.client_id = %s
                """,
                (run_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Test run not found or you don't have permission to access it"
                )
            
            # Get the test case ID for this run
            cursor.execute(
                "SELECT test_case_id FROM test_runs WHERE id = %s",
                (run_id,)
            )
            test_case_id = cursor.fetchone()[0]
            
            # Get all steps for this test case with their execution results and screenshot info
            cursor.execute(
                """
                SELECT ts.id, ts.step_order, ts.description, ts.action, ts.element_path, ts.value,
                       CASE WHEN (tser.screenshot_base64 IS NOT NULL OR tser.screenshot_path IS NOT NULL) THEN true ELSE false END as has_screenshot,
                       tser.status, tser.error_message, tser.execution_time_ms, tser.completed_at,
                       tser.screenshot_path, tser.screenshot_base64
                FROM test_steps ts
                LEFT JOIN test_step_execution_results tser ON ts.id = tser.test_step_id AND tser.test_run_id = %s
                WHERE ts.test_case_id = %s
                ORDER BY ts.step_order
                """,
                (run_id, test_case_id)
            )
            steps = []
            for row in cursor.fetchall():
                steps.append({
                    "id": row[0],
                    "test_step_id": row[0],  # Add explicit test_step_id for screenshot API
                    "step_order": row[1],
                    "description": row[2],
                    "action": row[3],
                    "element_path": row[4],
                    "value": row[5],
                    "has_screenshot": row[6],
                    "status": row[7] if row[7] else "not_executed",
                    "error_message": row[8],
                    "execution_time_ms": row[9],
                    "completed_at": row[10],
                    "screenshot_path": row[11],
                    "screenshot_base64": bool(row[12]) if row[12] else False  # Boolean flag for frontend
                })
            
            return {"steps": steps, "test_case_id": test_case_id, "run_id": run_id}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve test run steps: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/cleanup_orphaned_steps")
async def cleanup_orphaned_steps(
    current_user: User = Depends(get_current_user)
):
    """
    Clean up any test steps that have been stuck in 'running' status for more than 5 minutes.
    This handles cases where test execution processes were killed or crashed unexpectedly.
    """
    try:
        from auroqa.Utils.BrowserAutomation.TestRunner import TestRunner
        test_runner = TestRunner()
        test_runner._cleanup_orphaned_running_steps()
        
        return {
            "status": "success",
            "message": "Orphaned running steps have been cleaned up"
        }
    except Exception as e:
        logger.error(f"Failed to cleanup orphaned steps: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup orphaned steps: {str(e)}"
        )

@app.get("/api/test_run/{run_id}/step_execution_results")
async def get_test_run_step_execution_results(
    run_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Retrieve detailed step execution results for a specific test run.
    Includes status, error messages, screenshots, and execution times.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # First verify that the test run belongs to the current user's client
            cursor.execute(
                """
                SELECT tr.id 
                FROM test_runs tr
                JOIN test_cases tc ON tr.test_case_id = tc.id
                WHERE tr.id = %s AND tc.client_id = %s
                """,
                (run_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Test run not found or you don't have permission to access it"
                )
            
            # Get step execution results with preserved step details
            cursor.execute(
                """
                SELECT tser.id, tser.test_step_id, tser.step_order, tser.status,
                       tser.error_message, tser.screenshot_path, tser.execution_time_ms,
                       tser.started_at, tser.completed_at,
                       COALESCE(tser.step_description, ts.description) as description,
                       COALESCE(tser.step_action, ts.action) as action,
                       COALESCE(tser.step_element_path, ts.element_path) as element_path,
                       COALESCE(tser.step_value, ts.value) as value,
                       tr.test_case_id,
                       tser.additional_info
                FROM test_step_execution_results tser
                LEFT JOIN test_steps ts ON tser.test_step_id = ts.id
                JOIN test_runs tr ON tser.test_run_id = tr.id
                WHERE tser.test_run_id = %s
                ORDER BY tser.step_order
                """,
                (run_id,)
            )
            
            step_results = []
            test_case_id = None
            for row in cursor.fetchall():
                if test_case_id is None:
                    test_case_id = row[13]  # Get test_case_id from first row
                
                # Parse additional_info if it exists
                additional_info = row[14] if row[14] else {}
                
                step_results.append({
                    "id": row[0],
                    "test_step_id": row[1],
                    "step_order": row[2],
                    "status": row[3],
                    "error_message": row[4],
                    "screenshot_path": row[5],
                    "execution_time_ms": row[6],
                    "started_at": row[7].isoformat() if row[7] else None,
                    "completed_at": row[8].isoformat() if row[8] else None,
                    "description": row[9],
                    "action": row[10],
                    "element_path": row[11],
                    "value": row[12],
                    "has_screenshot": bool(row[5]),
                    "actual_url": additional_info.get('actual_url') if additional_info else None,
                    "method": additional_info.get('method') if additional_info else None,
                    "request_headers": additional_info.get('request_headers') if additional_info else None,
                    "request_body": additional_info.get('request_body') if additional_info else None
                })
            
            return {
                "step_results": step_results, 
                "test_case_id": test_case_id,
                "run_id": run_id,
                "total_steps": len(step_results)
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve step execution results: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/users/create", response_model=User)
async def create_new_user(user_data: UserCreate, current_user: User = Depends(get_current_user)):
    # Check if the current user is an admin
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can create new users"
        )
    
    # If the new user is 'user' role, client_id is required
    if (user_data.role == 'user' or user_data.role is None) and not user_data.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client is required for users with role 'user'"
        )
    
    # Create the new user
    with get_db_connection() as conn:
        return create_user(conn, user_data)

@app.put("/api/users/{user_id}/role")
async def update_user_role(
    user_id: int, 
    role_data: dict = Body(..., example={"role": "admin"}),
    current_user: User = Depends(get_current_user)
):
    # Check if the current user is an admin
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can update user roles"
        )
    
    # Validate the role
    new_role = role_data.get("role")
    if new_role not in ["admin", "user"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Role must be 'admin' or 'user'"
        )
    
    # Update the user's role
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Check if user exists
            cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Update the role
            cur.execute(
                "UPDATE users SET role = %s WHERE id = %s RETURNING id, email, full_name, is_active, created_at, last_login, client_id, role",
                (new_role, user_id)
            )
            user_data = cur.fetchone()
            conn.commit()
            
            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            return {
                "id": user_data[0],
                "email": user_data[1],
                "full_name": user_data[2],
                "is_active": user_data[3],
                "created_at": user_data[4].isoformat() if user_data[4] else None,
                "last_login": user_data[5].isoformat() if user_data[5] else None,
                "client_id": user_data[6],
                "role": user_data[7]
            }

@app.get("/api/test_case_generation_status/{id}")
async def test_case_generation_status(
    id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Check if a test case is currently generating steps and return the current steps.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # Verify the test case exists and belongs to the user's client
            cursor.execute(
                "SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                (id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Test case not found")
            
            # Check if the test case is currently generating steps (UI or API)
            runner = TestRunner(user_id=str(current_user.id), test_case_id=id)
            is_generating_ui = runner.is_generating_steps(id)
            
            # Also check for API test generation
            is_generating_api = False
            try:
                system = System()
                r = redis.Redis(host=system.redis_host, port=system.redis_port, db=0, decode_responses=True)
                api_gen_key = r.get(f"api_test_generating:{id}")
                is_generating_api = api_gen_key is not None
                logger.debug(f"API generation check for test case {id}: {is_generating_api} (key: {api_gen_key})")
            except Exception as redis_error:
                logger.error(f"Redis error checking API generation: {redis_error}")
            
            is_generating = is_generating_ui or is_generating_api
            
            # Get current and next step information from Redis
            current_step = ""
            next_step = ""
            if is_generating and runner._redis:
                try:
                    current_step = runner._redis.get(f"test_case_current_step:{id}") or ""
                    if isinstance(current_step, bytes):
                        current_step = current_step.decode('utf-8')
                    
                    next_step = runner._redis.get(f"test_case_next_step:{id}") or ""
                    if isinstance(next_step, bytes):
                        next_step = next_step.decode('utf-8')
                except Exception as e:
                    logger.error(f"Error getting step information from Redis: {e}")
            
            # Get the current test steps
            cursor.execute(
                """
                SELECT id, test_case_id, description, action, element_path, value, path_type, expected_result, created_at, updated_at 
                FROM test_steps 
                WHERE test_case_id = %s 
                ORDER BY step_order
                """,
                (id,)
            )
            test_steps = cursor.fetchall()
            
            # Convert to list of dicts
            steps = []
            for step in test_steps:
                step_dict = dict(step)
                # Convert datetime objects to ISO format strings
                for key, value in step_dict.items():
                    if isinstance(value, datetime):
                        step_dict[key] = value.isoformat()
                steps.append(step_dict)
            
            return {
                "is_generating": is_generating,
                "test_steps": steps,
                "current_step": current_step,
                "next_step": next_step
            }
    except Exception as e:
        logger.error(f"Error checking test case generation status: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check test case generation status: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.get("/api/test-cases/{id}/reasoning")
async def get_test_case_reasoning(
    id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get AI reasoning and planning data for a test case during generation.
    Returns thoughts, test split strategy, phases, current step, timeline, and statistics.
    """
    conn = None
    try:
        from auroqa.Services.ReasoningCollector import ReasoningCollector
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify the test case exists and belongs to the user's client
            cursor.execute(
                "SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                (id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Test case not found")
        
        # Get reasoning data from ReasoningCollector
        system = System()
        collector = ReasoningCollector(
            redis_host=system.redis_host,
            redis_port=system.redis_port
        )
        
        reasoning_data = collector.get_reasoning_data(id)
        
        return reasoning_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving reasoning data: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve reasoning data: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/stop_test_case_generation/{id}")
async def stop_test_case_generation(
    id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Stop the generation of test steps for a test case.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify the test case exists and belongs to the user's client
            cursor.execute(
                "SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                (id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Test case not found")
            
            # Get the TestRunner instance and stop the generation
            runner = TestRunner(user_id=str(current_user.id), test_case_id=id)
            runner.stop_generating_steps(id)
            
            # Update the test case's updated_at timestamp
            cursor.execute(
                "UPDATE test_cases SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (id,)
            )
            conn.commit()
            
            return {"status": "stopped"}
    except Exception as e:
        logger.error(f"Error stopping test case generation: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop test case generation: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/stop_test_case_execution/{id}")
async def stop_test_case_execution(
    id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Stop the execution of a test case.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify that the test case exists and belongs to the user's client
            cursor.execute(
                """
                SELECT id FROM test_cases
                WHERE id = %s AND client_id = %s
                """,
                (id, str(current_user.client_id))
            )
            test_case = cursor.fetchone()
            if not test_case:
                raise HTTPException(
                    status_code=404,
                    detail="Test case not found or you don't have permission to access it"
                )
            
            # Use the TestRunner to stop the test case execution
            runner = TestRunner(user_id=str(current_user.id), test_case_id=id)
            runner.stop_test_case_execution(id)
            
            return {"status": "success", "message": "Test case execution stop requested"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop test case execution: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/stop_test_case_execution/{id}")
async def stop_test_case_execution(id: int, request: Request):
    """
    Stop the execution of a test case
    """
    logger.info(f"Received request to stop test case execution for ID: {id}")
    
    # Get test runner instance
    test_runner = get_test_runner()
    
    # Stop test case execution
    result = test_runner.stop_test_case_execution(id)
    
    if result:
        return {"status": "success", "message": "Test case execution stop requested"}
    else:
        return {"status": "error", "message": "Failed to stop test case execution"}

@app.post("/api/stop-all-tests")
async def stop_all_test_executions(current_user: User = Depends(get_current_user)):
    """
    Stop all currently running test executions and API test generation for the current user's client
    """
    logger.info(f"Received request to stop all test executions for user {current_user.id}")
    
    try:
        # Create TestRunner instance
        runner = TestRunner(user_id=str(current_user.id))
        
        # Stop all test executions for this user's client
        result = runner.stop_all_test_executions(
            user_id=str(current_user.id),
            client_id=str(current_user.client_id)
        )
        
        # Update database to mark any running test_runs as stopped (single source of truth)
        generation_stopped_count = 0
        try:
            with get_db_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE test_runs 
                    SET result = 'stopped'
                    WHERE result = 'running' 
                    AND test_case_id IN (
                        SELECT id FROM test_cases WHERE client_id = %s
                    )
                """, (str(current_user.client_id),))
                generation_stopped_count = cursor.rowcount
                conn.commit()
                logger.info(f"Updated database to mark {generation_stopped_count} running test_runs as stopped for client {current_user.client_id}")
                
                # Also clear Redis generation flags so running threads stop
                from auroqa.Utils.System import System
                system = System()
                r = redis.Redis(host=system.redis_host, port=system.redis_port, db=0, decode_responses=True)
                
                # Get all test cases for this client
                cursor.execute("""
                    SELECT id FROM test_cases WHERE client_id = %s
                """, (str(current_user.client_id),))
                test_case_ids = [row[0] for row in cursor.fetchall()]
                
                # Set stop flags for generation threads
                for test_case_id in test_case_ids:
                    stop_key = f"test_case_stop_generating:{test_case_id}"
                    r.set(stop_key, "1", ex=300)
                logger.info(f"All test are marked as stopped")
                    
        except Exception as e:
            logger.error(f"Error while stopping all tests: {e}")
        
        if result["status"] == "success":
            total_stopped = result["stopped_count"] + generation_stopped_count
            return {
                "status": "success", 
                "message": f"Stopped {result['stopped_count']} test executions and {generation_stopped_count} test generations",
                "stopped_count": total_stopped,
                "executions_stopped": result["stopped_count"],
                "generations_stopped": generation_stopped_count
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result["message"]
            )
            
    except Exception as e:
        logger.error(f"Failed to stop all test executions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop all test executions: {str(e)}"
        )

# AI Model Management Endpoints

class AIModelCreate(BaseModel):
    name: str
    model_id: str
    description: Optional[str] = None
    is_active: Optional[bool] = True
    is_default: Optional[bool] = False
    input_price_per_1m: Optional[float] = 0
    output_price_per_1m: Optional[float] = 0
    tier_threshold: Optional[int] = 0
    input_price_per_1m_above: Optional[float] = None
    output_price_per_1m_above: Optional[float] = None
    cache_input_price_per_1m: Optional[float] = 0
    cache_input_price_per_1m_above: Optional[float] = None
    cache_storage_price_per_1m_hour: Optional[float] = 0

class AIModelUpdate(BaseModel):
    name: Optional[str] = None
    model_id: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    input_price_per_1m: Optional[float] = None
    output_price_per_1m: Optional[float] = None
    tier_threshold: Optional[int] = None
    input_price_per_1m_above: Optional[float] = None
    output_price_per_1m_above: Optional[float] = None
    cache_input_price_per_1m: Optional[float] = None
    cache_input_price_per_1m_above: Optional[float] = None
    cache_storage_price_per_1m_hour: Optional[float] = None

@app.get("/api/ai-models", response_model=List[Dict])
async def list_ai_models(current_user: User = Depends(get_current_user)):
    """
    List all available AI models with pricing information.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT id, name, model_id, description, is_active, is_default, 
                       input_price_per_1m, output_price_per_1m, tier_threshold,
                       input_price_per_1m_above, output_price_per_1m_above,
                       cache_input_price_per_1m, cache_input_price_per_1m_above,
                       cache_storage_price_per_1m_hour,
                       created_at, updated_at
                FROM ai_models
                ORDER BY name
            """)
            models = cursor.fetchall()
            
            # Check if the user has a preferred model
            cursor.execute("""
                SELECT ai_model_id, vlm_enabled
                FROM user_ai_models
                WHERE user_id = %s
            """, (current_user.id,))
            user_model = cursor.fetchone()
            
            # Add is_user_selected flag and vlm_enabled to each model
            for model in models:
                is_selected = user_model and model['id'] == user_model['ai_model_id']
                model['is_user_selected'] = is_selected
                if is_selected:
                    model['vlm_enabled'] = user_model['vlm_enabled']
                
            return models
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list AI models: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/ai-models", response_model=Dict)
async def create_ai_model(model_data: AIModelCreate, current_user: User = Depends(get_current_user)):
    """
    Create a new AI model. Admin only.
    """
    # Check if user is admin
    check_admin_role(current_user)
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if model_id already exists
            cursor.execute("""
                SELECT id FROM ai_models WHERE model_id = %s
            """, (model_data.model_id,))
            if cursor.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail=f"AI model with model_id '{model_data.model_id}' already exists"
                )
            
            # If this model is set as default, unset any existing default
            if model_data.is_default:
                cursor.execute("""
                    UPDATE ai_models SET is_default = FALSE WHERE is_default = TRUE
                """)
            
            # Insert new model with pricing
            cursor.execute("""
                INSERT INTO ai_models (
                    name, model_id, description, is_active, is_default,
                    input_price_per_1m, output_price_per_1m, tier_threshold,
                    input_price_per_1m_above, output_price_per_1m_above,
                    cache_input_price_per_1m, cache_input_price_per_1m_above,
                    cache_storage_price_per_1m_hour
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                model_data.name,
                model_data.model_id,
                model_data.description,
                model_data.is_active,
                model_data.is_default,
                model_data.input_price_per_1m or 0,
                model_data.output_price_per_1m or 0,
                model_data.tier_threshold or 0,
                model_data.input_price_per_1m_above,
                model_data.output_price_per_1m_above,
                model_data.cache_input_price_per_1m or 0,
                model_data.cache_input_price_per_1m_above,
                model_data.cache_storage_price_per_1m_hour or 0
            ))
            model_id = cursor.fetchone()[0]
            conn.commit()
            
            return {"id": model_id, "message": "AI model created successfully"}
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create AI model: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.put("/api/ai-models/{model_id}", response_model=Dict)
async def update_ai_model(
    model_id: int,
    model_data: AIModelUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing AI model. Admin only.
    """
    # Check if user is admin
    check_admin_role(current_user)
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if model exists
            cursor.execute("""
                SELECT id FROM ai_models WHERE id = %s
            """, (model_id,))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail=f"AI model with ID {model_id} not found"
                )
            
            # If this model is set as default, unset any existing default
            if model_data.is_default:
                cursor.execute("""
                    UPDATE ai_models SET is_default = FALSE WHERE is_default = TRUE
                """)
            
            # Build update query dynamically based on provided fields
            update_fields = []
            params = []
            
            if model_data.name is not None:
                update_fields.append("name = %s")
                params.append(model_data.name)
                
            if model_data.model_id is not None:
                update_fields.append("model_id = %s")
                params.append(model_data.model_id)
                
            if model_data.description is not None:
                update_fields.append("description = %s")
                params.append(model_data.description)
                
            if model_data.is_active is not None:
                update_fields.append("is_active = %s")
                params.append(model_data.is_active)
                
            if model_data.is_default is not None:
                update_fields.append("is_default = %s")
                params.append(model_data.is_default)
            
            if model_data.input_price_per_1m is not None:
                update_fields.append("input_price_per_1m = %s")
                params.append(model_data.input_price_per_1m)
            
            if model_data.output_price_per_1m is not None:
                update_fields.append("output_price_per_1m = %s")
                params.append(model_data.output_price_per_1m)
            
            if model_data.tier_threshold is not None:
                update_fields.append("tier_threshold = %s")
                params.append(model_data.tier_threshold)
            
            if model_data.input_price_per_1m_above is not None:
                update_fields.append("input_price_per_1m_above = %s")
                params.append(model_data.input_price_per_1m_above)
            
            if model_data.output_price_per_1m_above is not None:
                update_fields.append("output_price_per_1m_above = %s")
                params.append(model_data.output_price_per_1m_above)
            
            if model_data.cache_input_price_per_1m is not None:
                update_fields.append("cache_input_price_per_1m = %s")
                params.append(model_data.cache_input_price_per_1m)
            
            if model_data.cache_input_price_per_1m_above is not None:
                update_fields.append("cache_input_price_per_1m_above = %s")
                params.append(model_data.cache_input_price_per_1m_above)
            
            if model_data.cache_storage_price_per_1m_hour is not None:
                update_fields.append("cache_storage_price_per_1m_hour = %s")
                params.append(model_data.cache_storage_price_per_1m_hour)
            
            # Add updated_at timestamp
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            
            # Execute update if there are fields to update
            if update_fields:
                query = f"UPDATE ai_models SET {', '.join(update_fields)} WHERE id = %s"
                params.append(model_id)
                cursor.execute(query, params)
                conn.commit()
            
            return {"message": "AI model updated successfully"}
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update AI model: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.delete("/api/ai-models/{model_id}", response_model=Dict)
async def delete_ai_model(
    model_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Delete an AI model. Admin only.
    """
    # Check if user is admin
    check_admin_role(current_user)
    
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if model exists
            cursor.execute("""
                SELECT is_default FROM ai_models WHERE id = %s
            """, (model_id,))
            model = cursor.fetchone()
            if not model:
                raise HTTPException(
                    status_code=404,
                    detail=f"AI model with ID {model_id} not found"
                )
            
            # Don't allow deletion of default model
            if model[0]:  # is_default
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete the default AI model"
                )
            
            # Delete model
            cursor.execute("""
                DELETE FROM ai_models WHERE id = %s
            """, (model_id,))
            conn.commit()
            
            return {"message": "AI model deleted successfully"}
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete AI model: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

@app.post("/api/user-ai-model", response_model=Dict)
async def set_user_ai_model(
    model_data: dict = Body(..., example={"ai_model_id": 1, "vlm_enabled": False}),
    current_user: User = Depends(get_current_user)
):
    """
    Set the user's preferred AI model and VLM setting.
    """
    conn = None
    try:
        ai_model_id = model_data.get("ai_model_id")
        vlm_enabled = model_data.get("vlm_enabled", False)  # Default to False if not provided
        
        if not ai_model_id:
            raise HTTPException(
                status_code=400,
                detail="ai_model_id is required"
            )
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Check if model exists and is active
            cursor.execute("""
                SELECT id FROM ai_models WHERE id = %s AND is_active = TRUE
            """, (ai_model_id,))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail=f"Active AI model with ID {ai_model_id} not found"
                )
            
            # Check if user already has a preferred model
            cursor.execute("""
                SELECT user_id FROM user_ai_models WHERE user_id = %s
            """, (current_user.id,))
            user_model = cursor.fetchone()
            
            if user_model:
                # Update existing preference
                cursor.execute("""
                    UPDATE user_ai_models 
                    SET ai_model_id = %s, vlm_enabled = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                """, (ai_model_id, vlm_enabled, current_user.id))
            else:
                # Insert new preference
                cursor.execute("""
                    INSERT INTO user_ai_models (user_id, ai_model_id, vlm_enabled)
                    VALUES (%s, %s, %s)
                """, (current_user.id, ai_model_id, vlm_enabled))
            
            conn.commit()
            return {"message": "User AI model preference updated successfully"}
    except HTTPException:
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to set user AI model preference: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

# AI Usage Tracking Endpoints

@app.get("/api/ai-usage/stats", response_model=Dict)
async def get_ai_usage_stats(
    current_user: User = Depends(get_current_user),
    client_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Get AI usage statistics (tokens and costs).
    Admin can see all clients, regular users see their own client.
    """
    try:
        from auroqa.Services.AIRequestLogger import AIRequestLogger
        from datetime import datetime
        
        logger = AIRequestLogger()
        
        # Determine which client to query
        query_client_id = client_id
        if not current_user.is_admin and client_id and client_id != current_user.client_id:
            raise HTTPException(
                status_code=403,
                detail="You can only view usage for your own client"
            )
        
        if not current_user.is_admin and not client_id:
            query_client_id = current_user.client_id
        
        # Parse dates if provided
        start = None
        end = None
        if start_date:
            start = datetime.fromisoformat(start_date)
        if end_date:
            end = datetime.fromisoformat(end_date)
        
        stats = logger.get_usage_stats(
            client_id=query_client_id,
            start_date=start,
            end_date=end
        )
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get AI usage stats: {str(e)}"
        )

@app.get("/api/ai-usage/by-type", response_model=Dict)
async def get_ai_usage_by_type(
    current_user: User = Depends(get_current_user),
    client_id: Optional[str] = None
):
    """
    Get AI usage statistics grouped by request type.
    Request types: ui_step, ui_error, api_test, api_schema, image_analysis, text_analysis, other
    """
    try:
        from auroqa.Services.AIRequestLogger import AIRequestLogger
        
        logger = AIRequestLogger()
        
        # Determine which client to query
        query_client_id = client_id
        if not current_user.is_admin and client_id and client_id != current_user.client_id:
            raise HTTPException(
                status_code=403,
                detail="You can only view usage for your own client"
            )
        
        if not current_user.is_admin and not client_id:
            query_client_id = current_user.client_id
        
        stats = logger.get_request_type_stats(client_id=query_client_id)
        
        return {"by_type": stats}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get AI usage by type: {str(e)}"
        )

@app.get("/api/ai-usage/requests", response_model=Dict)
async def get_ai_request_logs(
    current_user: User = Depends(get_current_user),
    client_id: Optional[str] = None,
    request_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """
    Get detailed AI request logs with pagination.
    """
    conn = None
    try:
        # Determine which client to query
        query_client_id = client_id
        if not current_user.is_admin and client_id and client_id != current_user.client_id:
            raise HTTPException(
                status_code=403,
                detail="You can only view logs for your own client"
            )
        
        if not current_user.is_admin and not client_id:
            query_client_id = current_user.client_id
        
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            # Build query
            where_clauses = []
            params = []
            
            if query_client_id:
                where_clauses.append("client_id = %s")
                params.append(query_client_id)
            
            if request_type:
                where_clauses.append("request_type = %s")
                params.append(request_type)
            
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Get total count
            cursor.execute(f"""
                SELECT COUNT(*) FROM ai_request_logs WHERE {where_clause}
            """, params)
            total_count = cursor.fetchone()[0]
            
            # Get paginated results
            cursor.execute(f"""
                SELECT 
                    id, ai_model_id, client_id, user_id, request_type, request_context,
                    input_tokens, output_tokens, total_tokens,
                    input_cost, output_cost, total_cost,
                    prompt_length, response_length, response_time_ms,
                    status, error_message, created_at
                FROM ai_request_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, params + [limit, offset])
            
            requests = cursor.fetchall()
            
            return {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "requests": requests
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get AI request logs: {str(e)}"
        )
    finally:
        if conn:
            return_db_connection(conn)

from auroqa.models.contact import ContactRequest, ContactRequestResponse

# Contact Request Endpoints

@app.post("/api/contact", response_model=dict)
async def submit_contact_request(
    request_data: ContactRequest,
):
    """
    Submit a contact request from the landing page.
    This endpoint is public and does not require authentication.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Insert the contact request
        cursor.execute(
            """
            INSERT INTO contact_requests (name, message)
            VALUES (%s, %s)
            RETURNING id
            """,
            (request_data.name, request_data.message)
        )
        
        new_id = cursor.fetchone()[0]
        conn.commit()
        
        return {"success": True, "id": new_id, "message": "Contact request submitted successfully"}
    except Exception as e:
        conn.rollback()
        logging.error(f"Error submitting contact request: {str(e)}")
        logging.error(traceback.format_exc())
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "message": f"Error submitting contact request: {str(e)}"}
        )
    finally:
        cursor.close()
        return_db_connection(conn)

@app.get("/api/contact-requests", response_model=List[dict])
async def get_contact_requests(
    current_user: User = Depends(get_current_user)
):
    """
    Get all contact requests.
    This endpoint is only accessible to admin users.
    """
    # Check if user is admin
    check_admin_role(current_user)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Get all contact requests
        cursor.execute(
            """
            SELECT id, name, message, created_at, status
            FROM contact_requests
            ORDER BY created_at DESC
            """
        )
        
        contact_requests = []
        for row in cursor.fetchall():
            contact_requests.append({
                "id": row["id"],
                "name": row["name"],
                "message": row["message"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "status": row["status"]
            })
        
        return contact_requests
    except Exception as e:
        logging.error(f"Error getting contact requests: {str(e)}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting contact requests: {str(e)}"
        )
    finally:
        cursor.close()
        return_db_connection(conn)

@app.put("/api/contact-requests/{request_id}", response_model=dict)
async def update_contact_request_status(
    request_id: int,
    status_data: dict = Body(..., example={"status": "resolved"}),
    current_user: User = Depends(get_current_user)
):
    """
    Update the status of a contact request.
    This endpoint is only accessible to admin users.
    """
    # Check if user is admin
    check_admin_role(current_user)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Update the contact request status
        cursor.execute(
            """
            UPDATE contact_requests
            SET status = %s
            WHERE id = %s
            RETURNING id
            """,
            (status_data.get("status"), request_id)
        )
        
        updated = cursor.fetchone()
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contact request with ID {request_id} not found"
            )
        
        conn.commit()
        
        return {"success": True, "message": "Contact request status updated successfully"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        logging.error(f"Error updating contact request status: {str(e)}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating contact request status: {str(e)}"
        )
    finally:
        cursor.close()
        return_db_connection(conn)

# Test Execution endpoints
test_execution_service = TestExecutionService()

@app.get("/api/projects/{project_id}/test-executions")
async def get_project_test_executions(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all test executions for a project.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    try:
        executions = test_execution_service.get_executions_by_project(
            project_id, str(current_user.client_id)
        )
        return {"success": True, "executions": executions}
    except Exception as e:
        logger.error(f"Error retrieving test executions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve test executions: {str(e)}"
        )

@app.post("/api/test-executions")
async def create_test_execution(
    request_data: CreateTestExecutionRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new test execution.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    try:
        execution = test_execution_service.create_execution(
            name=request_data.name,
            description=request_data.description or "",
            project_id=str(request_data.project_id),
            client_id=str(current_user.client_id),
            created_by=current_user.id
        )
        return {"success": True, "execution": execution}
    except Exception as e:
        logger.error(f"Error creating test execution: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create test execution: {str(e)}"
        )

@app.get("/api/test-executions/{execution_id}")
async def get_test_execution(
    execution_id: str,  # Changed to str to handle both int and UUID attempts
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific test execution by ID.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    # Validate and convert execution_id to integer
    try:
        execution_id_int = int(execution_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid execution_id format. Expected integer, got: {execution_id}"
        )
    
    try:
        execution = await test_execution_service.get_execution_by_id(
            execution_id_int, str(current_user.client_id)
        )
        
        if not execution:
            raise HTTPException(
                status_code=404,
                detail="Test execution not found"
            )
        
        return {"success": True, "execution": execution}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving test execution: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve test execution: {str(e)}"
        )

@app.put("/api/test-executions/{execution_id}/status")
async def update_test_execution_status(
    execution_id: int,
    request_data: UpdateTestExecutionStatusRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Update the status of a test execution.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    # Validate status
    valid_statuses = ['New', 'In Progress', 'Done']
    if request_data.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    try:
        success = test_execution_service.update_execution_status(
            execution_id, request_data.status, str(current_user.client_id)
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Test execution not found"
            )
        
        return {"success": True, "message": "Test execution status updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating test execution status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update test execution status: {str(e)}"
        )

@app.delete("/api/test-executions/{execution_id}")
async def delete_test_execution(
    execution_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a test execution (only if it has no test runs).
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    try:
        success = test_execution_service.delete_execution(
            execution_id, str(current_user.client_id)
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Test execution not found"
            )
        
        return {"success": True, "message": "Test execution deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        if "Cannot delete execution with" in str(e):
            raise HTTPException(
                status_code=400,
                detail=str(e)
            )
        logger.error(f"Error deleting test execution: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete test execution: {str(e)}"
        )

@app.get("/api/projects/{project_id}/test-executions/in-progress")
async def get_in_progress_executions(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all test executions with 'In Progress' status for a project.
    Used for the Run Test dropdown.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    try:
        executions = test_execution_service.get_in_progress_executions(
            project_id, str(current_user.client_id)
        )
        return {"success": True, "executions": executions}
    except Exception as e:
        logger.error(f"Error retrieving in-progress executions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve in-progress executions: {str(e)}"
        )

@app.get("/api/test-executions/{execution_id}/test-runs")
async def get_execution_test_runs(
    execution_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get all test runs for a specific execution.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    try:
        result = test_execution_service.get_execution_test_runs(
            execution_id, str(current_user.client_id)
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Error retrieving execution test runs: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve execution test runs: {str(e)}"
        )

@app.post("/api/test-runs/assign-to-execution")
async def assign_test_run_to_execution(
    request_data: AssignTestRunRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Assign a test run to a test execution.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    try:
        success = test_execution_service.assign_test_run_to_execution(
            request_data.test_run_id, request_data.execution_id, str(current_user.client_id)
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Test run or execution not found"
            )
        
        return {"success": True, "message": "Test run assigned to execution successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning test run to execution: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to assign test run to execution: {str(e)}"
        )

# ================================
# User Requests / Bug Reports
# ================================

@app.post("/api/user-requests")
async def create_user_request(
    request_data: CreateUserRequestRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Submit a new bug report or feature request.
    Available to all authenticated users.
    """
    if not current_user.client_id:
        raise HTTPException(
            status_code=400,
            detail="User must be associated with a client"
        )
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Insert the user request
        cursor.execute(
            """
            INSERT INTO user_requests (
                user_id, client_id, title, description, request_type, 
                priority, browser_info, page_url, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'new')
            RETURNING id, created_at
            """,
            (
                current_user.id,
                str(current_user.client_id),
                request_data.title,
                request_data.description,
                request_data.request_type,
                request_data.priority,
                request_data.browser_info,
                request_data.page_url
            )
        )
        
        result = cursor.fetchone()
        new_id = result[0]
        created_at = result[1]
        conn.commit()
        
        logger.info(f"User {current_user.email} created {request_data.request_type} request #{new_id}: {request_data.title}")
        
        return {
            "success": True,
            "id": new_id,
            "message": "Request submitted successfully",
            "created_at": created_at.isoformat() if created_at else None
        }
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating user request: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create request: {str(e)}"
        )
    finally:
        cursor.close()
        return_db_connection(conn)

@app.get("/api/user-requests/my")
async def get_my_user_requests(
    current_user: User = Depends(get_current_user)
):
    """
    Get all requests submitted by the current user.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Get user's requests
        cursor.execute(
            """
            SELECT 
                ur.id, ur.title, ur.description, ur.request_type, 
                ur.status, ur.priority, ur.browser_info, ur.page_url,
                ur.created_at, ur.updated_at, ur.resolved_at, ur.admin_notes,
                u.email as resolved_by_email
            FROM user_requests ur
            LEFT JOIN users u ON ur.resolved_by = u.id
            WHERE ur.user_id = %s
            ORDER BY ur.created_at DESC
            """,
            (current_user.id,)
        )
        
        requests = []
        for row in cursor.fetchall():
            requests.append({
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "request_type": row["request_type"],
                "status": row["status"],
                "priority": row["priority"],
                "browser_info": row["browser_info"],
                "page_url": row["page_url"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
                "resolved_by_email": row["resolved_by_email"],
                "admin_notes": row["admin_notes"]
            })
        
        return requests
    except Exception as e:
        logger.error(f"Error getting user requests: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve requests: {str(e)}"
        )
    finally:
        cursor.close()
        return_db_connection(conn)

@app.get("/api/user-requests/all")
async def get_all_user_requests(
    status_filter: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user)
):
    """
    Get all user requests in the system.
    Admin only endpoint.
    """
    # Check if user is admin
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=403,
            detail="Only administrators can access all requests"
        )
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Build query with optional filters
        query = """
            SELECT 
                ur.id, ur.title, ur.description, ur.request_type, 
                ur.status, ur.priority, ur.browser_info, ur.page_url,
                ur.created_at, ur.updated_at, ur.resolved_at, ur.admin_notes,
                u.email as submitted_by_email,
                u.full_name as submitted_by_name,
                resolver.email as resolved_by_email
            FROM user_requests ur
            JOIN users u ON ur.user_id = u.id
            LEFT JOIN users resolver ON ur.resolved_by = resolver.id
            WHERE 1=1
        """
        params = []
        
        if status_filter:
            query += " AND ur.status = %s"
            params.append(status_filter)
        
        if type_filter:
            query += " AND ur.request_type = %s"
            params.append(type_filter)
        
        query += " ORDER BY ur.created_at DESC"
        
        cursor.execute(query, params)
        
        requests = []
        for row in cursor.fetchall():
            requests.append({
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "request_type": row["request_type"],
                "status": row["status"],
                "priority": row["priority"],
                "browser_info": row["browser_info"],
                "page_url": row["page_url"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
                "submitted_by": row['submitted_by_name'] if row['submitted_by_name'] else row['submitted_by_email'],
                "resolved_by_email": row["resolved_by_email"],
                "admin_notes": row["admin_notes"]
            })
        
        return requests
    except Exception as e:
        logger.error(f"Error getting all user requests: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve all requests: {str(e)}"
        )
    finally:
        cursor.close()
        return_db_connection(conn)

@app.patch("/api/user-requests/{request_id}/status")
async def update_user_request_status(
    request_id: int,
    status_data: UpdateUserRequestStatusRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Update the status of a user request.
    Admin only endpoint.
    """
    # Check if user is admin
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=403,
            detail="Only administrators can update request status"
        )
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Check if request exists
        cursor.execute("SELECT id FROM user_requests WHERE id = %s", (request_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Request not found")
        
        # Build update query dynamically based on provided fields
        update_fields = ["status = %s"]
        params = [status_data.status]
        
        # Set resolved_at and resolved_by if status is resolved or closed
        if status_data.status in ['resolved', 'closed']:
            update_fields.append("resolved_at = CURRENT_TIMESTAMP")
            update_fields.append("resolved_by = %s")
            params.append(current_user.id)
        
        if status_data.admin_notes is not None:
            update_fields.append("admin_notes = %s")
            params.append(status_data.admin_notes)
        
        if status_data.priority is not None:
            update_fields.append("priority = %s")
            params.append(status_data.priority)
        
        params.append(request_id)
        
        query = f"""
            UPDATE user_requests
            SET {', '.join(update_fields)}
            WHERE id = %s
            RETURNING id, status, updated_at
        """
        
        cursor.execute(query, params)
        result = cursor.fetchone()
        conn.commit()
        
        logger.info(f"Admin {current_user.email} updated request #{request_id} status to {status_data.status}")
        
        return {
            "success": True,
            "id": result["id"],
            "status": result["status"],
            "updated_at": result["updated_at"].isoformat() if result["updated_at"] else None,
            "message": "Request status updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating user request status: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update request status: {str(e)}"
        )
    finally:
        cursor.close()
        return_db_connection(conn)

@app.get("/api/system/pool-status")
async def get_pool_status_endpoint():
    """
    Get current database connection pool status for monitoring.
    """
    try:
        status = get_pool_status()
        return status
    except Exception as e:
        logger.error(f"Error getting pool status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pool status: {str(e)}"
        )

# ==================== PHASE 1: MONITORING ENDPOINTS ====================

def check_admin_access(current_user: User = Depends(get_current_user)) -> User:
    """
    Verify that the current user is an admin.
    Only admin users can access monitoring endpoints.
    """
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can access monitoring endpoints"
        )
    return current_user

# Initialize monitoring service
monitoring_service = AgentMonitoring()
generation_cost_analytics = GenerationCostAnalytics()

@app.get("/api/monitoring/health")
async def get_health_status(admin_user: User = Depends(check_admin_access)):
    """
    Get health status of all Phase 1 services.
    
    **Admin only endpoint**
    
    Returns:
    - overall_status: 'healthy', 'warning', or 'error'
    - tables: Status of each database table
    - recent_activity: Activity in the last hour
    """
    try:
        health = monitoring_service.get_health_status()
        return {
            'status': 'success',
            'data': health,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting health status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/metrics")
async def get_all_metrics(
    hours: int = Query(24, ge=1, le=720),
    admin_user: User = Depends(check_admin_access)
):
    """
    Get all Phase 1 metrics combined.
    
    **Admin only endpoint**
    
    Query Parameters:
    - hours: Number of hours to look back (1-720, default 24)
    
    Returns:
    - validation: Validation metrics
    - confidence: Confidence scoring metrics
    - feedback: Execution feedback metrics
    - retry: Retry attempt metrics
    """
    try:
        metrics = monitoring_service.get_all_metrics(hours=hours)
        return {
            'status': 'success',
            'data': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/validation")
async def get_validation_metrics(
    hours: int = Query(24, ge=1, le=720),
    admin_user: User = Depends(check_admin_access)
):
    """
    Get validation metrics.
    
    **Admin only endpoint**
    
    Query Parameters:
    - hours: Number of hours to look back (1-720, default 24)
    
    Returns:
    - total_validations: Total number of validations
    - valid_steps: Number of valid steps
    - invalid_steps: Number of invalid steps
    - success_rate: Percentage of valid steps
    - avg_confidence: Average validation confidence
    - error_distribution: Distribution of error types
    """
    try:
        metrics = monitoring_service.get_validation_metrics(hours=hours)
        return {
            'status': 'success',
            'data': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting validation metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/confidence")
async def get_confidence_metrics(
    hours: int = Query(24, ge=1, le=720),
    admin_user: User = Depends(check_admin_access)
):
    """
    Get confidence scoring metrics.
    
    **Admin only endpoint**
    
    Query Parameters:
    - hours: Number of hours to look back (1-720, default 24)
    
    Returns:
    - total_scored: Total steps scored
    - avg_confidence: Average confidence score
    - low_risk_steps: Number of low risk steps
    - medium_risk_steps: Number of medium risk steps
    - high_risk_steps: Number of high risk steps
    - factor_averages: Average scores for selector, action, data, pattern
    """
    try:
        metrics = monitoring_service.get_confidence_metrics(hours=hours)
        return {
            'status': 'success',
            'data': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting confidence metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/feedback")
async def get_feedback_metrics(
    hours: int = Query(24, ge=1, le=720),
    admin_user: User = Depends(check_admin_access)
):
    """
    Get execution feedback metrics.
    
    **Admin only endpoint**
    
    Query Parameters:
    - hours: Number of hours to look back (1-720, default 24)
    
    Returns:
    - total_failures: Total number of failures
    - unique_error_types: Number of unique error types
    - error_categories: Distribution of error categories
    - most_common_errors: Top 5 most common errors
    """
    try:
        metrics = monitoring_service.get_feedback_metrics(hours=hours)
        return {
            'status': 'success',
            'data': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting feedback metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/retry")
async def get_retry_metrics(
    hours: int = Query(24, ge=1, le=720),
    admin_user: User = Depends(check_admin_access)
):
    """
    Get retry attempt metrics.
    
    **Admin only endpoint**
    
    Query Parameters:
    - hours: Number of hours to look back (1-720, default 24)
    
    Returns:
    - total_retry_attempts: Total retry attempts
    - successful_retries: Number of successful retries
    - failed_retries: Number of failed retries
    - retry_success_rate: Percentage of successful retries
    - avg_attempts_per_step: Average number of attempts
    """
    try:
        metrics = monitoring_service.get_retry_metrics(hours=hours)
        return {
            'status': 'success',
            'data': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting retry metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring/alerts")
async def get_alerts(admin_user: User = Depends(check_admin_access)):
    """
    Check for alert conditions based on metrics.
    
    **Admin only endpoint**
    
    Returns:
    - alert_count: Number of active alerts
    - alerts: List of alerts with severity and message
    """
    try:
        alerts = monitoring_service.check_alerts()
        return {
            'status': 'success',
            'data': alerts,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error checking alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/generation-costs")
async def get_generation_costs(
    period: str = Query('day', regex='^(day|week|month|year|all)$'),
    current_user: User = Depends(check_admin_access)
):
    """
    Get generation job cost statistics.
    
    **Admin only endpoint**
    
    Query Parameters:
    - period: Time period to analyze ('day', 'week', 'month', 'year', 'all')
    
    Returns comprehensive statistics:
    - mean: Average cost per job
    - median / percentile_50: 50th percentile cost
    - percentile_90: 90th percentile cost
    - percentile_95: 95th percentile cost
    - percentile_99: 99th percentile cost
    - min: Minimum cost
    - max: Maximum cost
    - std_dev: Standard deviation
    - total_sum: Total cost for period
    - count: Number of jobs
    - jobs: List of individual job costs (up to 100 most recent)
    """
    try:
        client_id = current_user.client_id if current_user.role != 'admin' else None
        
        result = generation_cost_analytics.get_generation_costs(
            client_id=client_id,
            period=period
        )
        
        return {
            'status': 'success',
            'data': result,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting generation costs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/generation-costs/trends")
async def get_generation_cost_trends(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(check_admin_access)
):
    """
    Get daily generation cost trends.
    
    **Admin only endpoint**
    
    Query Parameters:
    - days: Number of days to analyze (1-365, default 30)
    
    Returns daily statistics:
    - date: Date
    - jobs_count: Number of generation jobs on that day
    - daily_cost: Total cost for that day
    - avg_cost_per_request: Average cost per individual AI request
    """
    try:
        client_id = current_user.client_id if current_user.role != 'admin' else None
        
        trends = generation_cost_analytics.get_cost_trends(
            client_id=client_id,
            days=days
        )
        
        return {
            'status': 'success',
            'data': trends,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting generation cost trends: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Phase 4 Pydantic Models ====================

class CacheEmbeddingRequest(BaseModel):
    """Request model for caching embeddings"""
    content_hash: str
    embedding: List[float]
    metadata: Optional[Dict] = None

class BatchProcessRequest(BaseModel):
    """Request model for batch processing"""
    items: List[Dict]
    batch_size: Optional[int] = 32

class OptimizationRecommendationRequest(BaseModel):
    """Request model for getting optimization recommendations"""
    analysis_type: str  # 'cache', 'query', 'index', 'all'

class FineTuningJobRequest(BaseModel):
    """Request model for submitting fine-tuning jobs"""
    model_id: str
    training_data: List[Dict]
    hyperparameters: Optional[Dict] = None
    job_name: Optional[str] = None

class ModelDeploymentRequest(BaseModel):
    """Request model for deploying models"""
    model_id: str
    environment: str  # 'staging', 'production'
    version: Optional[str] = None

class FailureAnalysisRequest(BaseModel):
    """Request model for failure analysis"""
    days_back: Optional[int] = 7
    include_recovery: Optional[bool] = True

class PromptImprovementRequest(BaseModel):
    """Request model for prompt improvement"""
    analysis_type: str  # 'weekly', 'monthly'
    focus_areas: Optional[List[str]] = None

class ABTestRequest(BaseModel):
    """Request model for running A/B tests"""
    test_case_id_a: int
    test_case_id_b: int
    variant_a_id: str
    variant_b_id: str
    project_id: Optional[UUID4] = None
    notes: Optional[str] = None
    sample_size: Optional[int] = 10  # Number of times to run each variant

# ==================== Phase 4 API Endpoints ====================

# ==================== Performance Optimizer Endpoints ====================

@app.post("/api/phase4/performance/cache-embedding")
async def cache_embedding(
    request: CacheEmbeddingRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Cache an embedding in the database.
    
    **Admin only endpoint**
    
    Request Body:
    - content_hash: Hash of the content
    - embedding: Vector embedding (list of floats)
    - metadata: Optional metadata dictionary
    
    Returns:
    - success: Boolean indicating if caching succeeded
    - cache_key: The key used to store the embedding
    """
    try:
        optimizer = PerformanceOptimizer()
        success = optimizer.cache_embedding(
            request.content_hash,
            request.embedding,
            request.metadata
        )
        
        return {
            'status': 'success' if success else 'failed',
            'success': success,
            'cache_key': request.content_hash,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error caching embedding: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/performance/cache-stats")
async def get_cache_stats(current_user: User = Depends(check_admin_access)):
    """
    Get cache statistics and performance metrics.
    
    **Admin only endpoint**
    
    Returns:
    - total_cached: Total number of cached items
    - cache_hit_rate: Percentage of cache hits
    - avg_access_time: Average access time in ms
    - memory_usage: Estimated memory usage
    """
    try:
        optimizer = PerformanceOptimizer()
        stats = optimizer.get_cache_statistics()
        
        return {
            'status': 'success',
            'data': stats,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/phase4/performance/batch-process")
async def batch_process(
    request: BatchProcessRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Process items in batches for optimization.
    
    **Admin only endpoint**
    
    Request Body:
    - items: List of items to process
    - batch_size: Size of each batch (default 32)
    
    Returns:
    - processed_count: Number of items processed
    - batch_count: Number of batches created
    - processing_time: Total processing time in seconds
    """
    try:
        optimizer = PerformanceOptimizer()
        result = optimizer.batch_process(request.items, request.batch_size or 32)
        
        return {
            'status': 'success',
            'data': result,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/performance/query-logs")
async def get_query_logs(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(check_admin_access)
):
    """
    Get query performance logs.
    
    **Admin only endpoint**
    
    Query Parameters:
    - limit: Maximum number of logs to return (1-1000, default 100)
    
    Returns:
    - logs: List of query performance logs
    - slow_queries: Number of slow queries detected
    - avg_query_time: Average query execution time
    """
    try:
        optimizer = PerformanceOptimizer()
        logs = optimizer.get_slow_queries(limit=limit)
        
        return {
            'status': 'success',
            'data': logs,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting query logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/performance/optimization-recommendations")
async def get_optimization_recommendations(
    analysis_type: str = Query("all", pattern="^(cache|query|index|all)$"),
    current_user: User = Depends(check_admin_access)
):
    """
    Get optimization recommendations based on system analysis.
    
    **Admin only endpoint**
    
    Query Parameters:
    - analysis_type: Type of analysis (cache, query, index, all)
    
    Returns:
    - recommendations: List of optimization recommendations
    - priority: Priority level of each recommendation
    - estimated_improvement: Estimated performance improvement percentage
    """
    try:
        optimizer = PerformanceOptimizer()
        recommendations = optimizer.generate_optimization_recommendations()
        
        return {
            'status': 'success',
            'data': recommendations,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/performance/index-analysis")
async def get_index_analysis(current_user: User = Depends(check_admin_access)):
    """
    Analyze database indexes for optimization opportunities.
    
    **Admin only endpoint**
    
    Returns:
    - used_indexes: List of actively used indexes
    - unused_indexes: List of unused indexes that could be removed
    - missing_indexes: Suggested indexes for frequently queried columns
    """
    try:
        optimizer = PerformanceOptimizer()
        analysis = optimizer.analyze_index_usage()
        
        return {
            'status': 'success',
            'data': analysis,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error analyzing indexes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Fine-Tuning Service Endpoints ====================

@app.get("/api/phase4/finetuning/collect-successful-tests")
async def collect_successful_tests(
    min_success_rate: float = Query(0.95, ge=0.0, le=1.0),
    limit: int = Query(1000, ge=1, le=10000),
    current_user: User = Depends(check_admin_access)
):
    """
    Collect successful test cases for fine-tuning.
    
    **Admin only endpoint**
    
    Query Parameters:
    - min_success_rate: Minimum success rate threshold (0.0-1.0, default 0.95)
    - limit: Maximum number of tests to collect (1-10000, default 1000)
    
    Returns:
    - collected_count: Number of tests collected
    - tests: List of successful test cases with metadata
    - avg_success_rate: Average success rate of collected tests
    """
    try:
        collector = FineTuningDataCollector()
        tests = collector.collect_successful_tests(min_success_rate, limit)
        
        return {
            'status': 'success',
            'collected_count': len(tests),
            'data': tests,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error collecting successful tests: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/phase4/finetuning/submit-job")
async def submit_finetuning_job(
    request: FineTuningJobRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Submit a fine-tuning job for model training.
    
    **Admin only endpoint**
    
    Request Body:
    - model_id: ID of the model to fine-tune
    - training_data: List of training examples
    - hyperparameters: Optional hyperparameters (epochs, learning_rate, batch_size)
    - job_name: Optional name for the job
    
    Returns:
    - job_id: Unique ID of the submitted job
    - status: Current job status
    - estimated_duration: Estimated time to completion in seconds
    """
    try:
        service = FineTuningService()
        job_id = service.submit_finetuning_job(
            request.model_id,
            request.training_data,
            request.hyperparameters,
            request.job_name
        )
        
        return {
            'status': 'success',
            'job_id': job_id,
            'job_status': 'submitted',
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error submitting fine-tuning job: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/finetuning/job-status/{job_id}")
async def get_finetuning_job_status(
    job_id: str,
    current_user: User = Depends(check_admin_access)
):
    """
    Get the status of a fine-tuning job.
    
    **Admin only endpoint**
    
    Path Parameters:
    - job_id: ID of the fine-tuning job
    
    Returns:
    - job_id: Job ID
    - status: Current status (submitted, processing, completed, failed)
    - progress: Progress percentage (0-100)
    - error_message: Error message if job failed
    """
    try:
        service = FineTuningService()
        status = service.get_job_status(job_id)
        
        return {
            'status': 'success',
            'data': status,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/phase4/finetuning/deploy-model")
async def deploy_finetuned_model(
    request: ModelDeploymentRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Deploy a fine-tuned model to an environment.
    
    **Admin only endpoint**
    
    Request Body:
    - model_id: ID of the fine-tuned model
    - environment: Target environment (staging, production)
    - version: Optional version tag
    
    Returns:
    - deployment_id: Unique ID of the deployment
    - status: Deployment status
    - deployed_at: Timestamp of deployment
    """
    try:
        service = FineTuningService()
        deployment_id = service.deploy_model(
            request.model_id,
            request.environment,
            request.version
        )
        
        return {
            'status': 'success',
            'deployment_id': deployment_id,
            'environment': request.environment,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error deploying model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/finetuning/job-history")
async def get_finetuning_job_history(
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(check_admin_access)
):
    """
    Get history of fine-tuning jobs.
    
    **Admin only endpoint**
    
    Query Parameters:
    - limit: Maximum number of jobs to return (1-500, default 50)
    
    Returns:
    - jobs: List of fine-tuning jobs with status and results
    - total_jobs: Total number of jobs in history
    """
    try:
        service = FineTuningService()
        jobs = service.get_job_history(limit)
        
        return {
            'status': 'success',
            'total_jobs': len(jobs),
            'data': jobs,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting job history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/phase4/finetuning/evaluate-model")
async def evaluate_finetuned_model(
    model_id: str = Query(...),
    test_data: List[Dict] = Body(...),
    current_user: User = Depends(check_admin_access)
):
    """
    Evaluate a fine-tuned model on test data.
    
    **Admin only endpoint**
    
    Query Parameters:
    - model_id: ID of the model to evaluate
    
    Request Body:
    - test_data: List of test examples
    
    Returns:
    - accuracy: Model accuracy on test data
    - precision: Precision metric
    - recall: Recall metric
    - f1_score: F1 score
    """
    try:
        service = FineTuningService()
        metrics = service.evaluate_model(model_id, test_data)
        
        return {
            'status': 'success',
            'model_id': model_id,
            'metrics': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error evaluating model: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== Continuous Improvement Endpoints ====================

@app.post("/api/phase4/improvement/analyze-failures")
async def analyze_failures(
    request: FailureAnalysisRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Analyze test failures to identify patterns and improvement opportunities.
    
    **Admin only endpoint**
    
    Request Body:
    - days_back: Number of days to analyze (default 7)
    - include_recovery: Include recovery attempt analysis (default true)
    
    Returns:
    - total_failures: Total number of failures analyzed
    - failure_categories: Failures grouped by type
    - top_errors: Most common error types
    - recovery_success_rate: Percentage of successful recoveries
    """
    try:
        service = ContinuousImprovement()
        start_date = datetime.utcnow() - timedelta(days=request.days_back or 7)
        end_date = datetime.utcnow()
        
        failures = service.analyze_failures(start_date, end_date)
        
        return {
            'status': 'success',
            'total_failures': len(failures),
            'data': failures,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error analyzing failures: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/phase4/improvement/generate-weekly-report")
async def generate_weekly_report(current_user: User = Depends(check_admin_access)):
    """
    Generate a comprehensive weekly improvement report.
    
    **Admin only endpoint**
    
    Returns:
    - report_id: Unique ID of the generated report
    - period: Week covered by the report
    - key_metrics: Summary of key metrics
    - recommendations: List of improvement recommendations
    - generated_at: Timestamp of report generation
    """
    try:
        service = ContinuousImprovement()
        report = service.generate_weekly_report()
        
        return {
            'status': 'success',
            'report_id': str(uuid.uuid4()),
            'data': report,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error generating weekly report: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/phase4/improvement/generate-monthly-report")
async def generate_monthly_report(current_user: User = Depends(check_admin_access)):
    """
    Generate a comprehensive monthly improvement report.
    
    **Admin only endpoint**
    
    Returns:
    - report_id: Unique ID of the generated report
    - period: Month covered by the report
    - key_metrics: Summary of key metrics
    - trend_analysis: Analysis of trends over the month
    - strategic_recommendations: Strategic improvement recommendations
    - generated_at: Timestamp of report generation
    """
    try:
        service = ContinuousImprovement()
        report = service.generate_monthly_report()
        
        return {
            'status': 'success',
            'report_id': str(uuid.uuid4()),
            'data': report,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error generating monthly report: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/phase4/improvement/improve-prompts")
async def improve_prompts(
    request: PromptImprovementRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Generate prompt improvement suggestions based on analysis.
    
    **Admin only endpoint**
    
    Request Body:
    - analysis_type: Type of analysis (weekly, monthly)
    - focus_areas: Optional list of areas to focus on
    
    Returns:
    - improvements: List of suggested prompt improvements
    - impact_estimate: Estimated impact on performance
    - implementation_priority: Priority order for implementation
    """
    try:
        service = ContinuousImprovement()
        improvements = service.improve_prompts(
            request.analysis_type,
            request.focus_areas
        )
        
        return {
            'status': 'success',
            'data': improvements,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error improving prompts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/phase4/improvement/run-ab-test")
async def run_ab_test(
    request: ABTestRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Run an A/B test comparing two test case variants.
    
    **Admin only endpoint**
    
    Request Body:
    - test_case_id_a: ID of first test case variant
    - test_case_id_b: ID of second test case variant
    - variant_a_id: Identifier for variant A
    - variant_b_id: Identifier for variant B
    - project_id: Optional project ID
    - notes: Optional notes about the test
    - sample_size: Number of times to run each variant (default 10)
    
    Returns:
    - test_id: ID of the A/B test record
    - status: Test status (active)
    - message: Confirmation message
    """
    try:
        with get_db_connection_context() as conn:
            with conn.cursor() as cur:
                # Get current user's client_id
                cur.execute("SELECT client_id FROM users WHERE id = %s", (current_user.id,))
                user_row = cur.fetchone()
                if not user_row:
                    raise HTTPException(status_code=401, detail="User not found")
                
                client_id = user_row[0]
                
                # Insert A/B test record
                cur.execute("""
                    INSERT INTO ab_test_results 
                    (client_id, project_id, test_case_id_a, test_case_id_b, 
                     variant_a_id, variant_b_id, status, notes, 
                     sample_size_a, sample_size_b)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    client_id, request.project_id, request.test_case_id_a, request.test_case_id_b,
                    request.variant_a_id, request.variant_b_id, 'active', request.notes,
                    request.sample_size, request.sample_size
                ))
                
                test_id = cur.fetchone()[0]
                conn.commit()
                
                logger.info(f"Created A/B test {test_id}: variant {request.variant_a_id} vs {request.variant_b_id}")
                
                return {
                    'status': 'success',
                    'test_id': test_id,
                    'variant_a': request.variant_a_id,
                    'variant_b': request.variant_b_id,
                    'message': f'A/B test created successfully. Test ID: {test_id}',
                    'timestamp': datetime.utcnow().isoformat()
                }
    except Exception as e:
        logger.error(f"Error running A/B test: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/improvement/confidence-calibration")
async def get_confidence_calibration(
    current_user: User = Depends(check_admin_access)
):
    """
    Get confidence score calibration analysis.
    
    **Admin only endpoint**
    
    Returns:
    - calibration_score: Overall calibration quality (0-100)
    - overconfident_areas: Areas where confidence is too high
    - underconfident_areas: Areas where confidence is too low
    - recommendations: Calibration improvement recommendations
    """
    try:
        service = ContinuousImprovement()
        calibration = service.analyze_confidence_calibration()
        
        return {
            'status': 'success',
            'data': calibration,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting confidence calibration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/improvement/tool-usage-analysis")
async def get_tool_usage_analysis(
    current_user: User = Depends(check_admin_access)
):
    """
    Analyze tool usage patterns and effectiveness.
    
    **Admin only endpoint**
    
    Returns:
    - tools: List of tools with usage statistics
    - most_used: Most frequently used tools
    - most_effective: Tools with highest success rate
    - recommendations: Tool usage optimization recommendations
    """
    try:
        service = ContinuousImprovement()
        analysis = service.analyze_tool_usage()
        
        return {
            'status': 'success',
            'data': analysis,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error analyzing tool usage: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/improvement/ab-test-analysis")
async def get_ab_test_analysis(
    current_user: User = Depends(check_admin_access)
):
    """
    Analyze A/B test results and determine winners.
    
    **Admin only endpoint**
    
    Returns:
    - active_tests: List of active A/B tests
    - completed_tests: List of completed tests with results
    - winners: Identified winning variants
    - statistical_significance: Confidence levels for each test
    """
    try:
        service = ContinuousImprovement()
        analysis = service.analyze_ab_test_results()
        
        return {
            'status': 'success',
            'data': analysis,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error analyzing A/B tests: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/improvement/ensemble-performance")
async def get_ensemble_performance(
    current_user: User = Depends(check_admin_access)
):
    """
    Analyze model ensemble performance and contribution.
    
    **Admin only endpoint**
    
    Returns:
    - ensemble_accuracy: Overall ensemble accuracy
    - model_contributions: Contribution of each model to ensemble
    - consensus_quality: Quality of model consensus
    - improvement_opportunities: Ways to improve ensemble performance
    """
    try:
        service = ContinuousImprovement()
        analysis = service.analyze_ensemble_performance()
        
        return {
            'status': 'success',
            'data': analysis,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error analyzing ensemble performance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/improvement/error-categories")
async def get_error_categories(
    current_user: User = Depends(check_admin_access)
):
    """
    Get analysis of error categories and patterns.
    
    **Admin only endpoint**
    
    Returns:
    - error_categories: List of error categories with frequency
    - root_causes: Identified root causes for each category
    - recovery_strategies: Recommended recovery strategies
    - prevention_recommendations: Ways to prevent errors
    """
    try:
        service = ContinuousImprovement()
        analysis = service.get_error_categories()
        
        return {
            'status': 'success',
            'data': analysis,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error analyzing error categories: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/improvement/planning-accuracy")
async def get_planning_accuracy(
    current_user: User = Depends(check_admin_access)
):
    """
    Analyze test case planning accuracy and effectiveness.
    
    **Admin only endpoint**
    
    Returns:
    - planning_accuracy: Overall accuracy of test planning
    - coverage_analysis: Test coverage metrics
    - gap_analysis: Identified gaps in test coverage
    - improvement_recommendations: Ways to improve planning
    """
    try:
        service = ContinuousImprovement()
        analysis = service.analyze_planning_accuracy()
        
        return {
            'status': 'success',
            'data': analysis,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error analyzing planning accuracy: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/phase4/monitoring/trends")
async def get_trends(
    hours: int = Query(24, ge=1, le=720),
    interval_minutes: int = Query(60, ge=5, le=1440),
    admin_user: User = Depends(check_admin_access)
):
    """
    Get metric trends over time.
    
    **Admin only endpoint**
    
    Query Parameters:
    - hours: Number of hours to look back (1-720, default 24)
    - interval_minutes: Interval for data points (5-1440, default 60)
    
    Returns:
    - validation_trend: Validation metrics over time
    - confidence_trend: Confidence metrics over time
    - failure_trend: Failure metrics over time
    """
    try:
        trends = monitoring_service.get_trends(hours=hours, interval_minutes=interval_minutes)
        return {
            'status': 'success',
            'data': trends,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting trends: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== API Aliases (without phase numbers) ====================
# These endpoints provide simpler naming without phase numbers

@app.post("/api/performance/cache-embedding")
async def cache_embedding_alias(
    request: CacheEmbeddingRequest,
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/performance/cache-embedding"""
    return await cache_embedding(request, current_user)

@app.get("/api/performance/cache-stats")
async def get_cache_stats_alias(current_user: User = Depends(check_admin_access)):
    """Alias for /api/phase4/performance/cache-stats"""
    return await get_cache_stats(current_user)

@app.post("/api/performance/batch-process")
async def batch_process_alias(
    request: BatchProcessRequest,
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/performance/batch-process"""
    return await batch_process(request, current_user)

@app.get("/api/performance/query-logs")
async def get_query_logs_alias(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/performance/query-logs"""
    return await get_query_logs(limit, current_user)

@app.get("/api/performance/optimization-recommendations")
async def get_optimization_recommendations_alias(
    analysis_type: str = Query("all", pattern="^(cache|query|index|all)$"),
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/performance/optimization-recommendations"""
    return await get_optimization_recommendations(analysis_type, current_user)

@app.get("/api/performance/index-analysis")
async def get_index_analysis_alias(current_user: User = Depends(check_admin_access)):
    """Alias for /api/phase4/performance/index-analysis"""
    return await get_index_analysis(current_user)

@app.get("/api/finetuning/collect-successful-tests")
async def collect_successful_tests_alias(
    min_success_rate: float = Query(0.95, ge=0.0, le=1.0),
    limit: int = Query(1000, ge=1, le=10000),
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/finetuning/collect-successful-tests"""
    return await collect_successful_tests(min_success_rate, limit, current_user)

@app.post("/api/finetuning/submit-job")
async def submit_finetuning_job_alias(
    request: FineTuningJobRequest,
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/finetuning/submit-job"""
    return await submit_finetuning_job(request, current_user)

@app.get("/api/finetuning/job-status/{job_id}")
async def get_finetuning_job_status_alias(
    job_id: str,
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/finetuning/job-status/{job_id}"""
    return await get_finetuning_job_status(job_id, current_user)

@app.post("/api/finetuning/deploy-model")
async def deploy_finetuned_model_alias(
    request: ModelDeploymentRequest,
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/finetuning/deploy-model"""
    return await deploy_finetuned_model(request, current_user)

@app.get("/api/finetuning/job-history")
async def get_finetuning_job_history_alias(
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/finetuning/job-history"""
    return await get_finetuning_job_history(limit, current_user)

@app.post("/api/finetuning/evaluate-model")
async def evaluate_finetuned_model_alias(
    model_id: str = Query(...),
    test_data: List[Dict] = Body(...),
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/finetuning/evaluate-model"""
    return await evaluate_finetuned_model(model_id, test_data, current_user)

@app.post("/api/improvement/analyze-failures")
async def analyze_failures_alias(
    request: FailureAnalysisRequest,
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/analyze-failures"""
    return await analyze_failures(request, current_user)

@app.post("/api/improvement/generate-weekly-report")
async def generate_weekly_report_alias(current_user: User = Depends(check_admin_access)):
    """Alias for /api/phase4/improvement/generate-weekly-report"""
    return await generate_weekly_report(current_user)

@app.post("/api/improvement/generate-monthly-report")
async def generate_monthly_report_alias(current_user: User = Depends(check_admin_access)):
    """Alias for /api/phase4/improvement/generate-monthly-report"""
    return await generate_monthly_report(current_user)

@app.post("/api/improvement/improve-prompts")
async def improve_prompts_alias(
    request: PromptImprovementRequest,
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/improve-prompts"""
    return await improve_prompts(request, current_user)

@app.post("/api/improvement/run-ab-test")
async def run_ab_test_alias(
    request: ABTestRequest,
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/run-ab-test"""
    return await run_ab_test(request, current_user)


# ================================
# A/B Test Result Tracking
# ================================

class LinkTestRunRequest(BaseModel):
    """Request model for linking test run to A/B test"""
    test_run_id: int
    ab_test_id: int
    variant: str  # 'A' or 'B'


class BatchLinkTestRunsRequest(BaseModel):
    """Request model for batch linking test runs to A/B test"""
    ab_test_id: int
    variant_a_run_ids: List[int] = []
    variant_b_run_ids: List[int] = []


@app.post("/api/phase4/improvement/link-test-run-to-ab-test")
async def link_test_run_to_ab_test(
    request: LinkTestRunRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Link a test run to an A/B test and mark which variant it belongs to.
    This is called after a test run completes to track results for A/B testing.
    
    Request Body:
    - test_run_id: ID of the completed test run
    - ab_test_id: ID of the A/B test
    - variant: 'A' or 'B' to indicate which variant was executed
    
    Returns:
    - success: True if linked successfully
    - message: Confirmation message
    """
    try:
        from auroqa.Services.ABTestResultTracker import ABTestResultTracker
        
        tracker = ABTestResultTracker()
        
        # Link the test run to the A/B test
        success = tracker.link_test_run_to_ab_test(
            request.test_run_id,
            request.ab_test_id,
            request.variant
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to link test run to A/B test")
        
        # Update A/B test results
        tracker.update_ab_test_results(request.ab_test_id)
        
        # Get updated status
        status = tracker.get_ab_test_status(request.ab_test_id)
        
        logger.info(f"Linked test run {request.test_run_id} to A/B test {request.ab_test_id} (variant {request.variant})")
        
        return {
            'status': 'success',
            'message': f'Test run linked to A/B test (variant {request.variant})',
            'ab_test_status': status
        }
    except Exception as e:
        logger.error(f"Error linking test run to A/B test: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/phase4/improvement/batch-link-test-runs")
async def batch_link_test_runs(
    request: BatchLinkTestRunsRequest,
    current_user: User = Depends(check_admin_access)
):
    """
    Link multiple test runs to an A/B test in batch.
    This is useful for linking many test runs at once after running tests.
    
    Request Body:
    - ab_test_id: ID of the A/B test
    - variant_a_run_ids: List of test run IDs for variant A
    - variant_b_run_ids: List of test run IDs for variant B
    
    Returns:
    - total_linked: Total number of runs linked
    - variant_a_linked: Number of variant A runs linked
    - variant_b_linked: Number of variant B runs linked
    - errors: List of any errors encountered
    - ab_test_status: Updated A/B test status
    """
    try:
        from auroqa.Services.ABTestResultTracker import ABTestResultTracker
        
        tracker = ABTestResultTracker()
        
        # Batch link the test runs
        link_results = tracker.batch_link_test_runs(
            request.ab_test_id,
            request.variant_a_run_ids,
            request.variant_b_run_ids
        )
        
        if link_results['total_linked'] == 0:
            raise HTTPException(status_code=400, detail="No test runs were linked")
        
        # Update A/B test results
        tracker.update_ab_test_results(request.ab_test_id)
        
        # Get updated status
        status = tracker.get_ab_test_status(request.ab_test_id)
        
        logger.info(f"Batch linked {link_results['total_linked']} test runs to A/B test {request.ab_test_id}")
        
        return {
            'status': 'success',
            'message': f'Linked {link_results["total_linked"]} test runs to A/B test',
            'linked': link_results,
            'ab_test_status': status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch linking test runs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/phase4/improvement/ab-test/{ab_test_id}/status")
async def get_ab_test_status(
    ab_test_id: int,
    current_user: User = Depends(check_admin_access)
):
    """
    Get current status of an A/B test including progress and results.
    
    Returns:
    - ab_test_id: ID of the A/B test
    - variant_a_id, variant_b_id: Variant identifiers
    - sample_size_a, sample_size_b: Target sample sizes
    - status: 'active' or 'completed'
    - results: Current results including success rates and winner
    """
    try:
        from auroqa.Services.ABTestResultTracker import ABTestResultTracker
        
        tracker = ABTestResultTracker()
        status = tracker.get_ab_test_status(ab_test_id)
        
        if not status:
            raise HTTPException(status_code=404, detail=f"A/B test {ab_test_id} not found")
        
        return {
            'status': 'success',
            'data': status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting A/B test status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/phase4/improvement/ab-tests/progress")
async def get_all_ab_tests_progress(
    limit: int = 50,
    current_user: User = Depends(check_admin_access)
):
    """
    Get all A/B tests with their current progress and results.
    
    Query Parameters:
    - limit: Maximum number of tests to return (default 50)
    
    Returns:
    - List of A/B tests with progress information
    """
    try:
        from auroqa.Services.ABTestResultTracker import ABTestResultTracker
        
        tracker = ABTestResultTracker()
        ab_tests = tracker.get_all_ab_tests_with_progress(limit)
        
        return {
            'status': 'success',
            'total': len(ab_tests),
            'data': ab_tests
        }
    except Exception as e:
        logger.error(f"Error getting A/B tests progress: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/phase4/improvement/available-test-runs/{test_case_id}")
async def get_available_test_runs(
    test_case_id: int,
    limit: int = 100,
    current_user: User = Depends(check_admin_access)
):
    """
    Get available test runs for a test case that haven't been linked to an A/B test.
    This helps you select which runs to link in batch linking.
    
    Path Parameters:
    - test_case_id: ID of the test case
    
    Query Parameters:
    - limit: Maximum number of runs to return (default 100)
    
    Returns:
    - List of available test runs with their results
    """
    try:
        from auroqa.Services.ABTestResultTracker import ABTestResultTracker
        
        tracker = ABTestResultTracker()
        runs = tracker.get_available_test_runs(test_case_id, limit)
        
        return {
            'status': 'success',
            'total': len(runs),
            'test_case_id': test_case_id,
            'data': runs
        }
    except Exception as e:
        logger.error(f"Error getting available test runs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/improvement/confidence-calibration")
async def get_confidence_calibration_alias(
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/confidence-calibration"""
    return await get_confidence_calibration(current_user)

@app.get("/api/improvement/tool-usage-analysis")
async def get_tool_usage_analysis_alias(
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/tool-usage-analysis"""
    return await get_tool_usage_analysis(current_user)

@app.get("/api/improvement/ab-test-analysis")
async def get_ab_test_analysis_alias(
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/ab-test-analysis"""
    return await get_ab_test_analysis(current_user)

@app.get("/api/improvement/ensemble-performance")
async def get_ensemble_performance_alias(
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/ensemble-performance"""
    return await get_ensemble_performance(current_user)

@app.get("/api/improvement/error-categories")
async def get_error_categories_alias(
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/error-categories"""
    return await get_error_categories(current_user)

@app.get("/api/improvement/planning-accuracy")
async def get_planning_accuracy_alias(
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/improvement/planning-accuracy"""
    return await get_planning_accuracy(current_user)

@app.get("/api/monitoring/trends")
async def get_trends_alias(
    hours: int = Query(24, ge=1, le=720),
    interval_minutes: int = Query(60, ge=5, le=1440),
    current_user: User = Depends(check_admin_access)
):
    """Alias for /api/phase4/monitoring/trends"""
    return await get_trends(hours, interval_minutes, current_user)

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Production vs Development configuration
    is_production = os.getenv("ENVIRONMENT", "development") == "production"
    
    if is_production:
        # Production configuration for Docker
        logger.info("🚀 Starting in PRODUCTION mode")
        uvicorn.run(
            "main:app",
            host="0.0.0.0",  # Bind to all interfaces in Docker
            port=9000,
            workers=1,  # Keep single worker in Docker for now
            timeout_keep_alive=60,
            timeout_graceful_shutdown=30,  # Give time for cleanup
            access_log=False,  # Disabled - using custom middleware for error-only logging
            log_level="info",
            reload=False,
            server_header=False,
            date_header=False
        )
    else:
        # Development configuration
        logger.info("🛠️ Starting in DEVELOPMENT mode")
        uvicorn.run(
            "main:app",
            host="127.0.0.1",
            port=9000,
            workers=1,
            timeout_keep_alive=30,
            timeout_graceful_shutdown=15,
            access_log=False,  # Disabled - using custom middleware for error-only logging
            log_level="debug",
            reload=False
        )

# ==================== Planning & Reasoning Visualization Endpoints ====================

@app.get("/api/test-cases/{id}/planning")
async def get_planning_data(
    id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get planning and reasoning data for a test case.
    
    This endpoint returns comprehensive planning, reasoning, and error recovery data
    collected during test generation, including:
    - Strategic planning (requirement analysis, decomposition, dependencies, risks)
    - Multi-turn reasoning (ReAct pattern, tool usage, reasoning traces)
    - Error recovery (failure analysis, recovery strategies, statistics)
    
    Args:
        id: Test case ID
        current_user: Authenticated user
    
    Returns:
        {
            "status": "success",
            "data": {
                "strategic_planning": {...},
                "multi_turn_reasoning": {...},
                "error_recovery": {...}
            },
            "timestamp": "2024-01-21T10:30:45Z"
        }
    """
    try:
        # Verify user has access to this test case
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT tc.id, tc.client_id 
            FROM test_cases tc
            WHERE tc.id = %s
        """, (id,))
        
        test_case = cursor.fetchone()
        cursor.close()
        return_db_connection(conn)
        
        if not test_case:
            raise HTTPException(status_code=404, detail="Test case not found")
        
        # Verify user's client matches test case's client
        if str(test_case[1]) != str(current_user.client_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get planning data from Redis
        collector = PlanningCollector(
            redis_host=System().redis_host,
            redis_port=System().redis_port
        )
        planning_data = collector.get_planning_data(id)
        
        return {
            "status": "success",
            "data": planning_data,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching planning data for test case {id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/state-machine/{test_case_id}")
async def get_state_machine_data(
    test_case_id: int,
    current_user: User = Depends(get_current_user)
):
    """
    Get State Machine data for a test case.
    Returns current state, history, and statistics.
    """
    try:
        # Verify user has access to this test case
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT tc.id, tc.client_id 
            FROM test_cases tc
            WHERE tc.id = %s
        """, (test_case_id,))
        
        test_case = cursor.fetchone()
        cursor.close()
        return_db_connection(conn)
        
        if not test_case:
            raise HTTPException(status_code=404, detail="Test case not found")
        
        # Verify user's client matches test case's client
        if str(test_case[1]) != str(current_user.client_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get State Machine data from Redis
        try:
            from auroqa.Utils.System import System
            import redis
            
            system = System()
            redis_client = redis.Redis(
                host=system.redis_host,
                port=system.redis_port,
                decode_responses=True
            )
            
            # Get current state
            state_key = f"state_machine:{test_case_id}:current_state"
            current_state = redis_client.get(state_key) or "INIT"
            
            # Get context
            context_key = f"state_machine:{test_case_id}:context"
            context_json = redis_client.get(context_key)
            context = json.loads(context_json) if context_json else {}
            
            # Get history
            history_key = f"state_machine:{test_case_id}:history"
            history_json = redis_client.get(history_key)
            history = json.loads(history_json) if history_json else []
            
            return {
                "status": "success",
                "current_state": current_state,
                "previous_state": context.get("previous_state"),
                "step_number": context.get("step_number", 0),
                "total_steps": context.get("total_steps", 0),
                "confidence": context.get("confidence", 0.0),
                "error_count": context.get("error_count", 0),
                "retry_count": context.get("retry_count", 0),
                "history": history[-20:] if history else [],  # Last 20 transitions
                "timestamp": datetime.utcnow().isoformat()
            }
        
        except Exception as redis_error:
            logger.warning(f"Failed to get State Machine data from Redis: {str(redis_error)}")
            # Return default data if Redis is not available
            return {
                "status": "success",
                "current_state": "INIT",
                "previous_state": None,
                "step_number": 0,
                "total_steps": 0,
                "confidence": 0.0,
                "error_count": 0,
                "retry_count": 0,
                "history": [],
                "timestamp": datetime.utcnow().isoformat()
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching State Machine data for test case {test_case_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test_cases/{test_case_id}/runs")
async def get_test_case_runs(
    test_case_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """
    Get recent test runs for a specific test case.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Verify permission
            cursor.execute(
                "SELECT id FROM test_cases WHERE id = %s AND client_id = %s",
                (test_case_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Test case not found")

            # Fetch runs
            cursor.execute(
                """
                SELECT id, result, run_date, duration
                FROM test_runs
                WHERE test_case_id = %s
                ORDER BY run_date DESC
                LIMIT %s
                """,
                (test_case_id, limit)
            )
            
            runs = []
            for row in cursor.fetchall():
                runs.append({
                    "id": row[0],
                    "result": row[1],
                    "run_date": row[2],
                    "duration": row[3],
                    "environment_id": None
                })
            
            return runs
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching test runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            return_db_connection(conn)