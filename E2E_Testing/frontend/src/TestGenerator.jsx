import React, { useState } from "react";
import { Upload, Globe, Code, FileText, CheckCircle, Copy, Download, Sparkles } from "lucide-react";

export default function TestGenerator() {
  const [file, setFile] = useState(null);
  const [projectUrl, setProjectUrl] = useState("");
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const csvHeaders = [
    "Test Case ID",
    "Scenario",
    "Scenario Description",
    "Pre Condition",
    "Steps to Execute",
    "Expected Result",
    "Actual Result",
    "Status",
    "Executed QA Name"
  ];

  const handleGenerate = async () => {
    if (!file || !projectUrl) {
      alert("Please upload file and enter project URL");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("project_url", projectUrl);

    setLoading(true);
    setOutput("");

    try {
      const res = await fetch("http://localhost:8000/parse_input", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      setOutput(data.script);
    } catch (err) {
      alert("Error generating test script");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(output);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([output], { type: "text/python" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "test_script.py"; // Updated for Python
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    setFile(selectedFile);
  };

  const downloadSampleCSV = () => {
    const csvContent = csvHeaders.join(",") + "\n"; // only headers
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", "sample_test_cases.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-indigo-500/10 rounded-2xl mb-4 border border-indigo-500/20">
            <Sparkles className="w-8 h-8 text-indigo-400" />
          </div>
          <h1 className="text-4xl font-bold mb-3 bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
            Test Script Generator
          </h1>
          <p className="text-gray-400 text-lg">Generate Python Playwright tests from your data files</p>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Input Section */}
          <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-2xl p-8">
            <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
              <FileText className="w-5 h-5 text-indigo-400" />
              Configuration
            </h2>

            <div className="space-y-6">
              {/* Download Sample CSV */}
              <button
                onClick={downloadSampleCSV}
                className="w-full px-6 py-3 bg-green-600 hover:bg-green-700 rounded-lg font-semibold transition-all duration-200 flex items-center justify-center gap-2"
              >
                <Download className="w-5 h-5" />
                Download Sample CSV
              </button>

              {/* File Upload */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">
                  Upload Test Data
                </label>
                <div className="relative">
                  <input
                    type="file"
                    accept=".csv, .xlsx, .xls"
                    onChange={handleFileChange}
                    className="hidden"
                    id="file-upload"
                  />
                  <label
                    htmlFor="file-upload"
                    className="flex items-center justify-center gap-3 w-full px-4 py-4 bg-slate-900/50 border-2 border-dashed border-slate-600 rounded-lg cursor-pointer hover:border-indigo-500 hover:bg-slate-900/70 transition-all group"
                  >
                    <Upload className="w-5 h-5 text-gray-400 group-hover:text-indigo-400 transition-colors" />
                    <span className="text-gray-400 group-hover:text-indigo-400 transition-colors">
                      {file ? file.name : "Choose CSV or Excel file"}
                    </span>
                  </label>
                </div>
                {file && (
                  <div className="mt-3 flex items-center gap-2 text-sm text-green-400">
                    <CheckCircle className="w-4 h-4" />
                    <span>File uploaded successfully</span>
                  </div>
                )}
              </div>

              {/* Project URL */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">
                  <Globe className="w-4 h-4 inline mr-2" />
                  Project URL
                </label>
                <input
                  type="text"
                  value={projectUrl}
                  onChange={(e) => setProjectUrl(e.target.value)}
                  placeholder="http://localhost:3000"
                  className="w-full px-4 py-3 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                />
              </div>

              {/* Generate Button */}
              <button
                onClick={handleGenerate}
                disabled={loading || !file || !projectUrl}
                className="w-full flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 rounded-lg font-semibold transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-indigo-500/25"
              >
                {loading ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    Generating Test Script...
                  </>
                ) : (
                  <>
                    <Code className="w-5 h-5" />
                    Generate Python Playwright Test Script
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Output Section */}
          <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-2xl overflow-hidden flex flex-col">
            <div className="p-6 border-b border-slate-700/50 flex items-center justify-between">
              <h2 className="text-xl font-semibold flex items-center gap-2">
                <Code className="w-5 h-5 text-purple-400" />
                Generated Python Script
              </h2>
              {output && (
                <div className="flex gap-2">
                  <button
                    onClick={handleCopy}
                    className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
                    title="Copy to clipboard"
                  >
                    {copied ? (
                      <CheckCircle className="w-5 h-5 text-green-400" />
                    ) : (
                      <Copy className="w-5 h-5 text-gray-400" />
                    )}
                  </button>
                  <button
                    onClick={handleDownload}
                    className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
                    title="Download Python test script"
                  >
                    <Download className="w-5 h-5 text-gray-400" />
                  </button>
                </div>
              )}
            </div>

            <div className="flex-1 p-6 overflow-hidden">
              {!output && !loading && (
                <div className="h-full flex items-center justify-center text-center">
                  <div>
                    <div className="inline-flex items-center justify-center w-16 h-16 bg-slate-700/50 rounded-full mb-4">
                      <Code className="w-8 h-8 text-gray-500" />
                    </div>
                    <p className="text-gray-500 text-lg">Your generated test script will appear here</p>
                    <p className="text-gray-600 text-sm mt-2">Upload a file and configure the settings to begin</p>
                  </div>
                </div>
              )}

              {loading && (
                <div className="h-full flex items-center justify-center">
                  <div className="text-center">
                    <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                    <p className="text-gray-400">Generating your test script...</p>
                  </div>
                </div>
              )}

              {output && (
                <div className="bg-slate-900/50 rounded-xl border border-slate-700/50 p-4 h-full overflow-auto custom-scrollbar">
                  <pre className="text-sm text-gray-300 leading-relaxed font-mono">
                    {output}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-sm text-gray-500">
          <p>AI-powered test generation • Playwright compatible</p>
        </div>
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
