import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { Navbar } from "@/components/layout/Navbar";
import { status } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { WifiOff } from "lucide-react";

import StudioPage from "@/pages/UploadStudio";
import ClipsPage from "@/pages/ClipReview";
import TemplatesPage from "@/pages/TemplateEditor";
import SchedulerPage from "@/pages/Scheduler";
import AccountsPage from "@/pages/Accounts";

export default function App() {
  const [collapsed, setCollapsed] = useState(false);
  const [statusData, setStatusData] = useState<{
    ollama_available: boolean;
  } | null>(null);
  const [offline, setOffline] = useState(false);
  let interval: any;

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await status();
        setStatusData(res.data);
        setOffline(false);
      } catch {
        setOffline(true);
      }
    };
    fetchStatus();
    interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  if (offline) {
    return (
      <div className="flex h-screen items-center justify-center bg-background text-foreground">
        <div className="text-center">
          <WifiOff className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
          <h2 className="text-lg font-medium">Cannot reach API</h2>
          <p className="text-muted-foreground mt-2">
            Make sure the backend is running on localhost:8000.
          </p>
          <Button onClick={() => window.location.reload()} className="mt-4">
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <div className="flex h-screen bg-background text-foreground">
        <Navbar status={statusData} />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />
          <main className="flex-1 flex flex-col overflow-hidden bg-background">
            <div className="flex-1 overflow-y-auto p-6 lg:p-8">
              <Routes>
                <Route index element={<Navigate to="/studio" replace />} />
                <Route path="/studio" element={<StudioPage />} />
                <Route path="/clips" element={<ClipsPage />} />
                <Route path="/templates" element={<TemplatesPage />} />
                <Route path="/scheduler" element={<SchedulerPage />} />
                <Route path="/accounts" element={<AccountsPage />} />
              </Routes>
            </div>
          </main>
        </div>
        {offline && (
          <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full bg-destructive text-destructive-foreground text-xs font-medium border border-destructive/30 shadow-lg">
            <WifiOff className="h-4 w-4 mr-2" /> Backend disconnected
          </div>
        )}
      </div>
    </BrowserRouter>
  );
}
