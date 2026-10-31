import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listClips,
  exportPackage,
  listSocialAccounts,
  connectSocialAccount,
  disconnectSocialAccount,
  postNow,
} from "@/lib/api";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui";
import {
  User,
  Download,
  Play,
  FileText,
  Clock,
  CheckCircle2,
  Plus,
  Trash2,
  Youtube,
  Instagram,
  Smartphone,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/utils";
import { toast } from "sonner";
import { SOCIAL_PLATFORMS } from "@/types";

const PLATFORM_ICONS: Record<string, React.ElementType> = {
  youtube: Youtube,
  tiktok: Smartphone,
  instagram: Instagram,
};

export default function Accounts() {
  const queryClient = useQueryClient();
  const [exportClipId, setExportClipId] = useState("");
  const [connectOpen, setConnectOpen] = useState(false);
  const [connectForm, setConnectForm] = useState({
    platform: "youtube",
    account_name: "",
    channel_id: "",
  });

  const { data: clips = [] } = useQuery({
    queryKey: ["accounts-clips"],
    queryFn: () => listClips().then((r) => r.data.filter((c: any) => c.status === "approved" || c.status === "rendered")),
  });

  const { data: accounts = [], refetch: refetchAccounts } = useQuery({
    queryKey: ["social-accounts"],
    queryFn: () => listSocialAccounts().then((r) => r.data),
  });

  const exportMut = useMutation({
    mutationFn: (id: number) => exportPackage(id).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["clips"] });
      const a = document.createElement("a");
      a.href = data.download_url;
      a.download = "package.json";
      a.click();
      toast.success("Export package downloaded");
    },
    onError: () => toast.error("Export failed"),
  });

  const connectMut = useMutation({
    mutationFn: () => connectSocialAccount(connectForm).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social-accounts"] });
      refetchAccounts();
      setConnectOpen(false);
      setConnectForm({ platform: "youtube", account_name: "", channel_id: "" });
      toast.success("Channel connected");
    },
    onError: () => toast.error("Connect failed"),
  });

  const disconnectMut = useMutation({
    mutationFn: (id: number) => disconnectSocialAccount(id).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["social-accounts"] });
      refetchAccounts();
      toast.success("Channel disconnected");
    },
    onError: () => toast.error("Disconnect failed"),
  });

  const postNowMut = useMutation({
    mutationFn: () => postNow().then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      const posted = (data as any)?.posted ?? 0;
      toast.success(posted ? `Posted ${posted} item(s)` : "Nothing queued to post");
    },
    onError: () => toast.error("Post all failed"),
  });

  const atLimit = accounts.length >= 10;

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Accounts</h1>
          <p className="text-muted-foreground">
            Connect your social channels (YouTube Shorts, TikTok, Instagram Reels) to schedule and auto-post
            approved clips directly from Creator Desk. Export-only packages remain available for manual posting.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <Button
            onClick={() => postNowMut.mutate()}
            disabled={postNowMut.isPending}
          >
            <Play className="h-4 w-4 mr-2" /> Post All
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-4">
          <Card>
            <CardHeader>
              <CardTitle>Export Package</CardTitle>
              <CardDescription>Download video + metadata for manual posting.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-2">
                <Label>Clip</Label>
                <select
                  value={exportClipId}
                  onChange={(e) => setExportClipId(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  <option value="">Select an approved clip</option>
                  {clips.map((c: any) => (
                    <option key={c.id} value={c.id.toString()}>
                      {c.title || `Clip ${c.id}`} — {formatDuration(c.duration)}
                    </option>
                  ))}
                </select>
              </div>
              <Button className="w-full" disabled={!exportClipId} onClick={() => {
                if (!exportClipId) return;
                exportMut.mutate(Number(exportClipId));
              }}>
                <Download className="h-4 w-4 mr-2" /> Export Package
              </Button>
            </CardContent>
          </Card>

          <Card className="mt-4">
            <CardHeader className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <User className="h-4 w-4" /> Connected Channels
              </CardTitle>
              <Button
                size="sm"
                disabled={atLimit}
                onClick={() => setConnectOpen(true)}
              >
                <Plus className="h-3.5 w-3.5 mr-1.5" /> Add Channel
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-xs text-muted-foreground">
                {accounts.length} / 10 channels connected
              </div>
              {accounts.length === 0 ? (
                <div className="h-32 flex flex-col items-center justify-center rounded-lg border border-dashed border-input text-muted-foreground">
                  <AlertCircle className="h-8 w-8 mb-2 opacity-50" />
                  <p>No connected channels yet. Add YouTube, TikTok or Instagram Reels to enable auto-posting.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {accounts.map((a: any) => {
                    const Icon = PLATFORM_ICONS[a.platform] || Smartphone;
                    return (
                      <Card key={a.id} className="p-3 border border-input" onClick={() => {}}>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted text-muted-foreground">
                              <Icon className="h-5 w-5" />
                            </div>
                            <div>
                              <div className="font-medium text-sm">{a.account_name}</div>
                              <div className="text-xs text-muted-foreground truncate max-w-xs">
                                {a.channel_id ? `@${a.channel_id}` : "No channel id"}
                              </div>
                            </div>
                          </div>
                          <span className={cn(
                            "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border",
                            a.status === "connected"
                              ? "bg-green-500/10 text-green-400 border-green-500/20"
                              : "bg-muted text-muted-foreground border-muted",
                          )}>
                            {a.status === "connected" ? <CheckCircle2 className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
                            {a.status === "connected" ? "Connected" : "Disconnected"}
                          </span>
                        </div>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (window.confirm(`Disconnect ${a.account_name}?`)) {
                              disconnectMut.mutate(a.id);
                            }
                          }}
                          disabled={disconnectMut.isPending}
                        >
                          <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Disconnect
                        </Button>
                      </Card>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-8">
          <Card>
            <CardHeader>
              <CardTitle>Ready-to-post clips</CardTitle>
            </CardHeader>
            <CardContent>
              {clips.length === 0 ? (
                <div className="h-48 flex flex-col items-center justify-center rounded-lg border border-dashed border-input text-muted-foreground">
                  <FileText className="h-10 w-10 mb-2 opacity-50" />
                  <p>No approved clips yet. Go to Clip Review and approve some.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {clips.map((c: any) => (
                    <AccountClipRow key={c.id} c={c} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={connectOpen} onOpenChange={setConnectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Connect Account</DialogTitle>
            <DialogDescription>
              Link a YouTube, TikTok or Instagram Reels channel. Creator Desk stores the access token locally
              and uses it only to publish the clips you schedule.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex flex-col gap-2">
                <Label>Platform</Label>
                <Select value={connectForm.platform} onValueChange={(v) => setConnectForm({ ...connectForm, platform: v ?? "youtube" })}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select platform" />
                  </SelectTrigger>
                  <SelectContent>
                    {SOCIAL_PLATFORMS.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label>Account name</Label>
                <Input
                  value={connectForm.account_name}
                  onChange={(e) => setConnectForm({ ...connectForm, account_name: e.target.value })}
                  placeholder="e.g. My Cooking Channel"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label>Channel handle / ID</Label>
                <Input
                  value={connectForm.channel_id}
                  onChange={(e) => setConnectForm({ ...connectForm, channel_id: e.target.value })}
                  placeholder="e.g. UCabc123 or @handle"
                />
              </div>
            </div>
            <Button
              className="w-full"
              disabled={connectMut.isPending || !connectForm.account_name}
              onClick={() => connectMut.mutate()}
            >
              {connectMut.isPending ? "Connecting…" : "Connect Account"}
            </Button>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            Limit: up to 10 connected channels. Tokens are stored in the local database; this is a demo/local setup,
            so re-authenticate with the real platform OAuth flow before publishing to live accounts.
          </DialogDescription>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AccountClipRow({ c }: { c: any }) {
  const hashtags = (c.hashtags || "").split(",").filter(Boolean);
  return (
    <div className="flex flex-col lg:flex-row lg:items-center gap-3 rounded-lg border border-input p-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="font-medium">{c.title || "Untitled"}</span>
          <span className="text-[10px] bg-green-500/10 text-green-400 px-2 py-0.5 rounded">{c.status}</span>
        </div>
        <div className="text-xs text-muted-foreground mb-2">
          {c.hook || "No hook"} • {formatDuration(c.duration)}
        </div>
        <div className="flex gap-1 mb-1">
          {hashtags.slice(0, 5).map((h: string, i: number) => (
            <span key={i} className="px-1.5 py-0.5 rounded bg-primary/10 text-primary text-[10px] font-medium border border-primary/20">
              #{h}
            </span>
          ))}
        </div>
        <div className="text-xs text-muted-foreground truncate max-w-[60%]">{c.description || "No description"}</div>
      </div>
      <div className="text-right">
        <div className="text-xs font-mono text-muted-foreground">Clip #{c.id}</div>
        <Button variant="outline" size="sm" onClick={() => {
          navigator.clipboard.writeText([
            c.title || "",
            c.description || "",
            hashtags.join(" "),
          ].filter(Boolean).join("\n\n"));
          toast.success("Copy-paste text copied");
        }}>
          <Clock className="h-3.5 w-3.5 mr-1.5" /> Copy Text
        </Button>
      </div>
    </div>
  );
}
