import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
from threading import Thread

from Utils.AIHelper.ImageAnalyzer import ImageAnalyzer
from Utils.AIHelper.TextAnalyzer import TextAnalyzer
from Utils.BrowserAutomation.TestRunner import TestRunner
from Utils.Connectors.KafkaMessageConsumer import KafkaMessageConsumer
from Utils.Connectors.KafkaMessageProducer import KafkaMessageProducer
from fetch_test_steps import get_test_data_from_db
from script_executor import execute_test_case
from test_case_builder import get_tests_tree


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
    global kafka_consumer, consumer_thread
    kafka_consumer = KafkaMessageConsumer('localhost:9092', 'user_requests', 'auroqa-group')
    consumer_thread = Thread(target=kafka_consumer.consume_messages, daemon=True)
    consumer_thread.start()
    yield
    # Shutdown
    if kafka_consumer:
        kafka_consumer.stop()
    if consumer_thread:
        consumer_thread.join(timeout=1)

app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/generate_test_cases_from_data")
async def generate_test_cases(file: UploadFile = File(...)):
    BOOTSTRAP_SERVERS = 'localhost:9092'
    TOPIC = 'user_requests'
    GROUP_ID = 'auroqa-group'

    producer = KafkaMessageProducer(BOOTSTRAP_SERVERS, TOPIC)
    request = {}
    
    if 'json' in file.filename.lower():
        file_content = await file.read()
        request['request_type'] = 'generate_test_cases'
        request['content'] = 'json'
        request['attachment_type'] = 'text'
        request['file_content'] = file_content
        producer.send_message(request)
        producer.close()
    elif 'yaml' in file.filename.lower():
        file_content = await file.read()
        request['request_type'] = 'generate_test_cases'
        request['content'] = 'yaml'
        request['attachment_type'] = 'text'
        request['file_content'] = file_content
        producer.send_message(request)
        producer.close()
    elif 'png' in file.filename.lower():
        print('Processing PNG file')
        try:
            request['request_type'] = 'generate_test_cases'
            request['content'] = 'png'
            request['attachment_type'] = 'image'
            filename = f"{uuid.uuid4()}.png"
            file_path = os.path.abspath(os.path.join(UPLOAD_DIRECTORY, filename))
            request['file_name'] = filename
            request['file_path'] = file_path
            
            # Read file in chunks to handle large files
            contents = b''
            chunk_size = 8192  # 8KB chunks
            
            while chunk := await file.read(chunk_size):
                contents += chunk
                
            if not contents:
                return {"error": "Empty file uploaded"}
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(contents)
            producer.send_message(request)
            producer.close()

            return {"message": "File uploaded successfully", "path": file_path}
            
        except Exception as e:
            print(f'Error processing PNG file: {str(e)}')
            return {"error": f"Failed to save PNG file: {str(e)}"}
    else:
        return {"error": "File type is unsupported yet"}


@app.get("/api/get_tree", response_model=Dict)
async def get_tree() -> JSONResponse:
    """
    Endpoint to get the test tree structure.
    """
    tree_data = get_tests_tree()
    return JSONResponse(content=tree_data)


@app.get("/api/get_test_cases/{id}", response_model=List[Dict])
async def get_test_cases(id: int) -> JSONResponse:
    test_steps = get_test_data_from_db(id)

    return JSONResponse(content=test_steps)


@app.post("/api/run_test_case/{id}", response_model=Dict)
async def run_test_case(id: int) -> JSONResponse:
    """
    Endpoint to run test script.
    """
    runner = TestRunner()
    result = runner.run_test_case(id)
    return JSONResponse(content=result)

@app.post("/api/generate_steps/{id}", response_model=Dict)
async def run_test_case(id: int) -> JSONResponse:
    """
    Endpoint to run test script.
    """
    BOOTSTRAP_SERVERS = 'localhost:9092'
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


if __name__ == "__main__":
    import uvicorn
    # PROD
    uvicorn.run(app, host="127.0.0.1", port=9000)
    # DEBUG
    # uvicorn.run("main:app", host="127.0.0.1", port=9000, reload=True)