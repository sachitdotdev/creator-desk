import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listClips,
  updateClip,
  deleteClip,
  reRenderClip,
  listTemplates,
  getRender,
  getSource,
} from "@/lib/api";
import {
  Button,
  Card,
  CardContent,
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
  Dialog,
  DialogContent,
  DialogTrigger,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Separator,
} from "@/components/ui";
import {
  Play,
  Edit,
  Trash2,
  RefreshCw,
  CheckCircle2,
  X,
  Film,
  Loader2,
  ThumbsUp,
  ThumbsDown,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatTime, formatDuration } from "@/lib/utils";
import { toast } from "sonner";

function renderUrl(outputPath: string | null): string {
  if (!outputPath) return "";
  const name = outputPath.split(/[\\/]/).pop();
  return name ? `/renders/${name}` : "";
}

export default function ClipReview() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const [templates, setTemplates] = useState<any[]>([]);

  const videoParam = searchParams.get("video");
  const videoId = videoParam ? Number(videoParam) : null;

  const { data: clips = [], isLoading: loadingClips, refetch } = useQuery({
    queryKey: ["clips", videoId],
    queryFn: async () => {
      const data = await listClips(videoId).then((r) => r.data);
      console.log("CLIPS DATA RECEIVED:", data);
      return Array.isArray(data) ? data : [];
    },
  });

  const filteredClips = useMemo(() => {
    const allClips = clips || [];
    if (videoId == null) return allClips;
    return allClips.filter((clip) => clip.video_id === videoId);
  }, [clips, videoId]);

  useQuery({
    queryKey: ["templates-list"],
    queryFn: () => listTemplates().then((r) => { setTemplates(r.data); return r.data; }),
    enabled: templates.length === 0,
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      updateClip(id, body).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clips"] });
      refetch();
      toast.success("Clip updated");
      setEditOpen(false);
    },
    onError: () => toast.error("Update failed"),
  });

  const renderMut = useMutation({
    mutationFn: (id: number) => reRenderClip(id).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clips"] });
      toast.success("Re-rendering clip");
    },
    onError: () => toast.error("Re-render failed"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteClip(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clips"] });
      refetch();
      toast.success("Clip deleted");
    },
  });


  const hashtagsArr = (s: string | null) => (s ? s.split(",").filter(Boolean) : []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Clip Review & Approval</h1>
          <p className="text-muted-foreground">
            Review generated clips, adjust in/out points, change template, approve for posting.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <Button onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" /> Refresh
          </Button>
        </div>
      </div>

      {loadingClips ? (
        <Card className="flex flex-col items-center justify-center py-20 text-center border-dashed">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-muted-foreground mb-3" />
          <h3 className="text-sm font-medium">Loading clips…</h3>
        </Card>
      ) : filteredClips.length === 0 ? (
        <Card className="flex flex-col items-center justify-center py-20 text-center border-dashed">
          <Film className="mx-auto h-12 w-12 text-muted-foreground mb-3" />
          <h3 className="text-sm font-medium">
            {videoId ? "No clips rendered yet." : "No video selected."}
          </h3>
          <p className="text-muted-foreground text-sm">
            {videoId
              ? "Go to Studio to process this video."
              : "Select a video from Studio or view recent clips below."}
          </p>
          <Button onClick={() => navigate("/studio")} className="mt-4">
            Go back to Studio
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {(filteredClips || []).map((clip) => (
            <ClipCard
              key={clip.id}
              clip={clip}
              templates={templates}
              onEdit={setEditing}
              onPreview={setPreviewUrl}
              onUpdate={updateMut.mutate}
              onRender={renderMut.mutate}
              onDelete={deleteMut.mutate}
            />
          ))}
        </div>
      )}

      {/* Edit dialog */}
      <Dialog open={editOpen} onOpenChange={(o) => { setEditOpen(o); if (!o) setEditing(null); }}>
        <DialogTrigger asChild>
          <Button variant="outline" size="sm" disabled={!editing}>
            Edit Selected
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Clip</DialogTitle>
            <DialogDescription>
              Adjust in/out points, title, description, hashtags and template.
            </DialogDescription>
          </DialogHeader>
          <Separator className="my-4" />
          <DialogContent className="space-y-4">
            {editing && <EditForm clip={editing} templates={templates} onSave={updateMut.mutate} />}
          </DialogContent>
        </DialogContent>
      </Dialog>

      {/* Preview dialog */}
      <Dialog open={previewOpen} onOpenChange={(o) => { setPreviewOpen(o); if (!o) setPreviewUrl(""); }}>
        <DialogContent className="max-w-[720px] max-h-[90vh] flex flex-col p-0">
          <DialogHeader className="px-6 py-4">
            <DialogTitle>Clip Preview</DialogTitle>
          </DialogHeader>
          <Separator className="my-0 border-t" />
          <div className="flex-1 min-h-[420px] flex items-center justify-center bg-[#0a0a0a] rounded-b-xl border-b border-input relative overflow-hidden px-6 pb-6">
            {previewUrl ? (
              <video
                autoPlay
                playsInline
                muted
                controls
                className="max-w-full max-h-full rounded-xl shadow-2xl"
                src={previewUrl}
              />
            ) : (
              <div className="text-center">
                <Film className="h-12 w-12 text-muted-foreground mb-3" />
                <p className="text-muted-foreground">Select a clip to preview</p>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EditForm({ clip, templates, onSave }: { clip: any; templates: any[]; onSave: any }) {
  const [form, setForm] = useState({
    start_time: clip.start_time,
    end_time: clip.end_time,
    title: clip.title || "",
    hook: clip.hook || "",
    description: clip.description || "",
    hashtags: clip.hashtags || "",
    template_id: clip.template_id ? clip.template_id.toString() : "",
    status: clip.status,
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave({ id: clip.id, body: form }); }}>
      <div className="grid gap-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1">
            <Label>Start (s)</Label>
            <Input type="number" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: Number(e.target.value) || 0 })} />
          </div>
          <div className="flex flex-col gap-1">
            <Label>End (s)</Label>
            <Input type="number" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: Number(e.target.value) || 0 })} />
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <Label>Title</Label>
          <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Hook</Label>
          <Input value={form.hook} onChange={(e) => setForm({ ...form, hook: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Description</Label>
          <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Hashtags (comma separated)</Label>
          <Input value={form.hashtags} onChange={(e) => setForm({ ...form, hashtags: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1">
          <Label>Template</Label>
          <Select value={form.template_id} onValueChange={(v) => setForm({ ...form, template_id: v ?? "" })}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Default template" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">Default</SelectItem>
              {(templates || []).map((t) => (
                <SelectItem key={t.id} value={t.id.toString()}>{t.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <Label>Status</Label>
          <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v ?? "pending" })}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder={form.status} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <Button type="button" variant="outline" onClick={() => { /* close handled by parent */ }}>
          Cancel
        </Button>
        <Button type="submit">Save Changes</Button>
      </div>
    </form>
  );
}

function ClipCard({
  clip,
  templates,
  onEdit,
  onPreview,
  onUpdate,
  onRender,
  onDelete,
}: {
  clip: any;
  templates: any[];
  onEdit: (c: any) => void;
  onPreview: (u: string) => void;
  onUpdate: (a: { id: number; body: Record<string, unknown> }) => void;
  onRender: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  const template = templates.find((t) => t.id === clip?.template_id);
  const rawHashtags = clip?.clip_metadata?.hashtags || clip?.hashtags || "";
  const hashtagsArr = Array.isArray(rawHashtags) ? rawHashtags : String(rawHashtags).split(" ").filter(Boolean);
  const hashtags = hashtagsArr;

  const [isHovered, setIsHovered] = useState(false);

  return (
    <Card
      className="group border border-input hover:border-primary/50 transition-colors cursor-pointer rounded-xl overflow-hidden"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {clip?.file_path ? (
        <div className="relative aspect-video bg-[#0a0a0a] rounded-t-xl overflow-hidden">
          <video 
    controls 
    src={clip.file_path ? `http://127.0.0.1:8000${clip.file_path}` : undefined}
    onError={(e) => console.error("VIDEO LOAD ERROR:", e.currentTarget.error, "SRC:", e.currentTarget.src)}
>
    Your browser does not support the video tag.
</video>

          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent pointer-events-none"></div>
          <div className="absolute bottom-3 left-3 flex items-center gap-1 text-xs font-medium bg-black/60 px-2 py-1 rounded backdrop-blur">
            <span className={cn("bg-green-500/20 text-green-400 border border-green-500/30", "px-1.5 py-0.5 rounded text-[10px]")}>
              {clip?.status}
            </span>
            {clip?.progress > 0 && clip?.progress < 100 && (
              <div className="ml-2 w-16 h-1 bg-black/40 rounded-full overflow-hidden">
                <div className="h-full bg-primary" style={{ width: `${clip?.progress}%` }}></div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="aspect-video bg-[#0a0a0a] rounded-t-xl flex items-center justify-center text-muted-foreground text-xs">
          Not rendered
        </div>
      )}

      <CardContent className="p-0"> <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden"> {clip.file_path ? ( <video src={`http://127.0.0.1:8000${clip.file_path}`} controls className="w-full h-full object-cover" /> ) : ( <span className="text-muted-foreground text-sm">Not rendered</span> )} <span className={`absolute top-2 left-2 px-2 py-1 rounded-md text-xs font-bold bg-green-500/20 text-green-400 border border-green-500/30`}> {clip.status} </span> </div> <div className="p-4 space-y-3"> <div className="flex items-center justify-between"> <h3 className="font-semibold text-sm line-clamp-1">{clip.title || "Untitled Clip"}</h3> </div> <div className="flex items-center gap-2 text-xs text-muted-foreground"> <span>{formatTime(clip.start_time)} - {formatTime(clip.end_time)}</span> <span>•</span> <span>{formatTime(clip.duration)}</span> </div> <div className="flex flex-wrap gap-1"> {(typeof clip.hashtags === 'string' ? clip.hashtags.split(',') : (Array.isArray(clip.hashtags) ? clip.hashtags : [])).map((tag: string, i: number) => ( <span key={i} className="text-[10px] bg-secondary text-secondary-foreground px-2 py-0.5 rounded-full"> {tag} </span> ))} </div> </div> </CardContent> <CardFooter className="flex items-center justify-between gap-2 px-3 py-2 bg-muted/50 border-t"> <div className="flex items-center gap-2"> <Button variant="outline" size="sm"> <Edit className="h-4 w-4 mr-1.5" /> Edit </Button> <Button variant="outline" size="sm" onClick={(e) => { console.log("RENDER CLICKED"); e.stopPropagation(); onRender(clip.id); }}> <RefreshCw className="h-4 w-4 mr-1.5" /> Render </Button> </div> <div className="flex items-center gap-2"> <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => onDelete(clip.id)}> <Trash2 className="h-4 w-4" /> </Button> </div> </CardFooter>
    </Card>
  );
}

function ActionButton({ icon, active, onClick }: { icon: JSX.Element; active: boolean; onClick: (e: React.MouseEvent) => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "p-1.5 rounded transition-colors",
        active ? "text-primary bg-primary/10" : "text-muted-foreground hover:bg-accent"
      )}
    >
      {icon}
    </button>
  );
}
