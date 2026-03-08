export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: number;
  elapsed?: number;
}

export interface ModelStatus {
  name: string;
  kind: "mlx" | "transformers";
  status: "local" | "cached" | "not_found";
  selected: boolean;
  adapter?: boolean;
  adapter_name?: string | null;
}

export interface AppConfig {
  assistant_name: string;
  user_name: string;
}

export interface BackendEvent {
  type:
    | "config"
    | "models"
    | "model_loaded"
    | "load_progress"
    | "context_info"
    | "reply_start"
    | "reply_chunk"
    | "reply_end"
    | "memory_update"
    | "error"
    | "exit";
  data: unknown;
}

export interface ContextInfo {
  date?: string;
  location?: string;
  weather?: string;
  weather_desc?: string;
}
