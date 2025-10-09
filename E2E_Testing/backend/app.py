from fastapi import FastAPI, Query, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware 
from fastapi.responses import StreamingResponse, JSONResponse
import json
import pandas as pd
from E2E_Agent import setup_python_playwright, safe_base_path
from E2E_Agent import run_playwright_generator

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 👈 or specify ["http://localhost:3000"]
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
async def generate_test_script(file: UploadFile = File(...), project_url: str = Form(...)):
    try:
        # Load file
        if file.filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file.file)
        elif file.filename.endswith(".csv"):
            df = pd.read_csv(file.file)
        else:
            return JSONResponse(status_code=400, content={"error": "Invalid file type. Must be CSV or Excel."})

        # Strip column names
        df.columns = [col.strip() for col in df.columns]

        # Only required columns
        required_cols = ["Scenario", "Scenario Description", "Steps to Execute", "Test Data", "Expected Result"]

        # Check missing
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            return JSONResponse(status_code=400, content={"error": f"Missing columns: {', '.join(missing_cols)}"})

        # Take only required columns (ignore extra ones)
        df = df[required_cols]

        # Convert to list of dicts for the generator
        test_cases = df.to_dict(orient="records")

        # Run LangGraph Playwright generator
        script_output = run_playwright_generator(test_cases, project_url)

        if not script_output.strip():
            return JSONResponse(status_code=500, content={"error": "No script generated. Check your API key or model."})

        return {"script": script_output}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
