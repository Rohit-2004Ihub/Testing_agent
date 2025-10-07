import subprocess
import sys
from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from typing import TypedDict, List, Dict
import os
from dotenv import load_dotenv
import pandas as pd
from fastapi import FastAPI, Query, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import json

load_dotenv()  # Load env vars (including GOOGLE_API_KEY)

def safe_base_path(user_path):
    p = Path(user_path)
    if p.parent == p.root:
        p = p / "PlaywrightSetupAgent"
    return p

def setup_python_playwright(base_path, stream=False):
    """
    Setup Python Playwright with full reporting and artifacts:
    - Install Playwright
    - Install Chromium
    - Create example test with screenshot, trace, report
    """
    def log(msg, type_="info"):
        entry = {"message": msg, "type": type_}
        if stream:
            yield entry
        else:
            print(msg)

    Path(base_path).mkdir(parents=True, exist_ok=True)
    Path(base_path, "tests").mkdir(exist_ok=True)
    Path(base_path, "screenshots").mkdir(exist_ok=True)
    Path(base_path, "reports").mkdir(exist_ok=True)

    if stream: yield {"message": "Base folders created", "type": "info"}

    # Install Python Playwright and Chromium
    try:
        if stream: yield {"message": "Installing Python Playwright + Chromium...", "type": "info"}
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"], stdout=subprocess.DEVNULL)
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"], stdout=subprocess.DEVNULL)
        if stream: yield {"message": "Python Playwright and Chromium installed", "type": "success"}
    except Exception as e:
        if stream: yield {"message": f"Python Playwright setup failed: {str(e)}", "type": "error"}

    # Example test
    try:
        test_file = Path(base_path, "tests", "example_test.py")
        if not test_file.exists():
            test_file.write_text(f"""
from playwright.sync_api import sync_playwright
import pytest

def test_basic():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto("https://playwright.dev/")
            assert "Playwright" in page.title()
        except Exception as e:
            page.screenshot(path="{base_path}/screenshots/error.png")
            raise e
        finally:
            browser.close()
""")
            if stream: yield {"message": f"Example Python test created: {test_file}", "type": "success"}
    except Exception as e:
        if stream: yield {"message": f"Failed to create example test: {str(e)}", "type": "error"}

    # Create pytest.ini for reporting & artifacts
    try:
        pytest_ini = Path(base_path, "pytest.ini")
        if not pytest_ini.exists():
            pytest_ini.write_text(f"""
[pytest]
addopts = --html={base_path}/reports/report.html --self-contained-html --capture=sys --tb=short
""")
            if stream: yield {"message": f"pytest.ini created for HTML report: {pytest_ini}", "type": "success"}
    except Exception as e:
        if stream: yield {"message": f"Failed to create pytest.ini: {str(e)}", "type": "error"}

    if stream: yield {"message": "Python Playwright auto-setup complete!", "type": "success"}


# ------------------------
# TypedDict for LangGraph state
# ------------------------
class TestGenState(TypedDict):
    project_url: str
    test_cases: List[Dict]
    generated_scripts: List[str]

# ------------------------
# Node 1: Parse input
# ------------------------
def parse_input(state: TestGenState) -> TestGenState:
    parsed = []
    for case in state["test_cases"]:
        if isinstance(case, dict):
            parsed.append({
                "scenario": case.get("Scenario", ""),
                "description": case.get("Scenario Description", ""),
                "steps": case.get("Steps to Execute", ""),
                "expected": case.get("Expected Result", "")
            })
        elif isinstance(case, list):
            # Handle list-of-lists (assume order: scenario, description, steps, expected)
            if len(case) >= 4:
                parsed.append({
                    "scenario": str(case[0]) if len(case) > 0 else "",
                    "description": str(case[1]) if len(case) > 1 else "",
                    "steps": str(case[2]) if len(case) > 2 else "",
                    "expected": str(case[3]) if len(case) > 3 else ""
                })
            else:
                print(f"Warning: Skipping short list case: {case}")  # Or raise error if preferred
        else:
            print(f"Warning: Skipping invalid case type: {type(case)}")  # Or raise error if preferred
    state["test_cases"] = parsed
    return state

# ------------------------
# Node 2: Generate scripts
# ------------------------
def generate_script_node(state: TestGenState) -> TestGenState:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",  # Confirm model name; may be "gemini-1.5-flash" if 2.5 is unavailable
        temperature=0.3,
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    scripts = []
    for case in state["test_cases"]:
        prompt = f"""
Generate a Python Playwright test using sync API for the following test case.
Project URL: {state['project_url']}
Scenario: {case['scenario']}
Description: {case['description']}
Steps: {case['steps']}
Expected Result: {case['expected']}

Requirements:
- Use Playwright Python (sync API)
- Include navigation to the project URL
- Implement step-by-step actions and assertions
- Include error handling
- Return a complete Python test function
"""
        response = llm.invoke(prompt)
        scripts.append(response.content if hasattr(response, "content") else str(response))

    state["generated_scripts"] = scripts
    return state

# ------------------------
# Node 3: Format output
# ------------------------
def format_output(state: TestGenState) -> TestGenState:
    combined = "\n\n" + ("#" * 80 + "\n\n").join(state["generated_scripts"])
    state["final_output"] = combined
    return state

# ------------------------
# Build LangGraph workflow
# ------------------------
def build_langgraph_agent() -> CompiledStateGraph:
    workflow = StateGraph(TestGenState)
    workflow.add_node("parse_input", parse_input)
    workflow.add_node("generate_script", generate_script_node)
    workflow.add_node("format_output", format_output)
    workflow.set_entry_point("parse_input")
    workflow.add_edge("parse_input", "generate_script")
    workflow.add_edge("generate_script", "format_output")
    workflow.add_edge("format_output", END)
    return workflow.compile()

# ------------------------
# Callable generator
# ------------------------
def run_playwright_generator(test_cases: List[Dict], project_url: str) -> str:
    graph = build_langgraph_agent()
    state: TestGenState = {
        "project_url": project_url,
        "test_cases": test_cases,
        "generated_scripts": []
    }
    result = graph.invoke(state)
    return result.get("final_output", "")

# ------------------------
# Load CSV/Excel
# ------------------------
def load_test_cases(file_path: str) -> List[Dict]:
    if file_path.endswith(".csv"):
        df = pd.read_csv(file_path)
    elif file_path.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file_path)
    else:
        raise ValueError("File must be CSV or Excel")

    # Ensure proper headers
    df = df.rename(columns={
        "Scenario": "Scenario",
        "Scenario Description": "Scenario Description",
        "Steps to Execute": "Steps to Execute",
        "Expected Result": "Expected Result"
    })
    return df.to_dict(orient="records")  # ✅ list of dicts