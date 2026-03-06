import React, { useState, useEffect, useCallback, useRef } from "react";
import { Box, Text, useApp } from "ink";
import {
  Banner,
  ModelList,
  LoadingBar,
  ContextBar,
  InputBox,
  MessageView,
  ThinkingIndicator,
  StreamingMessage,
  MemoryIndicator,
} from "./components/index.js";
import { Backend } from "./backend.js";
import { theme } from "./theme.js";
import type {
  ChatMessage,
  ModelStatus,
  AppConfig,
  ContextInfo,
} from "./types.js";

type AppPhase = "init" | "loading" | "ready" | "exiting";

export const App: React.FC = () => {
  const { exit } = useApp();
  const backendRef = useRef<Backend | null>(null);

  const [phase, setPhase] = useState<AppPhase>("init");
  const [config, setConfig] = useState<AppConfig>({
    assistant_name: "Assistant",
    user_name: "You",
  });
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [modelName, setModelName] = useState("");
  const [loadProgress, setLoadProgress] = useState({ loaded: 0, total: 0 });
  const [contextInfo, setContextInfo] = useState<ContextInfo>({});
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [thinking, setThinking] = useState(false);
  const [thinkingStart, setThinkingStart] = useState(0);
  const [streamContent, setStreamContent] = useState("");
  const [memoryActive, setMemoryActive] = useState(false);
  const [memoryDone, setMemoryDone] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const backend = new Backend();
    backendRef.current = backend;

    backend.on("config", (data: unknown) => {
      const d = data as AppConfig;
      setConfig({
        assistant_name: d.assistant_name || "Assistant",
        user_name: d.user_name || "You",
      });
    });

    backend.on("models", (data: unknown) => {
      const d = data as { models: ModelStatus[] };
      setModels(d.models || []);
      setPhase("loading");
    });

    backend.on("load_progress", (data: unknown) => {
      const d = data as { loaded: number; total: number };
      setLoadProgress({ loaded: d.loaded, total: d.total });
    });

    backend.on("model_loaded", (data: unknown) => {
      const d = data as { model_name: string };
      setModelName(d.model_name || "");
      setPhase("ready");
    });

    backend.on("context_info", (data: unknown) => {
      setContextInfo(data as ContextInfo);
    });

    backend.on("reply_start", () => {
      setThinking(true);
      setThinkingStart(Date.now());
      setStreamContent("");
    });

    backend.on("reply_chunk", (data: unknown) => {
      const d = data as { text: string };
      setStreamContent((prev) => prev + d.text);
      setThinking(false);
    });

    backend.on("reply_end", (data: unknown) => {
      const d = data as { text: string; elapsed: number };
      setThinking(false);
      setStreamContent("");
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: d.text,
          elapsed: d.elapsed,
          timestamp: Date.now(),
        },
      ]);
    });

    backend.on("memory_update", (data: unknown) => {
      const d = data as { status: string };
      if (d.status === "start") {
        setMemoryActive(true);
        setMemoryDone(false);
      } else if (d.status === "done") {
        setMemoryActive(false);
        setMemoryDone(true);
        setTimeout(() => setMemoryDone(false), 3000);
      }
    });

    backend.on("error", (data: unknown) => {
      const d = data as { message?: string };
      setErrorMsg(d.message || "Unknown error");
      setThinking(false);
    });

    backend.on("exit", () => {
      setPhase("exiting");
      setTimeout(() => exit(), 500);
    });

    backend.start();

    return () => {
      backend.kill();
    };
  }, [exit]);

  const handleSubmit = useCallback(
    (text: string) => {
      if (!backendRef.current) return;

      const lower = text.toLowerCase();
      if (lower === "quit" || lower === "exit" || lower === "q") {
        setPhase("exiting");
        backendRef.current.quit();
        return;
      }

      setMessages((prev) => [
        ...prev,
        { role: "user", content: text, timestamp: Date.now() },
      ]);
      setErrorMsg("");
      backendRef.current.sendMessage(text);
    },
    []
  );

  const [exitFrame, setExitFrame] = useState(0);

  useEffect(() => {
    if (phase !== "exiting") return;
    const interval = setInterval(() => {
      setExitFrame((i) => (i + 1) % theme.sparkleFrames.length);
    }, 120);
    return () => clearInterval(interval);
  }, [phase]);

  if (phase === "exiting") {
    return (
      <Box paddingLeft={2} paddingBottom={1}>
        <Text color={theme.colors.primary}>
          {theme.sparkleFrames[exitFrame]}
        </Text>
        <Text color={theme.colors.warning}>Saving memory…</Text>
        <Text color={theme.colors.primary}>
          {theme.sparkleFrames[(exitFrame + 4) % theme.sparkleFrames.length]}
        </Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      {/* Init / loading phase */}
      {(phase === "init" || phase === "loading") && (
        <Box flexDirection="column">
          {models.length > 0 && <ModelList models={models} />}
          <LoadingBar
            loaded={loadProgress.loaded}
            total={loadProgress.total}
            label={phase === "init" ? "Starting..." : "Loading..."}
          />
        </Box>
      )}

      {/* Ready phase */}
      {phase === "ready" && (
        <Box flexDirection="column">
          <Banner modelName={modelName} />
          <ContextBar context={contextInfo} />

          {/* Message history */}
          {messages.map((msg, i) => (
            <MessageView key={i} message={msg} config={config} />
          ))}

          {/* Streaming response */}
          {streamContent && !thinking && (
            <StreamingMessage
              name={config.assistant_name}
              content={streamContent}
            />
          )}

          {/* Thinking indicator */}
          {thinking && (
            <Box flexDirection="column">
              <ThinkingIndicator
                name={config.assistant_name}
                startTime={thinkingStart}
              />
            </Box>
          )}

          {/* Memory update indicator */}
          {(memoryActive || memoryDone) && (
            <MemoryIndicator active={memoryActive} done={memoryDone} />
          )}

          {/* Error display */}
          {errorMsg && (
            <Box paddingLeft={1}>
              <Text color={theme.colors.error}>Error: {errorMsg}</Text>
            </Box>
          )}

          {/* Input */}
          <Box marginTop={1}>
            <InputBox
              onSubmit={handleSubmit}
              disabled={thinking || !!streamContent}
              placeholder="Type your message..."
            />
          </Box>
        </Box>
      )}
    </Box>
  );
};
