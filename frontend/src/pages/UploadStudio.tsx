import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, Play } from 'lucide-react';

export function VideoRow({ video, onSelect, isSelected }: { video: any; onSelect?: () => void; isSelected?: boolean }) {
  return (
    <div onClick={() => onSelect?.()} className={`flex items-center justify-between p-4 bg-slate-800/50 rounded-lg mb-2 ${isSelected ? 'border-purple-500' : ''}`}>
      <div>
        <h3 className="font-semibold text-white">{video.original_name || video.filename}</h3>
        <p className="text-xs text-slate-400">{video.status === 'done' ? 'Done' : video.status}</p>
      </div>
      <button onClick={(e) => { e.stopPropagation(); navigate(`/clips?videoId=${video.id}`); }} className="text-xs text-purple-400 font-semibold">View Clips</button>
    </div>
  );
}

export default function UploadStudio() {
  const navigate = useNavigate();
  const [videos, setVideos] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [trending, setTrending] = useState<any[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  useEffect(() => {
    fetch('http://127.0.0.1:8000/api/videos').then(r => r.json()).then(setVideos).catch(() => {});
    fetch('http://127.0.0.1:8000/api/templates').then(r => r.json()).then(setTemplates).catch(() => {});
    fetch('http://127.0.0.1:8000/api/discover/trending').then(r => r.json()).then(setTrending).catch(() => {});
  }, []);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleUpload = async () => {
    if (!selectedFile) return;

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await fetch('http://127.0.0.1:8000/api/videos/upload', {
        method: 'POST',
        body: formData
      });
      if (response.ok) {
        window.location.reload();
      }
    } catch (error) {
      console.error('Upload failed:', error);
    }
  };

  const startPipeline = async () => {
    if (!selectedVideoId) { alert('Please select a video first'); return; }
    const videoId = selectedVideoId;
    setIsProcessing(true);
    try {
      await fetch(`http://127.0.0.1:8000/api/videos/${videoId}/process`, { method: 'POST' });

      const interval = setInterval(async () => {
        const res = await fetch('http://127.0.0.1:8000/api/videos');
        const data = await res.json();
        setVideos(data);
        const currentVideo = data.find((v: any) => v.id === videoId);
        if (currentVideo && (currentVideo.status === 'done' || currentVideo.status === 'error')) {
          clearInterval(interval);
          setIsProcessing(false);
        }
      }, 3000);
    } catch (e) {
      console.error(e);
      setIsProcessing(false);
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      <div className="text-center space-y-2">
        <h1 className="text-4xl font-bold tracking-tight text-white">Creator Desk</h1>
        <p className="text-slate-400">AI-powered auto-edit pipeline</p>
      </div>
      <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800 mb-6">
        <h2 className="text-xl font-bold text-white mb-4">Upload Video</h2>
        <div className="flex flex-col gap-3">
          <input
            type="file"
            accept="video/*"
            onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
            className="bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white"
          />
          <button
            onClick={handleUpload}
            className="bg-purple-600 hover:bg-purple-500 text-white px-6 py-2 rounded-lg font-semibold flex items-center gap-2"
          >
            Upload Video
          </button>
        </div>
      </div>
      <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800">
        <h2 className="text-xl font-bold text-white mb-4">Start Auto-Edit Pipeline</h2>
        <div className="flex items-end gap-4">
          <div className="flex-1">
            <label className="block text-sm text-slate-400 mb-1">Number of clips</label>
            <input type="number" defaultValue={5} className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white" />
          </div>
          <div className="flex-1">
            <label className="block text-sm text-slate-400 mb-1">Template</label>
            <select className="w-full bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white">
              <option>Default template</option>
              {templates.map(t => <option key={t.id}>{t.name}</option>)}
            </select>
          </div>
          <button
            onClick={startPipeline}
            disabled={isProcessing}
            className="bg-purple-600 hover:bg-purple-500 text-white px-6 py-2 rounded-lg font-semibold flex items-center gap-2 disabled:opacity-50"
          >
            <Play className="h-4 w-4" /> {isProcessing ? 'Processing...' : 'Start Pipeline'}
          </button>
        </div>
        <div className="mt-6">
          <h2 className="text-xl font-bold text-white mb-4">Recent Videos</h2>
          <div className="space-y-2">
            {videos.map(v => <VideoRow key={v.id} video={v} isSelected={selectedVideoId === video.id} onSelect={() => setSelectedVideoId(v.id)} />)}
            {videos.length === 0 && <p className="text-slate-500 text-sm">No videos yet.</p>}
          </div>
        </div>
        <div className="mt-6">
          <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
            <Zap className="text-purple-500" /> Content Radar
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {trending.map((item) => (
              <div key={item.id} className="group relative rounded-xl overflow-hidden bg-slate-900/50 border border-slate-800 hover:border-purple-500/50 transition-all duration-300">
                <div className="relative aspect-video overflow-hidden">
                  <img src={item.thumbnail} alt={item.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                  <div className="absolute inset-0 bg-gradient-to-t from-slate-950 to-transparent opacity-80" />
                  <span className="absolute bottom-2 right-2 bg-black/70 text-white text-xs px-2 py-1 rounded backdrop-blur-sm">{item.duration}</span>
                  <span className="absolute top-2 left-2 bg-purple-600 text-white text-xs font-bold px-2 py-1 rounded shadow-lg">{item.source}</span>
                </div>
                <div className="p-4">
                  <h3 className="font-semibold text-white line-clamp-1">{item.title}</h3>
                  <p className="text-xs text-slate-400 mt-1">{item.views} views</p>
                  <button className="w-full mt-4 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-sm font-semibold py-2 rounded-lg transition-all shadow-lg shadow-purple-900/20">⚡ Auto-Ingest & Process</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
