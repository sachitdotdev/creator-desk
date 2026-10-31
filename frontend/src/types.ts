export interface Video {
  id: number;
  filename: string;
  original_name: string;
  path: string;
  duration: number | null;
  fps: number | null;
  width: number | null;
  height: number | null;
  status: string;
  transcript_path: string | null;
  created_at: string;
}

export interface Template {
  id: number;
  name: string;
  description: string | null;
  config: TemplateConfig;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface TemplateConfig {
  vibe?: string;
  colors?: {
    primary?: string;
    accent?: string;
    background?: string;
    highlight?: string;
  };
  caption?: {
    font?: string;
    size?: number;
    bold?: number;
    primary?: string;
    outline?: string;
    back?: string;
    alignment?: number;
    margin_v?: number;
    outline_w?: number;
    shadow?: number;
    highlight_color?: string;
    karaoke?: boolean;
    kinetic?: boolean;
  };
  title?: {
    font?: string;
    size?: number;
    bold?: number;
    color?: string;
    position?: string;
    margin_v?: number;
    outline_w?: number;
    glow?: boolean;
    text?: string;
  };
  watermark?: {
    text?: string;
    font?: string;
    size?: number;
    color?: string;
    opacity?: number;
    position?: string;
    margin_x?: number;
    margin_y?: number;
  };
  background?: {
    mode?: string;
    blur_amount?: number;
    color?: string;
  };
}

export interface Clip {
  id: number;
  video_id: number;
  template_id: number | null;
  start_time: number;
  end_time: number;
  duration: number;
  title: string | null;
  description: string | null;
  hashtags: string | null;
  hook: string | null;
  status: string;
  file_path: string | null;
  thumbnail_path: string | null;
  error_message: string | null;
  progress: number;
  created_at: string;
  updated_at: string;
}

export interface Schedule {
  id: number;
  clip_id: number;
  account_id: number | null;
  platform: string;
  scheduled_at: string;
  status: string;
  posted_at: string | null;
}

export interface SocialAccount {
  id: number;
  platform: string;
  account_name: string;
  channel_id: string | null;
  status: string;
  connected: boolean;
  created_at: string;
}

export const SOCIAL_PLATFORMS: { id: string; label: string; icon: string }[] = [
  { id: "youtube", label: "YouTube Shorts", icon: "Youtube" },
  { id: "tiktok", label: "TikTok", icon: "Smartphone" },
  { id: "instagram", label: "Instagram Reels", icon: "Instagram" },
];
