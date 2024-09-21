from http.client import responses

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict

from starlette.responses import JSONResponse

from fetch_test_steps import get_test_data_from_db
from image_testcases import get_test_cases_from_image
from image_validator import is_relevant_content
from json_testcases import get_test_cases_from_json
from script_executor import execute_test_case
from test_case_builder import get_tests_tree

app = FastAPI()

# Add CORS middleware
origins = [
    "http://localhost",  # Adjust this to match your frontend's origin
    "http://localhost:3000", # If you're using a different port
    # Add more origins as needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Sample data for /get_test_cases route




@app.post("/generate_test_cases_from_data")
async def generate_test_cases(file: UploadFile = File(...)):
    # Process the uploaded file (e.g., save it, analyze it)
    file_content = await file.read()

    # Replace this with your actual logic to generate test cases
    result = {"message": f"Received file: {file.filename}, Content: {file_content}"}
    print(file.filename)
    if 'json' in file.filename:
        result = get_test_cases_from_json(file_content)
    elif 'yaml' in file.filename:
        result = get_test_cases_from_json(file_content)
    elif 'png' in file.filename:
        result = get_test_cases_from_image(file_content, file)

    return JSONResponse(content=result)

@app.get("/get_tree", response_model=Dict)
async def get_tree() -> JSONResponse:
    """
    Endpoint to get the test tree structure.
    """
    tree_data = get_tests_tree()
    return JSONResponse(content=tree_data)


@app.get("/get_test_cases/{id}", response_model=List[Dict])
async def get_test_cases(id: int) -> JSONResponse:
    """
    Endpoint to get the list of test cases.
    """
    print(id)
    test_steps = get_test_data_from_db(id)
    print(test_steps)

    return JSONResponse(content=test_steps)


@app.post("/run_test_case/{id}", response_model=Dict)
async def run_test_case(id: int) -> JSONResponse:
    """
    Endpoint to run test script.
    """
    result = execute_test_case(id)
    return JSONResponse(content=result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9000)