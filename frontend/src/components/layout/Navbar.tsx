import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Droplets, Circle, AlertCircle, Play, RefreshCw } from "lucide-react";

interface NavbarProps {
  status: { ollama_available: boolean } | null;
}

export function Navbar({ status }: NavbarProps) {
  const location = useLocation();
  const hide = ["/studio", "/clips", "/templates", "/scheduler", "/accounts"];
  const show = !hide.includes(location.pathname);

  return (
    show ? (
      <nav className="sticky top-0 z-40 h-14 border-b border-input bg-background/80 backdrop-blur-md">
        <div className="flex items-center justify-between h-full px-4">
          <div className="flex items-center gap-3">
            <Link to="/studio" className="flex items-center gap-2 text-sm font-medium">
              <Droplets className="h-4 w-4 text-primary" />
              <span>CreatorDesk AI</span>
            </Link>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted text-xs font-medium">
              <span
                className={cnPill(status?.ollama_available)}
              >
                {status?.ollama_available ? "Ollama Online" : "Ollama Offline"}
              </span>
              <Circle
                className={`h-2 w-2 rounded-full ${
                  status?.ollama_available ? "text-green-500" : "text-red-500"
                } animate-pulse`}
              />
            </div>
            <Button variant="ghost" size="sm" className="hidden sm:flex">
              <Play className="h-4 w-4 mr-2" /> Pipeline Status
            </Button>
          </div>
        </div>
      </nav>
    ) : null
  );
}

function cnPill(ok: boolean | undefined) {
  return ok
    ? "bg-green-500/10 text-green-400 border border-green-500/20"
    : "bg-red-500/10 text-red-400 border border-red-500/20";
}
