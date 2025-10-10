import subprocess
import sys
from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv
import pandas as pd
from fastapi.responses import StreamingResponse, JSONResponse
import json
import pandas as pd
from typing import TypedDict, List, Dict
from langgraph.graph import StateGraph, END


load_dotenv()  # Load env vars (including GOOGLE_API_KEY)

def safe_base_path(user_path):
    p = Path(user_path)
    if p.parent == p.root:
        p = p / "PlaywrightSetupAgent"
    return p

def setup_python_playwright(base_path, stream=False):
    """
    Setup Python Playwright with full reporting, embedded screenshots, and video artifacts:
    - Install Playwright, Chromium
    - Install pytest and pytest-html for HTML reporting
    - Enable screenshots and video recording
    - Embed screenshots inside the HTML report under failed tests
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
    Path(base_path, "videos").mkdir(exist_ok=True)
    Path(base_path, "reports").mkdir(exist_ok=True)

    if stream: yield {"message": "Base folders created", "type": "info"}

    # Install dependencies
    try:
        if stream: yield {"message": "Installing Playwright + Chromium + pytest + pytest-html...", "type": "info"}
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "pytest", "pytest-html"], stdout=subprocess.DEVNULL)
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"], stdout=subprocess.DEVNULL)
        if stream: yield {"message": "Dependencies installed", "type": "success"}
    except Exception as e:
        if stream: yield {"message": f"Setup failed: {str(e)}", "type": "error"}

    # Example test with embedded screenshot & video
    try:
        test_file = Path(base_path, "tests", "example_test.py")
        if not test_file.exists():
            test_file.write_text(f"""
from playwright.sync_api import sync_playwright
import pytest
import os

BASE_PATH = r"{base_path}"
SCREENSHOTS_DIR = os.path.join(BASE_PATH, "screenshots")
VIDEOS_DIR = os.path.join(BASE_PATH, "videos")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(VIDEOS_DIR, exist_ok=True)

# Hook to attach screenshots/videos inside pytest-html report
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        screenshot_path = os.path.join(SCREENSHOTS_DIR, f"{{item.name}}.png")
        video_path = os.path.join(VIDEOS_DIR, f"{{item.name}}.webm")
        # Embed screenshot directly in HTML
        if os.path.exists(screenshot_path):
            extra = getattr(rep, "extra", [])
            extra.append(pytest_html.extras.image(screenshot_path, "Screenshot"))
            rep.extra = extra
        # Provide clickable video link
        if os.path.exists(video_path):
            extra = getattr(rep, "extra", [])
            extra.append(pytest_html.extras.url(video_path, "Video"))
            rep.extra = extra

def test_basic():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(record_video_dir=VIDEOS_DIR)
        page = context.new_page()
        try:
            page.goto("https://playwright.dev/")
            assert "Playwright" in page.title()
        except Exception as e:
            screenshot_path = os.path.join(SCREENSHOTS_DIR, "test_basic.png")
            page.screenshot(path=screenshot_path)
            raise e
        finally:
            browser.close()
""")
            if stream: yield {"message": f"Example test created: {test_file}", "type": "success"}
    except Exception as e:
        if stream: yield {"message": f"Failed to create example test: {str(e)}", "type": "error"}

    # Create pytest.ini for HTML report
    try:
        pytest_ini = Path(base_path, "pytest.ini")
        if not pytest_ini.exists():
            pytest_ini.write_text(f"""
[pytest]
addopts = --html={base_path}/reports/report.html --self-contained-html --capture=sys --tb=short
""")
            if stream: yield {"message": f"pytest.ini created: {pytest_ini}", "type": "success"}
    except Exception as e:
        if stream: yield {"message": f"Failed to create pytest.ini: {str(e)}", "type": "error"}

    if stream: yield {"message": "Python Playwright auto-setup complete! Screenshots embedded inside HTML report.", "type": "success"}


import os
from typing import List, Dict, TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END

# ------------------------
# TypedDict for workflow state
# ------------------------
class TestGenState(TypedDict):
    project_url: str
    test_cases: List[Dict]
    generated_scripts: List[str]
    final_output: str

# ------------------------
# Node 1: Parse Input
# ------------------------
def parse_input(state: TestGenState) -> TestGenState:
    """
    Extract only relevant columns: Scenario, Description, Steps, Test Data, Expected Result
    """
    parsed = []
    for case in state["test_cases"]:
        parsed.append({
            "scenario": str(case.get("Scenario", "")).strip(),
            "description": str(case.get("Scenario Description", "")).strip(),
            "steps": str(case.get("Steps to Execute", "")).strip(),
            "test_data": case.get("Test Data", {}),
            "expected": str(case.get("Expected Result", "")).strip(),
        })
    state["test_cases"] = parsed
    return state

# ------------------------
# Node 2: Generate Playwright Script
# ------------------------
def generate_script_node(state: TestGenState) -> TestGenState:
    """
    Generate minimal, runnable Playwright Python scripts from test case steps and test data.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY is missing. Set it in your .env file")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.2,
        google_api_key=api_key
    )

    scripts = []
    for idx, case in enumerate(state["test_cases"], start=1):
        prompt = f"""
You are a QA engineer. Generate a **minimal, runnable Python Playwright script** using sync API for pytest.

Project URL: {state['project_url']}
Scenario: {case['scenario']}
Description: {case['description']}
Steps to Execute: {case['steps']}
Test Data: {case['test_data']}
Expected Result: {case['expected']}

Instructions:
1. Launch Chromium (headless=False) and navigate to Project URL once.
2. Map steps literally:
   - "fill <field>": fill input with value from Test Data
   - "click <button>": click the button
   - "select <dropdown>": select value from Test Data
   - "check <checkbox>": check it
3. Include try/except/finally:
   - Take screenshot on failure: test_case_{idx}_failure.png
   - Close browser in finally
   - Call pytest.fail() on exception
4. Assert expected result if applicable (URL change or visible element)
5. Name function test_case_{idx}
6. Output only Python code, no markdown or explanations.
"""

        try:
            response = llm.invoke(prompt)
            # Extract content
            if hasattr(response, "content"):
                resp_text = response.content
            elif isinstance(response, dict) and "output_text" in response:
                resp_text = response["output_text"]
            else:
                resp_text = str(response)

            # Clean output
            resp_text = resp_text.strip().replace("```python", "").replace("```", "")
            if not resp_text:
                resp_text = f"import pytest\n\ndef test_case_{idx}():\n    pass"

            scripts.append(resp_text)

        except Exception as e:
            scripts.append(f"import pytest\n\ndef test_case_{idx}():\n    pytest.fail('Error generating script: {e}')")

    state["generated_scripts"] = scripts
    return state

# ------------------------
# Node 3: Format Output
# ------------------------
def format_output(state: TestGenState) -> TestGenState:
    """
    Combine all generated scripts into a single output string
    """
    combined = "\n\n" + ("#" * 80 + "\n\n").join(state["generated_scripts"])
    state["final_output"] = combined
    return state

# ------------------------
# Build LangGraph Agent
# ------------------------
def build_langgraph_agent():
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
# Callable function
# ------------------------
def run_playwright_generator(test_cases: List[Dict], project_url: str) -> str:
    """
    Run the workflow and return combined Playwright test scripts.
    """
    graph = build_langgraph_agent()
    state: TestGenState = {
        "project_url": project_url,
        "test_cases": test_cases,
        "generated_scripts": [],
        "final_output": ""
    }
    result = graph.invoke(state)
    return result.get("final_output") or "\n\n".join(result.get("generated_scripts", []))
