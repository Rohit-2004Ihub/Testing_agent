from fastapi import FastAPI, Query, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware 
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
import pandas as pd
from E2E_Agent import setup_python_playwright, safe_base_path
from E2E_Agent import run_playwright_generator
import subprocess
import os
import tempfile
import shutil
import uuid
import time
from typing import Dict, Any
from pathlib import Path

app = FastAPI()

# Persistent artifacts directory to serve real reports/screenshots/videos
ARTIFACTS_ROOT = Path.cwd() / "artifacts"
ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)

# Serve artifacts statically
app.mount("/artifacts", StaticFiles(directory=str(ARTIFACTS_ROOT)), name="artifacts")

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


@app.post("/run_docker_tests")
async def run_docker_tests(request_data: Dict[str, Any]):
    """
    Run Playwright tests in Docker container with streaming output.
    """
    try:
        test_script = request_data.get("test_script")
        project_url = request_data.get("project_url")
        
        if not test_script or not project_url:
            return JSONResponse(status_code=400, content={"error": "Missing test_script or project_url"})

        # Create a unique directory for this test run in persistent artifacts folder
        test_run_id = str(uuid.uuid4())[:8]
        base_dir = ARTIFACTS_ROOT / test_run_id
        base_dir.mkdir(parents=True, exist_ok=True)

        def event_stream():
            try:
                # Send initial message
                yield f"data: {json.dumps({'message': '[INFO] Setting up Docker environment...', 'type': 'log'})}\n\n"
                
                # Create Docker files
                dockerfile_content = create_dockerfile(test_run_id)
                run_tests_content = create_run_tests_script()
                requirements_content = create_requirements()
                
                # Write files
                (base_dir / "Dockerfile").write_text(dockerfile_content)
                (base_dir / "run_tests.py").write_text(run_tests_content)
                (base_dir / "requirements.txt").write_text(requirements_content)
                
                # Create tests directory and write test script
                tests_dir = base_dir / "tests"
                tests_dir.mkdir(exist_ok=True)
                # Sanitize script for Docker: force headless=True and route localhost to host.docker.internal
                import re as _re
                script_sanitized = test_script
                # 1) Direct replacement of explicit headless=False
                script_sanitized = script_sanitized.replace("headless=False", "headless=True")
                # 1b) Replace localhost URLs to reach host service from container
                script_sanitized = script_sanitized.replace("http://localhost:", "http://host.docker.internal:")
                # 2) Inject headless=True for launches without headless param
                def _inject_headless(match):
                    inside = match.group(1)
                    if "headless" in inside:
                        return f"p.chromium.launch({inside})"
                    inside_clean = inside.strip()
                    if inside_clean == "":
                        return "p.chromium.launch(headless=True)"
                    return f"p.chromium.launch(headless=True, {inside})"
                script_sanitized = _re.sub(r"p\\.chromium\\.launch\\(([^)]*)\\)", _inject_headless, script_sanitized)

                # 3) Add smart helpers and rewrite page.fill(...) to robust smart_fill(...)
                SMART_HELPERS = '''
from typing import List

def smart_wait(page, selectors: List[str], timeout_ms: int = 10000):
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=timeout_ms, state="visible")
            return sel
        except Exception:
            continue
    raise TimeoutError(f"None of the selectors appeared: {selectors}")

def smart_fill(page, selectors: List[str], value: str, timeout_ms: int = 10000):
    chosen = smart_wait(page, selectors, timeout_ms)
    page.fill(chosen, value)
'''

                def _rewrite_fill(match):
                    sel_raw = match.group(1)
                    val_raw = match.group(2)
                    sel_lc = sel_raw.lower()
                    candidates = [sel_raw]
                    # Heuristics: add common alternatives
                    if 'email' in sel_lc:
                        candidates.extend(["'input[type=\\'email\\']'", "'[name*=" + '"email"' + " i]'", '"[name*=\\"email\\" i]"'])
                    if 'roll' in sel_lc:
                        candidates.extend(["'[name*=" + '"roll"' + " i]'", '"[name*=\\"roll\\" i]"'])
                    # Remove duplicates while preserving order
                    seen = set()
                    uniq = []
                    for c in candidates:
                        if c not in seen:
                            uniq.append(c)
                            seen.add(c)
                    arr = ", ".join(uniq)
                    return f"smart_fill(page, [{arr}], {val_raw})"

                # Rewrite simple page.fill('selector', 'value') patterns
                script_sanitized = _re.sub(r"page\\.fill\\(([^,]+),\\s*([^\)]+)\\)", _rewrite_fill, script_sanitized)

                # 4) Inject video recording and tracing helpers and instrumentation
                PREFIX_RUNTIME = """
from pathlib import Path
VIDEOS_DIR = Path('/app/videos')
REPORTS_DIR = Path('/app/reports')
"""

                # Ensure browser.new_context() records video
                def _inject_video_ctx(match):
                    inside = match.group(1)
                    if 'record_video_dir' in inside:
                        return f"browser.new_context({inside})"
                    inside_clean = inside.strip()
                    if inside_clean == "":
                        return "browser.new_context(record_video_dir=VIDEOS_DIR)"
                    return f"browser.new_context(record_video_dir=VIDEOS_DIR, {inside})"
                script_sanitized = _re.sub(r"browser\\.new_context\\(([^)]*)\\)", _inject_video_ctx, script_sanitized)

                # Add trace_path per test function header
                def _add_trace_path(match):
                    func_name = match.group(1)
                    return f"def {func_name}():\n    trace_path = REPORTS_DIR / '{func_name}_trace.zip'"
                script_sanitized = _re.sub(r"def\\s+(test_[a-zA-Z0-9_]+)\\s*\\(\\):", _add_trace_path, script_sanitized)

                # Start tracing after page creation
                script_sanitized = _re.sub(
                    r"(page\\s*=\\s*context\\.new_page\\(\\))",
                    r"\1\n        context.tracing.start(screenshots=True, snapshots=True, sources=True)",
                    script_sanitized
                )

                # Stop tracing in finally before browser.close
                script_sanitized = _re.sub(
                    r"(finally:\s*\n\s*)(browser\\.close\\\(\\\))",
                    r"\1try:\n            context.tracing.stop(path=str(trace_path))\n        except Exception:\n            pass\n        \2",
                    script_sanitized
                )

                # Prepend helpers once
                script_sanitized = SMART_HELPERS + "\n" + PREFIX_RUNTIME + "\n" + script_sanitized

                (tests_dir / "test_generated.py").write_text(script_sanitized)
                
                yield f"data: {json.dumps({'message': '[INFO] Docker files created successfully', 'type': 'log'})}\n\n"
                
                # Create directories for reports
                reports_dir = base_dir / "reports"
                screenshots_dir = base_dir / "screenshots"
                videos_dir = base_dir / "videos"
                
                for dir_path in [reports_dir, screenshots_dir, videos_dir]:
                    dir_path.mkdir(exist_ok=True)
                
                yield f"data: {json.dumps({'message': '[INFO] Building Docker image...', 'type': 'log'})}\n\n"
                
                # Build Docker image with robust fallbacks (avoid buildx-injected wrappers)
                build_cmds = [
                    ["docker", "image", "build", str(base_dir)],
                    ["docker", "build", str(base_dir)],
                ]
                build_result = None
                chosen_cmd = None
                for cmd in build_cmds:
                    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(base_dir))
                    if result.returncode == 0:
                        build_result = result
                        chosen_cmd = " ".join(cmd)
                        break
                if build_result is None:
                    # Emit the last stderr for debugging
                    last_err = result.stderr if 'result' in locals() else 'unknown error'
                    yield f"data: {json.dumps({'message': f'[ERROR] Docker build failed: {last_err}', 'type': 'error'})}\n\n"
                    return
                else:
                    yield f"data: {json.dumps({'message': f'[INFO] Docker build command used: {chosen_cmd}', 'type': 'log'})}\n\n"
                
                # Resolve image id by label set in Dockerfile
                inspect_result = subprocess.run(
                    ["docker", "images", "--filter", f"label=playwright_test_run={test_run_id}", "-q"],
                    capture_output=True,
                    text=True,
                    cwd=str(base_dir)
                )
                image_id = (inspect_result.stdout or "").strip().splitlines()[0] if (inspect_result.stdout or "").strip() else ""
                if not image_id:
                    yield f"data: {json.dumps({'message': '[ERROR] Could not resolve image id by label', 'type': 'error'})}\n\n"
                    return
                
                yield f"data: {json.dumps({'message': f'[SUCCESS] Docker image built successfully: {image_id}', 'type': 'log'})}\n\n"
                yield f"data: {json.dumps({'message': '[INFO] Running tests in Docker container...', 'type': 'log'})}\n\n"
                
                # Run Docker container
                run_result = subprocess.run([
                    "docker", "run", "--rm",
                    # Make host.docker.internal resolvable on Linux
                    "--add-host", "host.docker.internal:host-gateway",
                    "-v", f"{reports_dir}:/app/reports",
                    "-v", f"{screenshots_dir}:/app/screenshots", 
                    "-v", f"{videos_dir}:/app/videos",
                    image_id
                ], capture_output=True, text=True, cwd=str(base_dir))
                
                # Send container output
                if run_result.stdout:
                    for line in run_result.stdout.split('\n'):
                        if line.strip():
                            yield f"data: {json.dumps({'message': line, 'type': 'log'})}\n\n"
                
                if run_result.stderr:
                    for line in run_result.stderr.split('\n'):
                        if line.strip():
                            yield f"data: {json.dumps({'message': f'[WARNING] {line}', 'type': 'warning'})}\n\n"
                
                # Parse test results
                results = parse_test_results(reports_dir)
                results['reportUrl'] = f"http://localhost:8000/artifacts/{test_run_id}/reports/report.html"
                results['screenshotsUrl'] = f"http://localhost:8000/artifacts/{test_run_id}/screenshots/"
                results['videosUrl'] = f"http://localhost:8000/artifacts/{test_run_id}/videos/"
                
                yield f"data: {json.dumps({'message': '[SUCCESS] Test execution completed!', 'type': 'log'})}\n\n"
                yield f"data: {json.dumps({'message': f'[INFO] Results: {results["passed"]} passed, {results["failed"]} failed', 'type': 'log'})}\n\n"
                yield f"data: {json.dumps({'type': 'result', 'result': results})}\n\n"
                
                # Keep Docker image for inspection; do not remove
                
            except Exception as e:
                yield f"data: {json.dumps({'message': f'[ERROR] Error: {str(e)}', 'type': 'error'})}\n\n"
            finally:
                # Keep artifacts for viewing; no deletion here
                pass

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


def create_dockerfile(test_run_id: str) -> str:
    """Create Dockerfile content with a unique label to resolve image id."""
    return f"""FROM python:3.12-bullseye

WORKDIR /app

# Install system dependencies required by Playwright
RUN apt-get update && apt-get install -y \\
    libnss3 \\
    libatk1.0-0 \\
    libatk-bridge2.0-0 \\
    libcups2 \\
    libdrm2 \\
    libxkbcommon0 \\
    libxcomposite1 \\
    libxdamage1 \\
    libxrandr2 \\
    libgbm1 \\
    libasound2 \\
    libpangocairo-1.0-0 \\
    libpango-1.0-0 \\
    libgtk-3-0 \\
    fonts-liberation \\
    wget \\
    curl \\
    unzip \\
    ca-certificates \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN python -m playwright install chromium

# Copy test runner and test scripts
COPY run_tests.py .
COPY tests/ /app/tests/

ENV BASE_PATH=/app

# Label image so we can find it without tags
LABEL playwright_test_run={test_run_id}

CMD ["python", "run_tests.py"]"""


def create_run_tests_script() -> str:
    """Create run_tests.py content."""
    return '''import subprocess
import sys
from pathlib import Path
import os
import pytest
from pytest_html import extras

# Base path inside container
BASE_PATH = Path("/app")

# Define directories
TESTS_DIR = BASE_PATH / "tests"
REPORTS_DIR = BASE_PATH / "reports"
SCREENSHOTS_DIR = BASE_PATH / "screenshots"
VIDEOS_DIR = BASE_PATH / "videos"

# Create directories if they don't exist
for d in [TESTS_DIR, REPORTS_DIR, SCREENSHOTS_DIR, VIDEOS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Write a conftest.py to embed screenshots into pytest-html report even without fixtures
conftest_path = TESTS_DIR / "conftest.py"
conftest_path.write_text("""
import os
from pathlib import Path
import pytest

BASE_PATH = Path('/app')
SCREENSHOTS_DIR = BASE_PATH / 'screenshots'
VIDEOS_DIR = BASE_PATH / 'videos'

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    pytest_html = item.config.pluginmanager.getplugin('html')
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call':
        extras_list = getattr(rep, 'extra', [])
        # Preferred: {item.name}.png created by tests
        named_png = SCREENSHOTS_DIR / f"{item.name}.png"
        # Fallbacks used by generated tests
        fallback_candidates = [
            SCREENSHOTS_DIR / "screenshot_on_failure.png",
            SCREENSHOTS_DIR / "failure_screenshot.png",
            BASE_PATH / "screenshot_on_failure.png",
            BASE_PATH / "failure_screenshot.png",
        ]
        # Attach preferred screenshot if present
        if named_png.exists():
            extras_list.append(pytest_html.extras.image(str(named_png), 'Screenshot'))
        else:
            for candidate in fallback_candidates:
                if candidate.exists():
                    extras_list.append(pytest_html.extras.image(str(candidate), 'Screenshot'))
                    break
        # Try to attach a video link if exists at known locations
        named_video = VIDEOS_DIR / f"{item.name}.webm"
        if named_video.exists():
            extras_list.append(pytest_html.extras.url(str(named_video), 'Video'))
        rep.extra = extras_list
""")

# Custom pytest hook for reports (runs in the pytest process)
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    pytest_html = item.config.pluginmanager.getplugin("html")
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call":
        # Get page from fixture if available
        page = item.funcargs.get('page', None)
        if page:
            screenshot_path = SCREENSHOTS_DIR / f"{item.name}.png"
            try:
                page.screenshot(path=str(screenshot_path))
            except Exception:
                pass
            # For video, Playwright saves it automatically; find the path
            video_path = page.video.path() if page.video else None
            extra = getattr(rep, "extra", [])
            if screenshot_path.exists():
                extra.append(extras.image(str(screenshot_path), "Screenshot"))
            if video_path and Path(video_path).exists():
                extra.append(extras.url(str(video_path), "Video"))
            rep.extra = extra

# Create pytest.ini for HTML report
pytest_ini = BASE_PATH / "pytest.ini"
pytest_ini.write_text(f"""
[pytest]
addopts = --html={REPORTS_DIR}/report.html --self-contained-html --capture=sys --tb=short
""")

# Run pytest with JSON report for machine-readable results
print("[INFO] Running Playwright tests...")
json_report_path = REPORTS_DIR / "report.json"

# Ensure screenshots directory is on PATH for tests saving to CWD
os.chdir(BASE_PATH)

subprocess.run([
    sys.executable, "-m", "pytest", str(TESTS_DIR),
    "--json-report", f"--json-report-file={json_report_path}"
], check=False)

# Debug: List files in directories
print("\\nDebug: Files in reports:", os.listdir(str(REPORTS_DIR)))
print("Debug: Files in screenshots:", os.listdir(str(SCREENSHOTS_DIR)))
print("Debug: Files in videos:", os.listdir(str(VIDEOS_DIR)))

print(f"[SUCCESS] Test execution complete. View report at: {REPORTS_DIR}/report.html")'''


def create_requirements() -> str:
    """Create requirements.txt content."""
    return """playwright==1.55.0
pytest==8.3.3
pytest-html==4.1.1
pytest-base-url==2.1.0
pytest-metadata==3.1.1
pytest-xdist==3.5.0
pytest-timeout==2.3.1
pytest-json-report==1.5.0
requests==2.32.3"""


def parse_test_results(reports_dir: Path) -> Dict[str, Any]:
    """Parse real test results from the JSON report if present; fallback to 0s."""
    try:
        json_path = reports_dir / "report.json"
        if json_path.exists():
            import json as _json
            with open(json_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            tests = data.get("tests", [])
            total = len(tests)
            failed = sum(1 for t in tests if t.get("outcome") == "failed")
            passed = sum(1 for t in tests if t.get("outcome") == "passed")
            return {"passed": passed, "failed": failed, "total": total}
        # Fallback: no JSON report yet
        return {"passed": 0, "failed": 0, "total": 0}
    except Exception:
        return {"passed": 0, "failed": 0, "total": 0}


@app.get("/reports/{test_run_id}/report.html")
async def get_test_report(test_run_id: str):
    """Backward-compat: redirect to static artifacts URL for the report."""
    try:
        url = f"/artifacts/{test_run_id}/reports/report.html"
        html = f"""
        <html><head><meta http-equiv="refresh" content="0; url={url}"></head>
        <body>Redirecting to <a href="{url}">{url}</a>...</body></html>
        """
        return HTMLResponse(content=html)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
