import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Film,
  Edit3,
  Calendar,
  User,
  ChevronLeft,
  ChevronRight,
  Menu,
  X,
  Play,
  Upload,
  ClipboardList,
  Settings,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/studio", label: "Upload & Auto-Edit", icon: Film, key: "studio" },
  { href: "/clips", label: "Clip Review", icon: ClipboardList, key: "clips" },
  { href: "/templates", label: "Template Editor", icon: Edit3, key: "templates" },
  { href: "/scheduler", label: "Scheduler", icon: Calendar, key: "scheduler" },
  { href: "/accounts", label: "Accounts", icon: User, key: "accounts" },
];

interface SidebarProps {
  collapsed: boolean;
  setCollapsed: (c: boolean) => void;
}

export function Sidebar({ collapsed, setCollapsed }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isActive = (href: string) => location.pathname === href;

  return (
    <>
      <button
        className={cn(
          "fixed left-4 top-4 z-50 lg:hidden p-2 rounded-lg bg-card border border-input text-foreground",
          mobileOpen ? "" : "hidden"
        )}
        onClick={() => setMobileOpen(true)}
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex flex-col w-64 bg-card border-r border-input transition-all duration-300",
          collapsed ? "-translate-x-full" : "translate-x-0",
          mobileOpen ? "translate-x-0" : "",
          "lg:relative lg:translate-x-0 lg:shadow-none lg:border-r lg:border-input"
        )}
        aria-label="Sidebar"
      >
        <div className="flex items-center justify-between h-12 px-4 lg:px-6">
          {!collapsed && (
            <>
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-lg bg-primary/20 flex items-center justify-center text-primary font-bold">
                  CD
                </div>
                <span className="font-bold text-xl tracking-tight">CreatorDesk</span>
              </div>
              {collapsed === false && mobileOpen && (
                <button
                  onClick={() => setMobileOpen(false)}
                  className="ml-auto p-2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-5 w-5" />
                </button>
              )}
            </>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto py-4 space-y-1">
          {navItems.map((item) => {
            const active = isActive(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.key}
                to={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                )}
              >
                <Icon className="h-5 w-5" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-input">
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            System
          </div>
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => navigate("/studio")}
          >
            <Upload className="h-4 w-4 mr-2" /> New Project
          </Button>
        </div>
      </aside>

      {collapsed && !mobileOpen && (
        <div className="fixed inset-y-0 left-0 z-40 w-3 bg-input -translate-x-px"></div>
      )}
    </>
  );
}
