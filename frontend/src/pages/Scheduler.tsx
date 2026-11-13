import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  listClips,
  listSocialAccounts,
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
} from "@/components/ui";
import { Calendar, Play, ClipboardList, RefreshCw, CheckCircle2, AlertCircle, Clock, Youtube, Instagram, Smartphone } from "lucide-react";
import { formatDuration } from "@/lib/utils";
import { toast } from "sonner";
import { SOCIAL_PLATFORMS } from "@/types";

export default function Scheduler() {
  const queryClient = useQueryClient();
  const [clipId, setClipId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [dailyMorning, setDailyMorning] = useState(false);
  const [manualPlatform, setManualPlatform] = useState("tiktok");

  const { data: clips = [] } = useQuery({
    queryKey: ["scheduler-clips"],
    queryFn: () => listClips().then((r) => r.data.filter((c: any) => c.status === "rendered" || c.status === "approved")),
  });

  const { data: accounts = [] } = useQuery({
    queryKey: ["scheduler-accounts"],
    queryFn: () => listSocialAccounts().then((r) => r.data.filter((a: any) => a.connected)),
  });

  const { data: schedules = [], refetch } = useQuery({
    queryKey: ["schedules"],
    queryFn: () => listSchedules().then((r) => r.data),
  });

  const createMut = useMutation({
    mutationFn: () =>
      createSchedule({
        clip_id: Number(clipId),
        platform: manualPlatform,
        account_id: selectedAccountId(),
        scheduled_at: scheduledAt,
      }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      refetch();
      setClipId("");
      setScheduledAt("");
      setDailyMorning(false);
      toast.success("Scheduled");
    },
    onError: () => toast.error("Schedule failed"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, b }: { id: number; b: Record<string, unknown> }) =>
      updateSchedule(id, b).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      refetch();
      toast.success("Schedule updated");
    },
    onError: () => toast.error("Update failed"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteSchedule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      refetch();
      toast.success("Removed from queue");
    },
  });

  const postNowMut = useMutation({
    mutationFn: () => postNow().then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["schedules"] });
      refetch();
      const posted = (data as any)?.posted ?? 0;
      toast.success(posted ? `Posted ${posted} item(s)` : "Nothing queued to post");
    },
    onError: () => toast.error("Process queue failed"),
  });

  const selectedAccountId = () => {
    const picked = accounts.find((a: any) => a.platform === manualPlatform);
    return picked ? picked.id : null;
  };

  const tomorrowMorning = new Date(Date.now() + 86400000);
  tomorrowMorning.setHours(9, 0, 0, 0);

  const handleDailyMorning = () => {
    setScheduledAt(tomorrowMorning.toISOString().slice(0, 16));
    setDailyMorning(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Scheduler</h1>
          <p className="text-muted-foreground">
            Queue approved clips to connected channels at set times. Pick a clip, choose target channel(s),
            and set a date/time — or use the daily morning slot. Posts run locally from Creator Desk.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <Button
            onClick={() => postNowMut.mutate()}
            disabled={postNowMut.isPending}
          >
            <Play className="h-4 w-4 mr-2" /> Process Queue
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-4">
          <Card>
            <CardHeader>
              <CardTitle>Add to Queue</CardTitle>
              <CardDescription>Pick a rendered clip, target channel(s) and time.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-col gap-2">
                <Label>Clip</Label>
                <Select value={clipId} onValueChange={(v) => setClipId(v ?? "")}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select a rendered clip" />
                  </SelectTrigger>
                  <SelectContent>
                    {clips.map((c: any) => (
                      <SelectItem key={c.id} value={c.id.toString()}>
                        {c.title || `Clip ${c.id}`} ({formatDuration(c.duration)})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {accounts.length > 0 ? (
                <div className="flex flex-col gap-2">
                  <Label>Target channel(s)</Label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {accounts.map((a: any) => (
                      <label key={a.id} className="flex items-center gap-2 cursor-pointer rounded border border-input p-2 text-sm hover:bg-accent">
                        <input
                          type="checkbox"
                          className="w-4 h-4"
                          readOnly
                          onClick={(e) => {
                            e.stopPropagation();
                            setManualPlatform(a.platform);
                          }}
                        />
                        <span className="font-medium truncate">{a.account_name}</span>
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{a.platform}</span>
                      </label>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Selecting a channel schedules the clip for that connected account.{" "}
                    {accounts.length > 1 && "Pick one channel per schedule row; add more rows for other channels."}
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <Label>Platform</Label>
                  <Select value={manualPlatform} onValueChange={(v) => setManualPlatform(v ?? "tiktok")}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={manualPlatform} />
                    </SelectTrigger>
                    <SelectContent>
                      {SOCIAL_PLATFORMS.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    No connected channels yet — connect accounts on the Accounts page so posts have a target channel.
                  </p>
                </div>
              )}

              <div className="flex flex-col gap-2">
                <Label>Scheduled At</Label>
                <div className="flex gap-2 items-end">
                  <Input
                    type="datetime-local"
                    value={scheduledAt}
                    onChange={(e) => {
                      setScheduledAt(e.target.value);
                      setDailyMorning(false);
                    }}
                  />
                  <Button variant="outline" size="sm" onClick={handleDailyMorning}>
                    <Calendar className="h-3.5 w-3.5 mr-1.5" /> Daily 9 AM
                  </Button>
                </div>
                {dailyMorning && (
                  <p className="text-xs text-muted-foreground">
                    Set to {tomorrowMorning.toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}.
                  </p>
                )}
              </div>
              <Button className="w-full" disabled={!clipId || !scheduledAt} onClick={() => {
                if (!clipId || !scheduledAt) return toast.error("Pick a clip and time");
                createMut.mutate();
              }}>
                <Calendar className="h-4 w-4 mr-2" /> Add to Queue
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-8">
          <Card>
            <CardHeader className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <ClipboardList className="h-4 w-4" /> Queue
              </CardTitle>
              <div className="flex items-end gap-2">
                <Button variant="outline" size="sm" onClick={() => refetch()}>
                  <RefreshCw className="h-4 w-4 mr-2" /> Refresh
                </Button>
                <Button
                  onClick={() => postNowMut.mutate()}
                  disabled={postNowMut.isPending}
                  size="sm"
                >
                  <Play className="h-3.5 w-3.5 mr-1.5" /> Process Queue
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {schedules.length === 0 ? (
                <div className="h-48 flex flex-col items-center justify-center rounded-lg border border-dashed border-input text-muted-foreground">
                  Nothing scheduled yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {schedules.map((s: any) => (
                    <ScheduleRow key={s.id} s={s} accounts={accounts} onUpdate={updateMut.mutate} onDelete={deleteMut.mutate} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ScheduleRow({ s, accounts, onUpdate, onDelete }: { s: any; accounts: any[]; onUpdate: any; onDelete: any }) {
  const [editing, setEditing] = useState(false);
  const [platform, setPlatform] = useState(s.platform);
  const [scheduledAt, setScheduledAt] = useState(new Date(s.scheduled_at).toISOString().slice(0, 16));
  const account = accounts.find((a: any) => a.id === s.account_id);

  const PLATFORM_ICONS: Record<string, React.ElementType> = {
    youtube: Youtube,
    tiktok: Smartphone,
    instagram: Instagram,
  };
  const Icon = PLATFORM_ICONS[s.platform] || Smartphone;

  const statusBadge = (status: string) => {
    switch (status) {
      case "posted": return <CheckCircle2 className="h-3 w-3 text-green-400" />;
      case "failed": return <AlertCircle className="h-3 w-3 text-red-400" />;
      default: return <Clock className="h-3 w-3 text-muted-foreground animate-pulse" />;
    }
  };

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-input p-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{s.clip?.title || `Clip ${s.clip_id}`}</span>
          <div className="flex items-center gap-1">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-muted">
              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            {account ? (
              <span className="text-xs font-medium truncate max-w-[120px]">{account.account_name}</span>
            ) : (
              <span className="text-xs text-muted-foreground capitalize">{s.platform}</span>
            )}
          </div>
          {statusBadge(s.status)}
        </div>
        <div className="text-xs text-muted-foreground mt-1">
          {new Date(s.scheduled_at).toLocaleString()} • {s.status}
        </div>
      </div>
      <div className="flex gap-2">
        {editing ? (
          <div className="flex gap-2">
            <Select value={platform} onValueChange={(v) => setPlatform(v ?? "tiktok")}>
              <SelectTrigger className="w-32 text-xs">
                <SelectValue placeholder={platform} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tiktok">TikTok</SelectItem>
                <SelectItem value="instagram">Instagram</SelectItem>
                <SelectItem value="youtube">YouTube</SelectItem>
                <SelectItem value="x">X</SelectItem>
              </SelectContent>
            </Select>
            <Input type="datetime-local" defaultValue={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} className="text-xs" />
            <Button variant="outline" size="sm" onClick={() => {
              onUpdate({ id: s.id, b: { platform, scheduled_at: scheduledAt } });
              setEditing(false);
            }}>Save</Button>
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>X</Button>
          </div>
        ) : (
          <div className="flex gap-1">
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>Edit</Button>
            <Button variant="destructive" size="sm" onClick={() => onDelete(s.id)}>Remove</Button>
          </div>
        )}
      </div>
    </div>
  );
}


