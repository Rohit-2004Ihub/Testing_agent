from fastapi import FastAPI, Query, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware 
from fastapi.responses import StreamingResponse, JSONResponse
import json
import pandas as pd
from langgraph_agent import setup_python_playwright, safe_base_path, run_playwright_generator
from pathlib import Path

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # your React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/setup_playwright_project")
def auto_setup(path: str = Query(...)):
    """
    Stream logs while setting up Playwright in a safe folder.
    """
    base_path = safe_base_path(path)
    generator = setup_python_playwright(base_path, stream=True)

    def event_stream():
        for log_entry in generator:
            yield f"data: {json.dumps(log_entry)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/parse_input")
def generate_test_script(
    file: UploadFile = File(...),
    project_url: str = Form(...)
):
    """
    Generate Playwright test script using LangGraph + Gemini 2.5 Flash agent.
    """
    try:
        # Read the uploaded file into a DataFrame
        if file.filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file.file)
        elif file.filename.endswith(".csv"):
            df = pd.read_csv(file.file)
        else:
            return JSONResponse(status_code=400, content={"error": "Invalid file type. Must be CSV or Excel."})

        required_cols = ["Scenario", "Scenario Description", "Steps to Execute", "Expected Result"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return JSONResponse(status_code=400, content={"error": f"Missing columns: {', '.join(missing_cols)}"})

        test_cases = df[required_cols].to_dict(orient="records")

        # Run the full LangGraph workflow
        script_output = run_playwright_generator(test_cases, project_url)
        return {"script": script_output}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})