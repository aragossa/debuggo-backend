import os
import uuid
import json
from datetime import timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Form, File, UploadFile, BackgroundTasks, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
from pydantic import BaseModel, UUID4
from datetime import datetime
import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool
import jwt
from kafka import KafkaProducer, KafkaConsumer
import threading
from threading import Thread
import time
import sys
import logging
import traceback
from pathlib import Path
import requests
from models.user import User, UserCreate, UserLogin, Token
from models.client import Client, ClientCreate
from models.test import GenerateStepsRequest
from Utils.System import System
from Utils.BrowserAutomation.TestRunner import TestRunner
from Utils.BrowserAutomation.BrowserAutomation import BrowserAutomation
from Utils.Connectors.KafkaMessageConsumer import KafkaMessageConsumer
from Utils.Connectors.KafkaMessageProducer import KafkaMessageProducer
from Utils.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from models.crud import create_user, get_user_by_email, get_client_test_cases
from fetch_test_steps import get_test_data_from_db_helper
from test_case_builder import get_tests_tree, build_tree
from jose import JWTError, jwt
import asyncio
from Utils.Connectors.db_utils import get_db_connection, return_db_connection, init_db_pool

# Initialize connection pool
db_pool = None

class UpdateTestStepAction(BaseModel):
    action: Optional[str] = None
    value: Optional[str] = None
    element_path: Optional[str] = None

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
    target_group_id: int

class CreateTestCaseRequest(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    project_id: Optional[UUID4] = None

class UpdateTestCaseRequest(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    conn = get_db_connection()
    try:
        user = get_user_by_email(conn, email)
        if user is None:
            raise credentials_exception
        return user
    finally:
        return_db_connection(conn)

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
    "http://18.184.65.241",
    "http://95.217.211.91",
    "http://auroqa.com",
    
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
        from Utils.Connectors.db_utils import db_pool as utils_db_pool
        db_pool = utils_db_pool
    except Exception as e:
        print(f"Failed to initialize database pool: {e}")
        raise

    # Initialize Kafka consumer
    kafka_bootstrap_servers = f"{system.kafka_host}:{system.kafka_port}"
    try:
        kafka_consumer = KafkaMessageConsumer(kafka_bootstrap_servers, 'user_requests', 'auroqa-group')
        consumer_thread = Thread(target=kafka_consumer.consume_messages, daemon=True)
        consumer_thread.start()
        print(f"Kafka consumer initialized and connected to {kafka_bootstrap_servers}")
    except Exception as e:
        print(f"Warning: Failed to initialize Kafka consumer: {e}")
        print("Application will continue without Kafka integration")
        kafka_consumer = None
        consumer_thread = None
    
    # Initialize TestRunner singleton
    try:
        TestRunner()  # This will initialize the Redis connection
    except Exception as e:
        print(f"Failed to initialize TestRunner: {e}")
        raise
    
    yield

    # Shutdown
    if kafka_consumer:
        kafka_consumer.stop()
    if consumer_thread:
        consumer_thread.join(timeout=1.0)
    # Close the database pool using db_utils
    from Utils.Connectors.db_utils import close_db_pool
    close_db_pool()

app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_dependencies():
    return {
        "get_conn": get_db_connection,
        "return_conn": return_db_connection
    }

@app.post("/api/register", response_model=User)
async def register_user(user_data: UserCreate):
    conn = get_db_connection()
    try:
        return create_user(conn, user_data)
    finally:
        return_db_connection(conn)

@app.post("/api/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, email, password_hash, full_name, is_active
            FROM users WHERE email = %s
            """,
            (form_data.username,)
        )
        user_data = cur.fetchone()
        
        if not user_data or not verify_password(form_data.password, user_data[2]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Update last login time
        cur.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
            (user_data[0],)
        )
        conn.commit()

        # Create access token with longer expiration (24 hours instead of 60 minutes)
        access_token_expires = timedelta(hours=24)
        access_token = create_access_token(
            data={"sub": user_data[1]}, expires_delta=access_token_expires
        )
        
        return {"access_token": access_token, "token_type": "bearer"}
    finally:
        cur.close()
        return_db_connection(conn)

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
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.email, u.full_name, u.role, u.client_id, c.name as client_name
                FROM users u
                LEFT JOIN clients c ON u.client_id = c.id
                ORDER BY u.email
            """)
            users = []
            for row in cur.fetchall():
                users.append({
                    'id': row[0],
                    'email': row[1],
                    'full_name': row[2],
                    'role': row[3],
                    'client_id': row[4],
                    'client_name': row[5]
                })
            return users
    finally:
        return_db_connection(conn)

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
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Convert UUID to string for the query
            client_id = str(current_user.client_id) if current_user.client_id else None
            
            if current_user.role == 'admin':
                cur.execute(
                    """
                    WITH RECURSIVE TestCaseHierarchy AS (
                        SELECT id, name, description, parent_id, type, "order", client_id, project_id, created_at, updated_at
                        FROM test_cases
                        WHERE parent_id IS NULL
                        
                        UNION ALL
                        
                        SELECT tc.id, tc.name, tc.description, tc.parent_id, tc.type, tc."order", tc.client_id, tc.project_id, tc.created_at, tc.updated_at
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
                        t.project_id
                    FROM TestCaseHierarchy t
                    JOIN clients c ON t.client_id = c.id
                    ORDER BY t.parent_id NULLS FIRST, t."order"
                    """
                )
            else:
                cur.execute(
                    """
                    WITH RECURSIVE TestCaseHierarchy AS (
                        SELECT id, name, description, parent_id, type, "order", client_id, project_id, created_at, updated_at
                        FROM test_cases
                        WHERE parent_id IS NULL AND client_id = %s AND project_id = %s
                        
                        UNION ALL
                        
                        SELECT tc.id, tc.name, tc.description, tc.parent_id, tc.type, tc."order", tc.client_id, tc.project_id, tc.created_at, tc.updated_at
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
                        t.project_id
                    FROM TestCaseHierarchy t
                    JOIN clients c ON t.client_id = c.id
                    WHERE c.id = %s
                    ORDER BY t.parent_id NULLS FIRST, t."order"
                    """,
                    (client_id, current_user.client_id, client_id, current_user.client_id, client_id)
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
                    'project_id': row[10]
                })
            
            # Use the build_tree function from test_case_builder
            tree_data = build_tree(test_cases_list)
            
            # Create root node
            root = {
                'id': 'root',
                'name': 'Test Cases',
                'type': 'root',
                'children': tree_data
            }
            
            return [root]
    finally:
        return_db_connection(conn)

@app.get("/api/get_test_cases/{id}")
async def get_test_cases(id: int, current_user: User = Depends(get_current_user)):
    if not current_user.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any client"
        )
    conn = get_db_connection()
    try:
        from fetch_test_steps import get_test_data_from_db_helper
        return get_test_data_from_db_helper(conn, id, str(current_user.client_id))
    finally:
        return_db_connection(conn)

@app.post("/api/run_test_case/{id}", response_model=Dict)
async def run_test_case(
    id: int, 
    request_data: dict = None,
    current_user: User = Depends(get_current_user)
):
    """
    Endpoint to run test script.
    If environment_id is provided, the test will use the environment variables.
    """
    conn = None
    try:
        # Get the singleton instance of TestRunner
        runner = TestRunner(user_id=str(current_user.id), test_case_id=id)
        
        environment_vars = {}
        
        # If environment_id is provided, fetch environment variables
        if request_data and "environment_id" in request_data:
            environment_id = request_data.get("environment_id")
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT e.base_url, e.login, e.password
                    FROM environments e
                    JOIN projects p ON e.project_id = p.id
                    WHERE e.id = %s AND p.client_id = %s
                    """,
                    (environment_id, str(current_user.client_id))
                )
                env_data = cursor.fetchone()
                
                if env_data:
                    environment_vars = {
                        "base_url": env_data[0],
                        "login": env_data[1],
                        "password": env_data[2]
                    }
        
        # Run the test case in a blocking manner to prevent concurrent executions
        result = await asyncio.to_thread(runner.run_test_case, id, environment_vars)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run test case: {str(e)}"
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
        print(f"Error updating test case project: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update test case project: {str(e)}"
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
        
        # Get the AI model ID to use
        ai_model_id = None
        if request_data and request_data.ai_model_id:
            # Use the model specified in the request
            ai_model_id = request_data.ai_model_id
        else:
            # Check if the user has a preferred model
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT ai_model_id FROM user_ai_models WHERE user_id = %s
                        """,
                        (current_user.id,)
                    )
                    user_model = cursor.fetchone()
                    if user_model:
                        ai_model_id = user_model[0]
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
            finally:
                if conn:
                    return_db_connection(conn)
        # Start the test step generation in a separate thread
        thread = Thread(target=runner.generate_test_steps, args=(id, environment_vars, ai_model_id))
        thread.daemon = True
        thread.start()
        
        return {"status": "started"}
    except Exception as e:
        print(f"Error generating test steps: {e}")
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
            
            # Delete existing steps
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
        print(f"Error deleting existing test steps: {e}")
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
        
        # Get the AI model ID to use
        ai_model_id = None
        if request_data and request_data.ai_model_id:
            # Use the model specified in the request
            ai_model_id = request_data.ai_model_id
        else:
            # Check if the user has a preferred model
            conn = get_db_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT ai_model_id FROM user_ai_models WHERE user_id = %s
                        """,
                        (current_user.id,)
                    )
                    user_model = cursor.fetchone()
                    if user_model:
                        ai_model_id = user_model[0]
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
            finally:
                if conn:
                    return_db_connection(conn)
        # Start the test step generation in a separate thread
        thread = Thread(target=runner.generate_test_steps, args=(id, environment_vars, ai_model_id))
        thread.daemon = True
        thread.start()
        
        return {"status": "started"}
    except Exception as e:
        print(f"Error generating test steps: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate test steps: {str(e)}"
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
            
            # Build update query based on provided fields
            update_fields = []
            params = []
            if update_data.action is not None:
                update_fields.append("action = %s")
                params.append(update_data.action)
            if update_data.value is not None:
                update_fields.append("value = %s")
                params.append(update_data.value)
            if update_data.element_path is not None:
                update_fields.append("element_path = %s")
                params.append(update_data.element_path)
            
            if not update_fields:
                raise HTTPException(status_code=400, detail="No fields to update")
            
            # Update the fields
            query = f"UPDATE test_steps SET {', '.join(update_fields)} WHERE id = %s"
            params.append(id)
            cursor.execute(query, tuple(params))
            conn.commit()
            
            return JSONResponse(
                content={"message": "Test step updated successfully"},
                status_code=200
            )
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Error updating test step: {e}")
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
        print(f"Error updating step orders: {e}")
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
                request_data.action,
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
        print(f"Error listing projects: {e}")
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
        print(f"Error creating project: {e}")
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
        print(f"Error getting project: {e}")
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
        print(f"Error updating project: {e}")
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
        print(f"Error deleting project: {e}")
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
            
            print(f"Fetching test tree for project_id: {project_id}, client_id: {client_id_str}")
            
            # Let's also check all test cases for this project
            cursor.execute(
                """
                SELECT id, name, parent_id, type, client_id, project_id
                FROM test_cases
                WHERE project_id = %s
                ORDER BY id
                """,
                (project_id,)
            )
            all_project_test_cases = cursor.fetchall()
            print(f"All test cases for project {project_id}:")
            for tc in all_project_test_cases:
                print(f"  ID: {tc[0]}, Name: {tc[1]}, Parent: {tc[2]}, Type: {tc[3]}")
            
            # Use a recursive query to get all test cases for this project with proper hierarchy
            cursor.execute(
                """
                WITH RECURSIVE TestCaseHierarchy AS (
                    -- Base case: get all root nodes
                    SELECT id, name, description, parent_id, type, "order", created_at, updated_at
                    FROM test_cases
                    WHERE parent_id IS NULL AND project_id = %s
                    
                    UNION ALL
                    
                    -- Recursive case: get all children
                    SELECT tc.id, tc.name, tc.description, tc.parent_id, tc.type, tc."order", tc.created_at, tc.updated_at
                    FROM test_cases tc
                    JOIN TestCaseHierarchy tch ON tc.parent_id = tch.id
                    WHERE tc.project_id = %s
                )
                SELECT id, name, description, parent_id, type, "order", created_at, updated_at
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
            
            return root_items
    except Exception as e:
        print(f"Error getting project test tree: {e}")
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
        print(f"Error getting project environments: {e}")
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
        print(f"Error creating environment: {e}")
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
        print(f"Error updating environment: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update environment: {str(e)}"
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
        print(f"Error deleting environment: {e}")
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
        print(f"Test step client_id: {step['client_id']}, type: {type(step['client_id'])}")
        print(f"User client_id: {client_id}, type: {type(client_id)}")
        
        # Convert both to string for comparison if they're not already strings
        test_step_client_id = str(step['client_id'])
        user_client_id = str(client_id)
        
        print(f"Comparing: '{test_step_client_id}' == '{user_client_id}'")
        
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
        
        return {"status": "success", "message": "Test step deleted successfully"}
    
    except Exception as e:
        conn.rollback()
        # Include more detailed error information for debugging
        error_detail = f"Failed to delete test step: {e}"
        print(f"Error in delete_test_step: {error_detail}")
        print(f"Traceback: {traceback.format_exc()}")
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
        print(f"Test case client_id: {test_case['client_id']}, type: {type(test_case['client_id'])}")
        print(f"User client_id: {client_id}, type: {type(client_id)}")
        
        # Convert both to string for comparison if they're not already strings
        test_case_client_id = str(test_case['client_id'])
        user_client_id = str(client_id)
        
        print(f"Comparing: '{test_case_client_id}' == '{user_client_id}'")
        
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
        print(f"Error in delete_test_case: {error_detail}")
        print(f"Traceback: {traceback.format_exc()}")
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
            
            print(f"Debug - Request data: {request_data}")
            print(f"Debug - Project ID (raw): {request_data.project_id}, type: {type(request_data.project_id)}")
            print(f"Debug - Project ID (string): {project_id_str}")
            print(f"Debug - Client ID: {client_id_str}")
            
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
            print(f"Debug - Created group: {group}")
            print(f"Debug - Group project_id: {group[7]}")
            
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
        print(f"Error creating test group: {str(e)}")
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
            
            print(f"Debug - Group client_id: {group_client_id}")
            print(f"Debug - User client_id: {user_client_id}")
            
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
            
            print(f"Debug - Group client_id: {group_client_id}")
            print(f"Debug - User client_id: {user_client_id}")
            
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
            
            print(f"Debug - Project ID: {project_id_str}")
            print(f"Debug - Client ID: {client_id_str}")
            
            # Insert the new test case
            cur.execute(
                """
                INSERT INTO test_cases (name, description, parent_id, type, "order", client_id, project_id)
                VALUES (%s, %s, %s, 'test', 1, %s, %s)
                RETURNING id, name, description, parent_id, type, "order", created_at, updated_at, project_id
                """,
                (
                    request_data.name,
                    request_data.description,
                    request_data.parent_id,
                    client_id_str,
                    project_id_str
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
                "project_id": test_case[8]
            }
    except Exception as e:
        conn.rollback()
        print(f"Error creating test case: {str(e)}")
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
            
            print(f"Debug - Test case client_id: {test_case_client_id}")
            print(f"Debug - User client_id: {user_client_id}")
            
            # Skip permission check if client_id is None (for development/testing)
            if test_case_client_id and user_client_id and test_case_client_id != user_client_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to move this test case"
                )
            
            # Check if the target group exists and is a valid group
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
            
            print(f"Debug - Target group client_id: {target_group_client_id}")
            
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
                print(f"SQL Error: {str(sql_error)}")
                traceback.print_exc()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database error: {str(sql_error)}"
                )
    except Exception as e:
        conn.rollback()
        print(f"Error in move_test_case: {str(e)}")
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
                cur.execute(
                    """
                    UPDATE test_cases 
                    SET name = %s, description = %s, parent_id = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, name, description, parent_id, type, "order", created_at, updated_at, project_id
                    """,
                    (
                        request_data.name,
                        request_data.description,
                        request_data.parent_id,
                        id
                    )
                )
            else:
                cur.execute(
                    """
                    UPDATE test_cases 
                    SET name = %s, description = %s, updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, name, description, parent_id, type, "order", created_at, updated_at, project_id
                    """,
                    (
                        request_data.name,
                        request_data.description,
                        id
                    )
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
                "project_id": updated_test_case[8]
            }
    except Exception as e:
        conn.rollback()
        print(f"Error updating test case: {str(e)}")
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
    Returns the screenshot as a base64 encoded string.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # First verify that the test step belongs to the current user's client
            cursor.execute(
                """
                SELECT ts.id 
                FROM test_steps ts
                JOIN test_cases tc ON ts.test_case_id = tc.id
                WHERE ts.id = %s AND tc.client_id = %s
                """,
                (step_id, str(current_user.client_id))
            )
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="Test step not found or you don't have permission to access it"
                )
            
            # Get the screenshot
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
            
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail="No screenshot found for this test step"
                )
            
            # Convert the result to a dictionary
            screenshot_data = result[0]
            if isinstance(screenshot_data, memoryview):
                screenshot_data = bytes(screenshot_data)
            
            if isinstance(screenshot_data, bytes):
                screenshot_data = screenshot_data.decode('utf-8')
            
            screenshot_dict = {
                "screenshot": screenshot_data,
                "description": result[1] if result[1] is not None else "Screenshot"
            }
            
            # Return the dictionary directly
            return JSONResponse(content=screenshot_dict)
    except Exception as e:
        # Check if the error is related to the screenshot not being found
        if "No screenshot found" in str(e) or "screenshot" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail=f"No screenshot found for this test step: {str(e)}"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve screenshot: {str(e)}"
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
            
            # Check if the test case is currently generating steps
            runner = TestRunner(user_id=str(current_user.id), test_case_id=id)
            is_generating = runner.is_generating_steps(id)
            
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
                    print(f"Error getting step information from Redis: {e}")
            
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
        print(f"Error checking test case generation status: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check test case generation status: {str(e)}"
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
            
            return {"status": "stopped"}
    except Exception as e:
        print(f"Error stopping test case generation: {e}")
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

# AI Model Management Endpoints

class AIModelCreate(BaseModel):
    name: str
    model_id: str
    description: Optional[str] = None
    is_active: Optional[bool] = True
    is_default: Optional[bool] = False

class AIModelUpdate(BaseModel):
    name: Optional[str] = None
    model_id: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None

@app.get("/api/ai-models", response_model=List[Dict])
async def list_ai_models(current_user: User = Depends(get_current_user)):
    """
    List all available AI models.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT id, name, model_id, description, is_active, is_default, created_at, updated_at
                FROM ai_models
                ORDER BY name
            """)
            models = cursor.fetchall()
            
            # Check if the user has a preferred model
            cursor.execute("""
                SELECT ai_model_id
                FROM user_ai_models
                WHERE user_id = %s
            """, (current_user.id,))
            user_model = cursor.fetchone()
            
            # Add user_selected flag to each model
            for model in models:
                model['user_selected'] = user_model and model['id'] == user_model['ai_model_id']
                
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
            
            # Insert new model
            cursor.execute("""
                INSERT INTO ai_models (name, model_id, description, is_active, is_default)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                model_data.name,
                model_data.model_id,
                model_data.description,
                model_data.is_active,
                model_data.is_default
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
    model_data: dict = Body(..., example={"ai_model_id": 1}),
    current_user: User = Depends(get_current_user)
):
    """
    Set the user's preferred AI model.
    """
    conn = None
    try:
        ai_model_id = model_data.get("ai_model_id")
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
                    SET ai_model_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                """, (ai_model_id, current_user.id))
            else:
                # Insert new preference
                cursor.execute("""
                    INSERT INTO user_ai_models (user_id, ai_model_id)
                    VALUES (%s, %s)
                """, (current_user.id, ai_model_id))
            
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=9000,
        workers=1,  # Use single worker to avoid process-level concurrency
        timeout_keep_alive=30,
        access_log=True,
        reload=True
    )