import os
import uuid
from datetime import timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
from pydantic import BaseModel, UUID4
from datetime import datetime
import json
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
from test_case_builder import get_tests_tree
from jose import JWTError, jwt
import asyncio

# Initialize connection pool
db_pool = None

def get_db_connection():
    if db_pool is None:
        raise HTTPException(status_code=500, detail="Database pool not initialized")
    return db_pool.getconn()

def return_db_connection(conn):
    if db_pool is not None and conn is not None:
        db_pool.putconn(conn)

class UpdateTestStepAction(BaseModel):
    action: Optional[str] = None
    value: Optional[str] = None

class StepOrderUpdate(BaseModel):
    test_case_id: int
    step_orders: List[Dict[str, int]]

class UserClientUpdate(BaseModel):
    client_id: Optional[str] = None

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
    "http://auroqa.com",
    
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global db_pool, kafka_consumer, consumer_thread
    system = System()
    
    # Initialize database pool
    try:
        db_pool = SimpleConnectionPool(
            minconn=1,
            maxconn=20,  # Increase max connections
            host=system.db_host,
            database=system.db_name,
            user=system.db_user,
            password=system.db_password,
            port=system.db_port
        )
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
    if db_pool:
        db_pool.closeall()

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

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user_data[1]}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    finally:
        cur.close()
        return_db_connection(conn)

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
                    WITH RECURSIVE test_tree AS (
                        -- Root level test cases (parent_id is null)
                        SELECT 
                            tc.id,
                            tc.name,
                            tc.description,
                            tc.type,
                            tc.parent_id,
                            tc.client_id,
                            1 as level
                        FROM test_cases tc
                        WHERE tc.parent_id IS NULL
                        
                        UNION ALL
                        
                        -- Child test cases
                        SELECT 
                            tc.id,
                            tc.name,
                            tc.description,
                            tc.type,
                            tc.parent_id,
                            tc.client_id,
                            tt.level + 1
                        FROM test_cases tc
                        JOIN test_tree tt ON tc.parent_id = tt.id
                    )
                    SELECT 
                        tt.id,
                        tt.name,
                        tt.description,
                        tt.type,
                        tt.parent_id,
                        tt.level,
                        c.id as client_id,
                        c.name as client_name
                    FROM test_tree tt
                    JOIN clients c ON tt.client_id = c.id
                    ORDER BY tt.level, tt.name
                    """
                )
            else:
                cur.execute(
                    """
                    WITH RECURSIVE test_tree AS (
                        -- Root level test cases (parent_id is null)
                        SELECT 
                            tc.id,
                            tc.name,
                            tc.description,
                            tc.type,
                            tc.parent_id,
                            tc.client_id,
                            1 as level
                        FROM test_cases tc
                        WHERE tc.parent_id IS NULL
                        
                        UNION ALL
                        
                        -- Child test cases
                        SELECT 
                            tc.id,
                            tc.name,
                            tc.description,
                            tc.type,
                            tc.parent_id,
                            tc.client_id,
                            tt.level + 1
                        FROM test_cases tc
                        JOIN test_tree tt ON tc.parent_id = tt.id
                    )
                    SELECT 
                        tt.id,
                        tt.name,
                        tt.description,
                        tt.type,
                        tt.parent_id,
                        tt.level,
                        c.id as client_id,
                        c.name as client_name
                    FROM test_tree tt
                    JOIN clients c ON tt.client_id = c.id
                    WHERE c.id = %s
                    ORDER BY tt.level, tt.name
                    """,
                    (client_id,)
                )

            rows = cur.fetchall()
            
            # Create root node
            root = {
                'id': 'root',
                'name': 'Test Cases',
                'type': 'root',
                'children': []
            }
            
            # Create lookup dictionaries for each level
            nodes_by_id = {'root': root}
            
            # First pass: create all nodes
            for row in rows:
                node = {
                    'id': str(row[0]),
                    'name': row[1],
                    'description': row[2],
                    'type': 'test' if row[3] == 'test' else row[3],  # Ensure we use 'test' instead of 'test_case'
                    'children': []
                }
                nodes_by_id[node['id']] = node
            
            # Second pass: build the tree structure
            for row in rows:
                node_id = str(row[0])
                parent_id = str(row[4]) if row[4] else 'root'
                
                if parent_id in nodes_by_id:
                    parent = nodes_by_id[parent_id]
                    parent['children'].append(nodes_by_id[node_id])
            
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
        runner = TestRunner()
        
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
        runner = TestRunner()
        
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
        
        # Start the test step generation in a separate thread
        thread = Thread(target=runner.generate_test_steps, args=(id, environment_vars))
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
            # Verify the test case exists and belongs to the user's client
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
        runner = TestRunner()
        
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
        
        # Start the test step generation in a separate thread
        thread = Thread(target=runner.generate_test_steps, args=(id, environment_vars))
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
            cursor.execute(
                """
                SELECT id, name, description, created_at, updated_at
                FROM projects
                WHERE client_id = %s
                ORDER BY name
                """,
                (str(current_user.client_id),)
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
                    project_data.get("name"),
                    project_data.get("description"),
                    str(current_user.client_id)
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
    # Helper function to build tree structure
    def build_tree(nodes, parent_id=None):
        tree = []
        for node in nodes:
            if node['parent_id'] == parent_id:
                children = build_tree(nodes, node['id'])
                if children:
                    node['children'] = children
                else:
                    node['children'] = []
                tree.append(node)
        return tree
    
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
            
            # Get all test cases for this project
            cursor.execute(
                """
                SELECT id, name, description, parent_id, type, "order", created_at, updated_at
                FROM test_cases
                WHERE client_id = %s AND project_id = %s
                ORDER BY "order"
                """,
                (str(current_user.client_id), project_id)
            )
            test_cases = cursor.fetchall()
            
            # Convert to a list of dictionaries
            test_cases_list = [
                {
                    "id": test_case[0],
                    "name": test_case[1],
                    "description": test_case[2],
                    "parent_id": test_case[3],
                    "type": test_case[4],
                    "order": test_case[5],
                    "created_at": test_case[6].isoformat() if test_case[6] else None,
                    "updated_at": test_case[7].isoformat() if test_case[7] else None
                }
                for test_case in test_cases
            ]
            
            # Build the tree structure directly
            tree_data = build_tree(test_cases_list)
            return tree_data
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
                SELECT id, name, base_url, login, password, created_at, updated_at
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
                    "updated_at": environment[6].isoformat() if environment[6] else None
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
            
            # Create the environment
            cursor.execute(
                """
                INSERT INTO environments (name, base_url, login, password, project_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, base_url, login, password, created_at, updated_at
                """,
                (
                    environment_data.get("name"),
                    environment_data.get("base_url"),
                    environment_data.get("login"),
                    environment_data.get("password"),
                    project_id
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
                "updated_at": environment[6].isoformat() if environment[6] else None
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
            
            # Update the environment
            cursor.execute(
                """
                UPDATE environments
                SET name = %s, base_url = %s, login = %s, password = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, name, base_url, login, password, project_id, created_at, updated_at
                """,
                (
                    environment_data.get("name"),
                    environment_data.get("base_url"),
                    environment_data.get("login"),
                    environment_data.get("password"),
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
                "updated_at": environment[7].isoformat() if environment[7] else None
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
        error_detail = f"Failed to delete test step: {str(e)}"
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
        error_detail = f"Failed to delete test case: {str(e)}"
        print(f"Error in delete_test_case: {error_detail}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_detail)
    finally:
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