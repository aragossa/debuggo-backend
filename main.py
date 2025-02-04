import os
import uuid
from datetime import timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
from threading import Thread
from pydantic import BaseModel
from psycopg2.pool import SimpleConnectionPool
from Utils.BrowserAutomation.TestRunner import TestRunner
from Utils.Connectors.KafkaMessageConsumer import KafkaMessageConsumer
from Utils.Connectors.KafkaMessageProducer import KafkaMessageProducer
from Utils.System import System
from Utils.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from models.user import UserCreate, User, Token
from models.client import ClientCreate, Client
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
    kafka_consumer = KafkaMessageConsumer(kafka_bootstrap_servers, 'user_requests', 'auroqa-group')
    consumer_thread = Thread(target=kafka_consumer.consume_messages, daemon=True)
    consumer_thread.start()
    
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
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    if not current_user.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any client"
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
            'client_id': str(current_user.client_id)  # Add client_id to the message
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
async def run_test_case(id: int, current_user: User = Depends(get_current_user)):
    """
    Endpoint to run test script.
    """
    try:
        # Get the singleton instance of TestRunner
        runner = TestRunner()
        
        # Run the test case in a blocking manner to prevent concurrent executions
        result = await asyncio.to_thread(runner.run_test_case, id)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run test case: {str(e)}"
        )

@app.post("/api/generate_steps/{id}", response_model=Dict)
async def run_test_case(id: int, current_user: User = Depends(get_current_user)):
    """
    Endpoint to run test script.
    """
    system = System()
    BOOTSTRAP_SERVERS = f"{system.kafka_host}:{system.kafka_port}"
    TOPIC = 'user_requests'
    GROUP_ID = 'auroqa-group'

    producer = KafkaMessageProducer(BOOTSTRAP_SERVERS, TOPIC)
    request = {}

    request['request_type'] = 'generate_test_steps'
    request['test_case_id'] = f'{id}'
    producer.send_message(request)
    producer.close()

    result = {'result': 'queued'}
    return JSONResponse(content=result)

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