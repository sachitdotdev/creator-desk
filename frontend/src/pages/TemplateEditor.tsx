import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listTemplates,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  seedTemplates,
} from "@/lib/api";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
  Separator,
  Switch,
} from "@/components/ui";
import {
  Edit,
  Plus,
  Trash2,
  Copy,
  Play,
  RefreshCw,
  Save,
  Palette,
  Font,
  Image as ImageIcon,
  Eye,
  Code,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export default function TemplateEditor() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<TemplateForm>({ name: "", description: "", config: {} as any, is_default: false });
  const [previewConfig, setPreviewConfig] = useState<any>(null);
  const [activeTab, setActiveTab] = useState("visual" as "visual" | "json");

  const { data: templates = [], refetch } = useQuery({
    queryKey: ["templates"],
    queryFn: () => listTemplates().then((r) => r.data),
  });

  const createMut = useMutation({
    mutationFn: (b: any) => createTemplate(b).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      refetch();
      setOpen(false);
      toast.success("Template created");
    },
    onError: () => toast.error("Create failed"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, b }: { id: number; b: any }) => updateTemplate(id, b).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      refetch();
      setOpen(false);
      setEditingId(null);
      toast.success("Template saved");
    },
    onError: () => toast.error("Save failed"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      refetch();
      toast.success("Template deleted");
    },
  });

  useEffect(() => {
    setPreviewConfig(templates.find((t) => t.is_default)?.config || templates[0]?.config || null);
  }, [templates]);

  const selectTemplate = (t: any) => {
    setPreviewConfig(t.config);
    setEditingId(t.id);
    setForm({
      name: t.name,
      description: t.description || "",
      config: JSON.parse(JSON.stringify(t.config)),
      is_default: t.is_default,
    });
    setOpen(true);
  };

  const duplicateTemplate = (t: any) => {
    setForm({
      name: `${t.name} (Copy)`,
      description: t.description || "",
      config: JSON.parse(JSON.stringify(t.config)),
      is_default: false,
    });
    setEditingId(null);
    setOpen(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Template Editor</h1>
          <p className="text-muted-foreground">
            Create, edit, preview and delete templates. Each template drives caption style, titles,
            watermarks and background treatment for 9:16 renders.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <Button onClick={() => seedTemplates()} size="sm" disabled={false}>
            <RefreshCw className="h-4 w-4 mr-2" /> Seed Defaults
          </Button>
          <Button onClick={() => { setForm({ name: "", description: "", config: defaultConfig(), is_default: false }); setEditingId(null); setOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" /> New Template
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Templates list */}
        <div className="lg:col-span-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider">Templates</h2>
          </div>
          {templates.length === 0 ? (
            <div className="h-40 flex flex-col items-center justify-center rounded-xl border border-dashed border-input bg-muted/50 text-muted-foreground text-sm">
              No templates. Click "Seed Defaults" or create one.
            </div>
          ) : (
            <div className="space-y-2">
              {templates.map((t) => (
                <TemplateListItem
                  key={t.id}
                  t={t}
                  isEditing={editingId === t.id}
                  onSelect={selectTemplate}
                  onDuplicate={() => duplicateTemplate(t)}
                  onDelete={(id: number) => {
                    if (window.confirm(`Delete template "${t.name}"?`)) deleteMut.mutate(id);
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Editor + preview */}
        <div className="lg:col-span-8 flex flex-col gap-4">
          {previewConfig ? (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wider">Live Preview</h2>
                <TabsControl active={activeTab} onSet={setActiveTab} />
              </div>

              <div className="flex-1 min-h-[520px] grid grid-cols-2 gap-4">
                {/* Preview canvas */}
                <div className="col-span-1 flex flex-col items-center justify-center bg-[#0a0a0a] rounded-xl border border-input p-4 relative overflow-hidden">
                  <div className="absolute top-4 left-4 text-xs font-medium text-muted-foreground">
                    9:16 Preview
                  </div>
                  <TemplatePreview config={previewConfig} />
                </div>

                {/* Controls */}
                <div className="col-span-1 overflow-y-auto space-y-4">
                  {activeTab === "visual" ? (
                    <VisualControls config={previewConfig} onChange={setPreviewConfig} />
                  ) : (
                    <JsonControls config={previewConfig} onChange={setPreviewConfig} />
                  )}
                </div>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Save className="h-4 w-4" /> Save Template
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="flex flex-col gap-2">
                    <Label>Name</Label>
                    <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label>Description</Label>
                    <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
                  </div>
                  <div className="flex items-end">
                    <Label className="flex items-center gap-2">
                      <Switch checked={form.is_default} onCheckedChange={(v) => setForm({ ...form, is_default: !!v })} />
                      Default template
                    </Label>
                  </div>
                </CardContent>
                <CardFooter className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                  <Button onClick={() => {
                    const payload = { ...form, config: previewConfig };
                    if (editingId) updateMut.mutate({ id: editingId, b: payload });
                    else createMut.mutate(payload);
                  }}>
                    {editingId ? "Save Changes" : "Create Template"}
                  </Button>
                </CardFooter>
              </Card>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 rounded-xl border border-dashed border-input bg-muted/50 text-muted-foreground">
              <Eye className="h-8 w-8 mb-2 opacity-50" />
              <p>Select a template to preview</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function defaultConfig() {
  return {
    vibe: "Custom",
    colors: { primary: "#FFFFFF", accent: "#7B68EE", background: "#000000", highlight: "#7B68EE" },
    caption: { font: "Arial", size: 48, bold: 1, primary: "&H00FFFFFF&", outline: "&H00000000&", back: "&H4D000000&", alignment: 2, margin_v: 120, outline_w: 3, shadow: 0, highlight_color: "&H0068EE7B&", karaoke: false, kinetic: true },
    title: { font: "Arial", size: 36, bold: 1, color: "&H00FFFFFF&", position: "top", margin_v: 70, outline_w: 2, glow: false, text: "CREATOR DESK" },
    watermark: { text: "", font: "Arial", size: 22, color: "&H00FFFFFF&", opacity: 0.3, position: "bottom-right", margin_x: 40, margin_y: 40 },
    background: { mode: "blur", blur_amount: 25, color: "#000000" },
  };
}

type TemplateForm = {
  name: string;
  description: string;
  config: any;
  is_default: boolean;
};

// ---------- List item ----------
function TemplateListItem({
  t,
  isEditing,
  onSelect,
  onDuplicate,
  onDelete,
}: {
  t: any; isEditing: boolean; onSelect: (t: any) => void; onDuplicate: (t: any) => void; onDelete: (id: number) => void;
}) {
  return (
    <div className={cn(
      "flex items-center justify-between gap-2 rounded-lg border px-3 py-2.5 text-sm transition-colors cursor-pointer",
      isEditing ? "bg-primary/10 border-primary text-primary" : "bg-card border-input hover:bg-accent hover:text-foreground"
    )} onClick={() => onSelect(t)}>
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-1.5">
        <span className="font-medium truncate">{t.name}</span>
        {t.is_default && <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded">default</span>}
      </div>
      <p className="text-xs text-muted-foreground truncate">{t.description || "No description"}</p>
    </div>
    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <button onClick={(e) => { e.stopPropagation(); onDuplicate(t); }} className="p-1.5 text-muted-foreground hover:text-foreground" title="Duplicate">
        <Copy className="h-4 w-4" />
      </button>
      <button onClick={(e) => { e.stopPropagation(); onDelete(t.id); }} className="p-1.5 text-muted-foreground hover:text-red-400" title="Delete">
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  </div>
  );
}

// ---------- Tabs ----------
function TabsControl({ active, onSet }: { active: string; onSet: (v: string) => void }) {
  return (
    <div className="flex gap-1">
      {["visual", "json"].map((k) => (
        <button
          key={k}
          onClick={() => onSet(k)}
          className={cn("px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
            active === k ? "bg-primary text-primary-foreground" : "border border-input text-muted-foreground hover:bg-accent"
          )}
        >
          {k === "visual" ? "Visual" : "JSON"}
        </button>
      ))}
    </div>
  );
}

// ---------- JSON controls ----------
function JsonControls({ config, onChange }: { config: any; onChange: (v: any) => void }) {
  const [json, setJson] = useState(JSON.stringify(config, null, 2));
  useEffect(() => setJson(JSON.stringify(config, null, 2)), [config]);
  return (
    <div className="flex flex-col gap-2">
      <Label>Template JSON Config</Label>
      <Textarea
        value={json}
        onChange={(e) => {
          setJson(e.target.value);
          try { onChange(JSON.parse(e.target.value)); } catch { /* invalid json, keep last */ }
        }}
        className="font-mono text-xs h-64"
      />
      <p className="text-xs text-muted-foreground">Edit raw JSON. Invalid JSON is ignored until valid.</p>
    </div>
  );
}

// ---------- Visual controls ----------
function VisualControls({ config, onChange }: { config: any; onChange: (v: any) => void }) {
  const cap = config.caption || {};
  const title = config.title || {};
  const wm = config.watermark || {};
  const bg = config.background || {};
  const colors = config.colors || {};

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-input bg-card p-3">
        <div className="flex items-center justify-between mb-3">
          <Label className="text-sm font-medium">Colors</Label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <ColorRow label="Primary" value={colors.primary} onChange={(v) => onChange({ ...config, colors: { ...colors, primary: v } })} />
          <ColorRow label="Accent" value={colors.accent} onChange={(v) => onChange({ ...config, colors: { ...colors, accent: v } })} />
          <ColorRow label="Background" value={colors.background} onChange={(v) => onChange({ ...config, colors: { ...colors, background: v } })} />
          <ColorRow label="Highlight" value={colors.highlight} onChange={(v) => onChange({ ...config, colors: { ...colors, highlight: v } })} />
        </div>
      </div>

      <div className="rounded-xl border border-input bg-card p-3">
        <Label className="text-sm font-medium mb-2 block">Captions</Label>
        <div className="grid grid-cols-2 gap-3">
          <InputRow label="Font" value={cap.font || "Arial"} onChange={(v) => setNested("caption", "font", v)} />
          <InputRow label="Size" type="number" value={String(cap.size || 48)} onChange={(v) => setNested("caption", "size", Number(v) || 48)} />
          <InputRow label="Primary color (ASS)" value={cap.primary || "&H00FFFFFF&"} onChange={(v) => setNested("caption", "primary", v)} />
          <InputRow label="Margin V" type="number" value={String(cap.margin_v || 120)} onChange={(v) => setNested("caption", "margin_v", Number(v) || 120)} />
          <InputRow label="Outline width" type="number" value={String(cap.outline_w || 3)} onChange={(v) => setNested("caption", "outline_w", Number(v) || 3)} />
          <SwitchRow label="Karaoke highlight" checked={!!cap.karaoke} onChange={(v) => setNested("caption", "karaoke", v)} />
          <SwitchRow label="Kinetic word captions" checked={!!cap.kinetic} onChange={(v) => setNested("caption", "kinetic", v)} />
        </div>
      </div>

      <div className="rounded-xl border border-input bg-card p-3">
        <Label className="text-sm font-medium mb-2 block">Title</Label>
        <div className="grid grid-cols-2 gap-3">
          <InputRow label="Text" value={title.text || "CREATOR DESK"} onChange={(v) => setNested("title", "text", v)} />
          <InputRow label="Font" value={title.font || "Arial"} onChange={(v) => setNested("title", "font", v)} />
          <InputRow label="Size" type="number" value={String(title.size || 36)} onChange={(v) => setNested("title", "size", Number(v) || 36)} />
          <SelectRow label="Position" value={title.position || "top"} items={["top", "center", "bottom"]} onChange={(v) => setNested("title", "position", v)} />
          <SwitchRow label="Glow" checked={!!title.glow} onChange={(v) => setNested("title", "glow", v)} />
        </div>
      </div>

      <div className="rounded-xl border border-input bg-card p-3">
        <Label className="text-sm font-medium mb-2 block">Watermark</Label>
        <div className="grid grid-cols-2 gap-3">
          <InputRow label="Text" value={wm.text || ""} onChange={(v) => setNested("watermark", "text", v)} />
          <InputRow label="Opacity" type="number" step="0.1" value={String(wm.opacity || 0.3)} onChange={(v) => setNested("watermark", "opacity", Number(v) || 0.3)} />
          <InputRow label="Size" type="number" value={String(wm.size || 22)} onChange={(v) => setNested("watermark", "size", Number(v) || 22)} />
          <SelectRow label="Position" value={wm.position || "bottom-right"} items={["bottom-right", "bottom-left", "top-right", "top-left"]} onChange={(v) => setNested("watermark", "position", v)} />
        </div>
      </div>

      <div className="rounded-xl border border-input bg-card p-3">
        <Label className="text-sm font-medium mb-2 block">Background</Label>
        <SelectRow label="Mode" value={bg.mode || "blur"} items={["blur", "solid", "bars"]} onChange={(v) => setNested("background", "mode", v)} />
        <InputRow label="Blur amount" type="number" value={String(bg.blur_amount || 25)} onChange={(v) => setNested("background", "blur_amount", Number(v) || 25)} />
        <ColorRow label="Color" value={bg.color || "#000000"} onChange={(v) => onChange({ ...config, background: { ...bg, color: v } })} />
      </div>
    </div>
  );

  function setNested(section: string, key: string, value: any) {
    onChange({ ...config, [section]: { ...config[section], [key]: value } });
  }
}

function ColorRow({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <Label className="text-xs">{label}</Label>
      <div className="flex items-center gap-2">
        <input type="color" value={assToHex(value)} onChange={(e) => onChange(hexToAss(e.target.value))} className="h-8 w-12 rounded cursor-pointer" />
        <Input value={value} onChange={(e) => onChange(e.target.value)} className="text-xs" />
      </div>
    </div>
  );
}

function InputRow({ label, value, type = "text", onChange }: { label: string; value: string; type?: string; onChange: (v: any) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <Label className="text-xs">{label}</Label>
      <Input type={type} value={value} onChange={(e) => onChange(e.target.value)} className="text-xs" />
    </div>
  );
}

function SelectRow({ label, value, items, onChange }: { label: string; value: string; items: string[]; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <Label className="text-xs">{label}</Label>
      <Select value={value} onValueChange={(v) => onChange(v ?? value)}>
        <SelectTrigger className="w-full text-xs">
          <SelectValue placeholder={value} />
        </SelectTrigger>
        <SelectContent>
          {items.map((i) => <SelectItem key={i} value={i}>{i}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}

function SwitchRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

function assToHex(ass: string): string {
  // &H00BBGGRR& -> #RRGGBB
  const m = ass.match(/&H00([0-9A-Fa-f]{6})&/);
  if (!m) return "#ffffff";
  const bgr = m[1];
  const r = bgr.slice(4, 6);
  const g = bgr.slice(2, 4);
  const b = bgr.slice(0, 2);
  return `#${r}${g}${b}`.toLowerCase();
}

function hexToAss(hex: string): string {
  const h = hex.replace("#", "");
  const r = h.slice(0, 2);
  const g = h.slice(2, 4);
  const b = h.slice(4, 6);
  return `&H00${b}${g}${r}&`;
}

// ---------- Preview canvas ----------
function TemplatePreview({ config }: { config: any }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = 432;
    const H = 768;
    canvas.width = W;
    canvas.height = H;

    const cap = config.caption || {};
    const title = config.title || {};
    const wm = config.watermark || {};
    const bg = config.background || {};
    const colors = config.colors || {};

    // Background
    const bgMode = bg.mode || "blur";
    if (bgMode === "solid" || bgMode === "bars") {
      ctx.fillStyle = hexToCss(bg.color || "#000000");
      ctx.fillRect(0, 0, W, H);
    } else {
      // blurred simulation: gradient
      const grad = ctx.createLinearGradient(0, 0, 0, H);
      grad.addColorStop(0, "#1a1a2e");
      grad.addColorStop(1, "#0f0f12");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, W, H);
    }

    // Center video placeholder (rounded rect)
    const vw = W * 0.85;
    const vh = W * 0.85 * (9 / 16);
    const vx = (W - vw) / 2;
    const vy = (H - vh) / 2;
    ctx.fillStyle = "#222";
    ctx.fillRect(vx, vy, vw, vh);
    ctx.strokeStyle = "rgba(255,255,255,0.1)";
    ctx.lineWidth = 2;
    ctx.strokeRect(vx, vy, vw, vh);
    ctx.fillStyle = "rgba(255,255,255,0.3)";
    ctx.font = "bold 14px Inter";
    ctx.textAlign = "center";
    ctx.fillText("SOURCE VIDEO (center crop)", W / 2, H / 2);

    // Title
    const tText = title.text || "CREATOR DESK";
    if (tText) {
      ctx.font = `bold ${Math.max(14, title.size || 36) * 0.45}px ${title.font || "Arial"}`;
      ctx.fillStyle = hexToCss(assToHex(title.color || "&H00FFFFFF&"));
      ctx.textAlign = "center";
      let ty = title.position === "top" ? (title.margin_v || 70) * 0.4 : title.position === "bottom" ? H - (title.margin_v || 70) * 0.4 : H / 2;
      ctx.fillText(tText, W / 2, ty);
    }

    // Caption sample
    const sample = "This is a sample caption burned into the video";
    ctx.font = `bold ${Math.max(12, cap.size || 48) * 0.45}px ${cap.font || "Arial"}`;
    ctx.fillStyle = hexToCss(assToHex(cap.primary || "&H00FFFFFF&"));
    ctx.textAlign = "center";
    const cy = cap.alignment === 2 ? H - (cap.margin_v || 120) * 0.45 : H / 2;
    ctx.fillText(sample, W / 2, cy);

    // Watermark
    if (wm.text) {
      ctx.font = `${Math.max(10, wm.size || 22) * 0.4}px ${wm.font || "Arial"}`;
      ctx.globalAlpha = wm.opacity || 0.3;
      ctx.fillStyle = hexToCss(assToHex(wm.color || "&H00FFFFFF&"));
      const pos = wm.position || "bottom-right";
      const mx = wm.margin_x || 40;
      const my = wm.margin_y || 40;
      const tw = ctx.measureText(wm.text).width;
      const x = pos === "bottom-right" ? W - tw - mx * 0.8 : pos === "bottom-left" ? mx * 0.8 : pos === "top-right" ? W - tw - mx * 0.8 : mx * 0.8;
      const y = pos === "top-right" || pos === "top-left" ? my * 0.8 + 12 : H - my * 0.8;
      ctx.fillText(wm.text, x, y);
      ctx.globalAlpha = 1;
    }

    // Frame border
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 1;
    ctx.strokeRect(0, 0, W, H);
  }, [config]);

  return (
    <div className="relative">
      <canvas ref={canvasRef} className="rounded-lg shadow-xl border border-white/10" />
    </div>
  );
}

function hexToCss(ass: string): string {
  return assToHex(ass);
}
