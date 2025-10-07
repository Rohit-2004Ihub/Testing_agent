import React from "react";
import { Play, ArrowRight, FolderOpen, CheckCircle, XCircle, Info } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function App() {
  const navigate = useNavigate();
  const [path, setPath] = React.useState("E:\\PlaywrightSetupAgent");
  const [logs, setLogs] = React.useState([]);
  const [loading, setLoading] = React.useState(false);

  const handleSetup = () => {
    if (!path) return alert("Enter folder path");
    setLogs([]);
    setLoading(true);

    const evtSource = new EventSource(
      `http://localhost:8000/setup_playwright_project?path=${encodeURIComponent(path)}`
    );

    evtSource.onmessage = (e) => {
      const data = JSON.parse(e.data);
      setLogs((prev) => [...prev, data]);
      if (data.message.includes("🎉")) {
        evtSource.close();
        setLoading(false);
      }
    };

    evtSource.onerror = () => {
      evtSource.close();
      setLoading(false);
    };
  };

  const handleNavigateToGenerator = () => {
    navigate("/test-generator");
  };

  const getLogIcon = (type) => {
    switch (type) {
      case "success": return <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />;
      case "error": return <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />;
      default: return <Info className="w-4 h-4 text-blue-400 flex-shrink-0" />;
    }
  };

  const getLogColor = (type) => {
    switch (type) {
      case "success": return "text-green-300";
      case "error": return "text-red-300";
      default: return "text-gray-300";
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white">
      <div className="max-w-5xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-purple-500/10 rounded-2xl mb-4 border border-purple-500/20">
            <Play className="w-8 h-8 text-purple-400" />
          </div>
          <h1 className="text-4xl font-bold mb-3 bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
            Playwright Setup & Test Generator
          </h1>
          <p className="text-gray-400 text-lg">Automate your end-to-end testing workflow</p>
        </div>

        {/* Main Card */}
        <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-slate-700/50 shadow-2xl overflow-hidden">
          {/* Setup Section */}
          <div className="p-8 border-b border-slate-700/50">
            <div className="flex items-center gap-2 mb-6">
              <FolderOpen className="w-5 h-5 text-purple-400" />
              <h2 className="text-xl font-semibold">Project Setup</h2>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Project Path
                </label>
                <input
                  type="text"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-900/50 border border-slate-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                  placeholder="Enter your project folder path..."
                />
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  onClick={handleSetup}
                  disabled={loading}
                  className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-gradient-to-r from-purple-600 to-purple-500 hover:from-purple-500 hover:to-purple-400 rounded-lg font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-purple-500/25"
                >
                  {loading ? (
                    <>
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      Setting up...
                    </>
                  ) : (
                    <>
                      <Play className="w-5 h-5" />
                      Auto Setup Playwright
                    </>
                  )}
                </button>

                <button
                  onClick={handleNavigateToGenerator}
                  className="flex-1 flex items-center justify-center gap-2 px-6 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg font-medium transition-all duration-200 border border-slate-600"
                >
                  Test Script Generator
                  <ArrowRight className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>

          {/* Logs Section */}
          <div className="p-8">
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              Setup Logs
            </h3>
            
            <div className="bg-slate-900/50 rounded-xl border border-slate-700/50 p-4 max-h-96 overflow-y-auto custom-scrollbar">
              {logs.length === 0 ? (
                <div className="text-center py-12">
                  <div className="inline-flex items-center justify-center w-12 h-12 bg-slate-700/50 rounded-full mb-3">
                    <Info className="w-6 h-6 text-gray-500" />
                  </div>
                  <p className="text-gray-500">Waiting for setup to begin...</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {logs.map((log, idx) => (
                    <div
                      key={idx}
                      className="flex items-start gap-3 p-3 rounded-lg bg-slate-800/30 hover:bg-slate-800/50 transition-colors"
                    >
                      {getLogIcon(log.type)}
                      <p className={`text-sm flex-1 ${getLogColor(log.type)} leading-relaxed`}>
                        {log.message}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer Info */}
        <div className="mt-8 text-center text-sm text-gray-500">
          <p>Automated testing made simple with Playwright</p>
        </div>
      </div>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(51, 65, 85, 0.3);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(139, 92, 246, 0.5);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(139, 92, 246, 0.7);
        }
      `}</style>
    </div>
  );
}
