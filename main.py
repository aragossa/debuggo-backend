import os
import uuid
from datetime import timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
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
from fetch_test_steps import get_test_data_from_db
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
    action: str

class StepOrderUpdate(BaseModel):
    test_case_id: int
    step_orders: List[Dict[str, int]]

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
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, email, full_name, is_active, created_at, last_login
            FROM users WHERE email = %s
            """,
            (email,)
        )
        user_data = cur.fetchone()
        if user_data is None:
            raise credentials_exception
        
        return User(
            id=user_data[0],
            email=user_data[1],
            full_name=user_data[2],
            is_active=user_data[3],
            created_at=user_data[4],
            last_login=user_data[5]
        )
    finally:
        cur.close()
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
        cur = conn.cursor()
        # Check if user already exists
        cur.execute("SELECT id FROM users WHERE email = %s", (user_data.email,))
        if cur.fetchone() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create new user
        hashed_password = get_password_hash(user_data.password)
        cur.execute(
            """
            INSERT INTO users (email, password_hash, full_name)
            VALUES (%s, %s, %s)
            RETURNING id, email, full_name, is_active, created_at, last_login
            """,
            (user_data.email, hashed_password, user_data.full_name)
        )
        user_data = cur.fetchone()
        conn.commit()
        
        return User(
            id=user_data[0],
            email=user_data[1],
            full_name=user_data[2],
            is_active=user_data[3],
            created_at=user_data[4],
            last_login=user_data[5]
        )
    finally:
        cur.close()
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

@app.post("/api/generate_test_cases_from_data", response_model=Dict)
async def generate_test_cases(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Generate test cases from uploaded file data.
    Accepts JSON, YAML, or PNG files.
    """
    try:
        # Validate file extension
        allowed_extensions = ['.json', '.yaml', '.yml', '.png']
        file_ext = os.path.splitext(file.filename.lower())[1]
        
        if not file_ext:
            raise HTTPException(
                status_code=422,
                detail="File must have an extension"
            )
            
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type. Allowed types: {', '.join(allowed_extensions)}"
            )

        # Initialize Kafka producer
        system = System()
        BOOTSTRAP_SERVERS = f"{system.kafka_host}:{system.kafka_port}"
        TOPIC = 'user_requests'
        producer = KafkaMessageProducer(BOOTSTRAP_SERVERS, TOPIC)
        request = {
            'request_type': 'generate_test_cases',
            'user_id': current_user.id
        }
        
        try:
            if file_ext in ['.json', '.yaml', '.yml']:
                file_content = await file.read()
                if not file_content:
                    raise HTTPException(
                        status_code=422,
                        detail="Empty file uploaded"
                    )
                    
                request.update({
                    'content': 'json' if file_ext == '.json' else 'yaml',
                    'attachment_type': 'text',
                    'file_content': file_content
                })
                producer.send_message(request)
                
            elif file_ext == '.png':
                # Handle PNG files
                filename = f"{uuid.uuid4()}.png"
                file_path = os.path.abspath(os.path.join(UPLOAD_DIRECTORY, filename))
                
                # Read file in chunks
                contents = b''
                chunk_size = 8192  # 8KB chunks
                while chunk := await file.read(chunk_size):
                    contents += chunk
                    
                if not contents:
                    raise HTTPException(
                        status_code=422,
                        detail="Empty PNG file uploaded"
                    )
                
                # Save PNG file
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(contents)
                
                request.update({
                    'content': 'png',
                    'attachment_type': 'image',
                    'file_name': filename,
                    'file_path': file_path
                })
                producer.send_message(request)
            
            return {
                "status": "success",
                "message": "File processed successfully",
                "file_type": file_ext[1:],  # Remove leading dot
                "user_id": current_user.id
            }
            
        finally:
            producer.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )

@app.get("/api/get_tree", response_model=Dict)
async def get_tree(current_user: User = Depends(get_current_user)):
    """
    Endpoint to get the test tree structure.
    """
    tree_data = get_tests_tree()
    return JSONResponse(content=tree_data)

@app.get("/api/get_test_cases/{id}", response_model=List[Dict])
async def get_test_cases(id: int, current_user: User = Depends(get_current_user)):
    test_steps = get_test_data_from_db(id)

    return JSONResponse(content=test_steps)

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
            
            # Update the action
            cursor.execute(
                "UPDATE test_steps SET action = %s WHERE id = %s",
                (update_data.action, id)
            )
            conn.commit()
            
            return JSONResponse(
                content={"message": "Test step action updated successfully"},
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
                "SELECT id FROM test_cases WHERE id = %s",
                (update_data.test_case_id,)
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
            content={"error": "Failed to update step orders"}
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