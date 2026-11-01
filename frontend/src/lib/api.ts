import axios, { AxiosInstance } from "axios";

const BASE_URL = "http://127.0.0.1:8000";

export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// Videos
export const listVideos = async () => {
  const res = await api.get('/api/videos');
  const data = await res.json();
  return data;
};
export const uploadVideo = (file: File) => {
  const fd = new FormData();
  fd.append("file", file);
  return api.post("/api/videos/upload", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const deleteVideo = (id: number) => api.delete(`/api/videos/${id}`);
export const processVideo = (
  id: number,
  body: { video_id: number; template_id?: number; num_clips?: number; vibe?: string },
) => {
  const url = `${BASE_URL}/api/videos/${id}/process`;
  console.log("FETCHING URL:", url);
  return api.post(url, body);
};
export const pipelineStatus = (id: number) => api.get(`/api/pipeline/${id}/status`);

// Clips
export const listClips = (videoId?: number) => {
  const url = videoId ? `http://127.0.0.1:8000/api/clips?video_id=${videoId}` : "http://127.0.0.1:8000/api/clips";
  return api.get(url);
};
export const getClip = (id: number) => api.get(`/api/clips/${id}`);
export const updateClip = (id: number, body: Record<string, unknown>) =>
  api.put(`/api/clips/${id}`, body);
export const deleteClip = (id: number) => api.delete(`/api/clips/${id}`);
export const reRenderClip = (id: number) => api.post(`/api/clips/${id}/render`);
export const getRender = (filename: string) => api.get(`/api/renders/${filename}`);
export const getSource = (filename: string) => api.get(`/api/sources/${filename}`);

// Templates
export const listTemplates = () => api.get("/api/templates");
export const getTemplate = (id: number) => api.get(`/api/templates/${id}`);
export const createTemplate = (body: Record<string, unknown>) => api.post("/api/templates", body);
export const updateTemplate = (id: number, body: Record<string, unknown>) =>
  api.put(`/api/templates/${id}`, body);
export const deleteTemplate = (id: number) => api.delete(`/api/templates/${id}`);
export const seedTemplates = () => api.post("/api/templates/seed");

// Schedules
export const listSchedules = () => api.get("/api/schedules");
export const createSchedule = (body: Record<string, unknown>) => api.post("/api/schedules", body);
export const updateSchedule = (id: number, body: Record<string, unknown>) =>
  api.put(`/api/schedules/${id}`, body);
export const deleteSchedule = (id: number) => api.delete(`/api/schedules/${id}`);

// Schedule execution
export const listPendingSchedules = () => api.get("/api/schedule/pending");
export const postNow = (body?: Record<string, unknown>) => api.post("/api/schedule/post-now", body ?? {});

// Social accounts
export const listSocialAccounts = () => api.get("/api/accounts");
export const connectSocialAccount = (body: Record<string, unknown>) => api.post("/api/accounts/connect", body);
export const disconnectSocialAccount = (id: number) => api.delete(`/api/accounts/${id}`);

// Export
export const exportPackage = (clipId: number) => api.post("/api/accounts/export", { clip_id: clipId });

// Trending
export const getTrending = () => api.get("/api/discover/trending");

// Status
export const status = () => {
  try {
    const res = api.get("/api/videos");
    return { data: { ollama_available: true } };
  } catch {
    return { data: { ollama_available: false } };
  }
};
