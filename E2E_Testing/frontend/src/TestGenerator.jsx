import React, { useState } from "react";
import { FileCode, Globe, Play, Download, Loader2, CheckCircle2, Copy, AlertCircle } from "lucide-react";

export default function TestGenerator() {
  const [file, setFile] = useState(null);
  const [projectUrl, setProjectUrl] = useState("");
  const [output, setOutput] = useState("");
  const [runCommand, setRunCommand] = useState("");
  const [loading, setLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [copySuccess, setCopySuccess] = useState(false);
  const [dockerRunning, setDockerRunning] = useState(false);
  const [dockerOutput, setDockerOutput] = useState("");
  const [dockerResults, setDockerResults] = useState(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleGenerate = async () => {
    if (!file || !projectUrl) return;
    setLoading(true);
    setOutput("");
    setRunCommand("");

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("project_url", projectUrl);

      const res = await fetch("http://localhost:8000/parse_input", {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      const script = data.script || "";
      setOutput(script);

      const cmd = `pytest --headed --browser chromium`;
      setRunCommand(cmd);

    } catch (err) {
      setOutput("Error: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([output], { type: "text/python" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "test_script.py";
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(runCommand);
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2000);
  };

  const handleRunWithDocker = async () => {
    if (!output) {
      alert("Please generate a test script first");
      return;
    }

    setDockerRunning(true);
    setDockerOutput("");
    setDockerResults(null);

    try {
      const response = await fetch("http://localhost:8000/run_docker_tests", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          test_script: output,
          project_url: projectUrl
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullOutput = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              fullOutput += data.message + "\n";
              setDockerOutput(fullOutput);
              
              if (data.type === 'result') {
                setDockerResults(data.result);
              }
            } catch (e) {
              fullOutput += line + "\n";
              setDockerOutput(fullOutput);
            }
          }
        }
      }
    } catch (err) {
      setDockerOutput("Error running Docker tests: " + err.message);
      console.error(err);
    } finally {
      setDockerRunning(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      <div className="max-w-6xl mx-auto p-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="bg-indigo-500 p-2 rounded-lg">
              <FileCode className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-white">Playwright Test Generator</h1>
          </div>
          <p className="text-slate-400 ml-14">Generate automated test scripts from your CSV or Excel files</p>
        </div>

        {/* Main Card */}
        <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl shadow-2xl border border-slate-700/50 p-8">
          {/* File Upload Section */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-slate-300 mb-3">
              Test Data File
            </label>
            <div
              className={`relative border-2 border-dashed rounded-xl p-8 transition-all ${
                dragActive
                  ? "border-indigo-400 bg-indigo-500/10"
                  : "border-slate-600 hover:border-slate-500"
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={e => setFile(e.target.files[0])}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                id="file-upload"
              />
              <div className="text-center">
                {file ? (
                  <div className="flex items-center justify-center gap-3">
                    <CheckCircle2 className="w-8 h-8 text-green-400" />
                    <div className="text-left">
                      <p className="text-white font-medium">{file.name}</p>
                      <p className="text-slate-400 text-sm">{(file.size / 1024).toFixed(2)} KB</p>
                    </div>
                  </div>
                ) : (
                  <>
                    <FileCode className="w-12 h-12 text-slate-500 mx-auto mb-3" />
                    <p className="text-slate-300 mb-1">
                      Drag and drop your file here, or click to browse
                    </p>
                    <p className="text-slate-500 text-sm">Supports CSV, XLSX, and XLS files</p>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Project URL Section */}
          <div className="mb-8">
            <label className="block text-sm font-medium text-slate-300 mb-3">
              Project URL
            </label>
            <div className="relative">
              <Globe className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
              <input
                type="text"
                placeholder="https://example.com"
                value={projectUrl}
                onChange={e => setProjectUrl(e.target.value)}
                className="w-full bg-slate-700/50 border border-slate-600 rounded-xl py-3 pl-12 pr-4 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
              />
            </div>
          </div>

          {/* Generate Button */}
          <button
            onClick={handleGenerate}
            disabled={loading || !file || !projectUrl}
            className="w-full bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 disabled:from-slate-600 disabled:to-slate-600 text-white font-semibold py-4 rounded-xl transition-all duration-200 flex items-center justify-center gap-2 shadow-lg disabled:cursor-not-allowed"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Generating Test Script...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                Generate Test Script
              </>
            )}
          </button>
        </div>

        {/* Output Section */}
        {output && (
          <div className="mt-8 space-y-6">
            {/* Generated Script */}
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl shadow-2xl border border-slate-700/50 overflow-hidden">
              <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700/50">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <FileCode className="w-5 h-5 text-indigo-400" />
                  Generated Python Test Script
                </h2>
                 <div className="flex gap-2">
                   <button
                     onClick={handleDownload}
                     className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg transition-all"
                   >
                     <Download className="w-4 h-4" />
                     Download
                   </button>
                   <button
                     onClick={handleRunWithDocker}
                     disabled={dockerRunning}
                     className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 text-white px-4 py-2 rounded-lg transition-all"
                   >
                     {dockerRunning ? (
                       <>
                         <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                         Running...
                       </>
                     ) : (
                       <>
                         <Play className="w-4 h-4" />
                         Run with Docker
                       </>
                     )}
                   </button>
                 </div>
              </div>
              <pre className="bg-slate-900/50 p-6 overflow-auto text-sm text-slate-300 font-mono max-h-96">
                {output}
              </pre>
            </div>

            {/* Run Command */}
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl shadow-2xl border border-slate-700/50 p-6">
              <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Play className="w-5 h-5 text-green-400" />
                Run Command
              </h2>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={runCommand}
                  readOnly
                  className="flex-1 bg-slate-900/50 border border-slate-700 rounded-lg px-4 py-3 text-white font-mono text-sm focus:outline-none"
                />
                <button
                  onClick={copyToClipboard}
                  className={`flex items-center gap-2 px-6 py-3 rounded-lg transition-all font-medium ${
                    copySuccess
                      ? "bg-green-600 hover:bg-green-500"
                      : "bg-indigo-600 hover:bg-indigo-500"
                  } text-white`}
                >
                  {copySuccess ? (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="w-4 h-4" />
                      Copy
                    </>
                  )}
                </button>
              </div>
            </div>
           </div>
         )}

         {/* Docker Results Section */}
         {(dockerOutput || dockerResults) && (
           <div className="mt-8 bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-2xl overflow-hidden">
             <div className="p-6 border-b border-slate-700/50">
               <h2 className="text-xl font-semibold flex items-center gap-2 text-white">
                 <Play className="w-5 h-5 text-blue-400" />
                 Docker Test Execution
               </h2>
             </div>
             
             <div className="p-6">
               {dockerRunning && (
                 <div className="mb-6 flex items-center justify-center">
                   <div className="text-center">
                     <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                     <p className="text-gray-400">Running tests in Docker container...</p>
                   </div>
                 </div>
               )}

               {dockerOutput && (
                 <div className="mb-6">
                   <h3 className="text-lg font-semibold mb-3 text-gray-300">Execution Logs</h3>
                   <div className="bg-slate-900/50 rounded-xl border border-slate-700/50 p-4 max-h-64 overflow-auto custom-scrollbar">
                     <pre className="text-sm text-gray-300 leading-relaxed font-mono whitespace-pre-wrap">
                       {dockerOutput}
                     </pre>
                   </div>
                 </div>
               )}

               {dockerResults && (
                 <div>
                   <h3 className="text-lg font-semibold mb-3 text-gray-300">Test Results</h3>
                   <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                     <div className="bg-slate-900/50 rounded-xl border border-slate-700/50 p-4">
                       <div className="flex items-center gap-2 mb-2">
                         <CheckCircle2 className="w-5 h-5 text-green-400" />
                         <span className="font-semibold text-green-400">Tests Passed</span>
                       </div>
                       <p className="text-2xl font-bold text-green-400">{dockerResults.passed || 0}</p>
                     </div>
                     <div className="bg-slate-900/50 rounded-xl border border-slate-700/50 p-4">
                       <div className="flex items-center gap-2 mb-2">
                         <AlertCircle className="w-5 h-5 text-red-400" />
                         <span className="font-semibold text-red-400">Tests Failed</span>
                       </div>
                       <p className="text-2xl font-bold text-red-400">{dockerResults.failed || 0}</p>
                     </div>
                     <div className="bg-slate-900/50 rounded-xl border border-slate-700/50 p-4">
                       <div className="flex items-center gap-2 mb-2">
                         <FileCode className="w-5 h-5 text-blue-400" />
                         <span className="font-semibold text-blue-400">Total Tests</span>
                       </div>
                       <p className="text-2xl font-bold text-blue-400">{dockerResults.total || 0}</p>
                     </div>
                   </div>
                   
                   {dockerResults.reportUrl && (
                     <div className="mt-4">
                       <a
                         href={dockerResults.reportUrl}
                         target="_blank"
                         rel="noopener noreferrer"
                         className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors text-white"
                       >
                         <Download className="w-4 h-4" />
                         View Full Report
                       </a>
                     </div>
                   )}
                 </div>
               )}
             </div>
           </div>
         )}
       </div>

       <style>{`
         .custom-scrollbar::-webkit-scrollbar {
           width: 8px;
           height: 8px;
         }
         .custom-scrollbar::-webkit-scrollbar-track {
           background: rgba(51, 65, 85, 0.3);
           border-radius: 4px;
         }
         .custom-scrollbar::-webkit-scrollbar-thumb {
           background: rgba(99, 102, 241, 0.5);
           border-radius: 4px;
         }
         .custom-scrollbar::-webkit-scrollbar-thumb:hover {
           background: rgba(99, 102, 241, 0.7);
         }
       `}</style>
     </div>
   );
}