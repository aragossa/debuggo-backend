from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict

from Utils.AIHelper.ImageAnalyzer import ImageAnalyzer
from Utils.AIHelper.TextAnalyzer import TextAnalyzer
from Utils.clear_data import clear_all_data
from fetch_test_steps import get_test_data_from_db
from script_executor import execute_test_case
from test_case_builder import get_tests_tree

app = FastAPI()

# Add CORS middleware
origins = [
    "http://localhost",  # Adjust this to match your frontend's origin
    "http://localhost:3000", # If you're using a different port
    "http://18.194.44.160:3000", # If you're using a different port
    "http://localhost:8080", # If you're using a different port
    "http://18.184.65.241", # If you're using a different port
    "http://auroqa.com", # If you're using a different port
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




@app.post("/api/generate_test_cases_from_data")
async def generate_test_cases(file: UploadFile = File(...)):
    # Process the uploaded file
    file_content = await file.read()
    result = {"message": f"Received file: {file.filename}, Content: {file_content}"}
    if 'json' in file.filename:
        text_analyzer = TextAnalyzer()
        result = text_analyzer.analyze_txt(file_content)
    elif 'yaml' in file.filename:
        text_analyzer = TextAnalyzer()
        result = text_analyzer.analyze_txt(file_content)
    elif 'png' in file.filename:
        image_analyzer = ImageAnalyzer()
        result = image_analyzer.analyze_img(file_content, file)

    return JSONResponse(content=result)

@app.get("/api/get_tree", response_model=Dict)
async def get_tree() -> JSONResponse:
    """
    Endpoint to get the test tree structure.
    """
    tree_data = get_tests_tree()
    return JSONResponse(content=tree_data)


@app.get("/api/get_test_cases/{id}", response_model=List[Dict])
async def get_test_cases(id: int) -> JSONResponse:
    """
    Endpoint to get the list of test cases.
    """
    print(id)
    test_steps = get_test_data_from_db(id)
    print(test_steps)

    return JSONResponse(content=test_steps)


@app.post("/api/run_test_case/{id}", response_model=Dict)
async def run_test_case(id: int) -> JSONResponse:
    """
    Endpoint to run test script.
    """
    result = execute_test_case(id)
    return JSONResponse(content=result)

@app.get("/api/clear_all", response_model=Dict)
async def clear_all() -> JSONResponse:
    """
    Endpoint to clear all test cases, test steps, test runs
    """
    clear_all_data()
    return {"message": "All data cleared successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9000)