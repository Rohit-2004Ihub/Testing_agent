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



from typing import List, Dict, TypedDict
import os
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI


class TestGenState(TypedDict):
    project_url: str
    test_cases: List[Dict]
    generated_scripts: List[str]


# ------------------------
# Node 1: Parse Input
# ------------------------
def parse_input(state: TestGenState) -> TestGenState:
    """
    Parse test case data including Scenario, Description, Steps, Expected Result, and Test Data.
    """
    parsed = []
    for case in state["test_cases"]:
        parsed.append({
            "scenario": case.get("Scenario", "").strip(),
            "description": case.get("Scenario Description", "").strip(),
            "steps": case.get("Steps to Execute", "").strip(),
            "expected": case.get("Expected Result", "").strip(),
            "test_data": case.get("Test Data", "").strip(),  # ✅ new column
        })
    state["test_cases"] = parsed
    return state


# ------------------------
# Node 2: Generate Script using Gemini
# ------------------------
# ------------------------
# Node 2: Generate Script using Gemini (Enhanced)
# ------------------------
def generate_script_node(state: TestGenState) -> TestGenState:
    """
    Generate clean, minimal Playwright Python (sync API) test scripts that dynamically
    handle only the UI elements mentioned in each test case.
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
        # Detect which elements are mentioned in the test steps
        steps_lower = (case["steps"] + " " + case["test_data"]).lower()
        handle_dropdown = "dropdown" in steps_lower or "select" in steps_lower
        handle_checkbox = "checkbox" in steps_lower or "policy" in steps_lower
        handle_button = "click" in steps_lower or "button" in steps_lower
        handle_input = "type" in steps_lower or "fill" in steps_lower or "input" in steps_lower

        # Construct element handling instructions dynamically
        element_handling = ""
        if handle_dropdown:
            element_handling += "- Select dropdown values using visible text only if mentioned.\n"
        if handle_checkbox:
            element_handling += "- Check only the checkboxes explicitly mentioned.\n"
        if handle_button:
            element_handling += "- Click only buttons explicitly mentioned.\n"
        if handle_input:
            element_handling += "- Fill input fields only as per Test Data.\n"

        prompt = f"""
Generate a clean, ready-to-run Python Playwright test using sync API for pytest.

Project URL: {state['project_url']}
Scenario: {case['scenario']}
Description: {case['description']}
Steps: {case['steps']}
Test Data: {case['test_data']}
Expected Result: {case['expected']}

Requirements:
- Launch Chromium in **headed mode** (headless=False)
- Name the function: test_case_{idx}
- Navigate to project URL and execute only the steps mentioned
- Dynamically handle UI elements **only if mentioned in the steps or Test Data**:
{element_handling}
- Include assertions for expected results
- Include try/except with screenshot on failure
- Keep the code minimal, concise, and ready-to-run
- Do NOT include extra print statements or redundant fallback locators
- Output Python code only, no markdown, no extra comments
"""

        try:
            response = llm.invoke(prompt)
            if hasattr(response, "content"):
                resp_text = response.content
            elif isinstance(response, dict) and "output_text" in response:
                resp_text = response["output_text"]
            else:
                resp_text = str(response)

            if not resp_text.strip():
                resp_text = f"# Failed to generate script for '{case['scenario']}'"

            scripts.append(resp_text)

        except Exception as e:
            scripts.append(f"# Error generating script for '{case['scenario']}': {e}")

    state["generated_scripts"] = scripts
    return state




# ------------------------
# Node 3: Format Output
# ------------------------
def format_output(state: TestGenState) -> TestGenState:
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
    Run the complete LangGraph workflow and return combined Playwright test scripts.
    """
    graph = build_langgraph_agent()
    state: TestGenState = {
        "project_url": project_url,
        "test_cases": test_cases,
        "generated_scripts": []
    }
    result = graph.invoke(state)

    final_output = result.get("final_output") or "\n\n".join(result.get("generated_scripts", []))
    return final_output

