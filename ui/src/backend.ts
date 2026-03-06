import { spawn, type ChildProcess } from "node:child_process";
import { createInterface, type Interface } from "node:readline";
import { EventEmitter } from "node:events";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import type { BackendEvent } from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(__dirname, "..", "..");
const BRIDGE_SCRIPT = resolve(PROJECT_ROOT, "scripts", "chat_bridge.py");

export class Backend extends EventEmitter {
  private proc: ChildProcess | null = null;
  private rl: Interface | null = null;
  private _ready = false;

  get ready(): boolean {
    return this._ready;
  }

  start(): void {
    const venvPython = resolve(PROJECT_ROOT, ".venv", "bin", "python");
    const pythonCmd = process.env["PYTHON_PATH"] ?? venvPython;

    this.proc = spawn(pythonCmd, [BRIDGE_SCRIPT], {
      cwd: PROJECT_ROOT,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        TRANSFORMERS_VERBOSITY: "error",
      },
    });

    this.rl = createInterface({ input: this.proc.stdout! });
    this.rl.on("line", (line: string) => {
      if (!line.trim()) return;
      try {
        const event: BackendEvent = JSON.parse(line);
        if (event.type === "config" || event.type === "model_loaded") {
          this._ready = true;
        }
        this.emit("event", event);
        this.emit(event.type, event.data);
      } catch {
        // non-JSON output from Python
      }
    });

    this.proc.stderr?.on("data", () => {
      // suppress stderr noise from model loading
    });

    this.proc.on("close", (code) => {
      this.emit("event", { type: "exit", data: { code } });
      this.emit("exit", code);
    });

    this.proc.on("error", (err) => {
      this.emit("event", { type: "error", data: { message: err.message } });
      this.emit("error", err);
    });
  }

  send(action: string, data?: unknown): void {
    if (!this.proc?.stdin?.writable) return;
    const msg = JSON.stringify({ action, ...((data as object) ?? {}) });
    this.proc.stdin.write(msg + "\n");
  }

  sendMessage(text: string): void {
    this.send("chat", { text });
  }

  quit(): void {
    this.send("quit");
    const onFinalized = () => {
      clearTimeout(fallback);
      setTimeout(() => this.proc?.kill("SIGTERM"), 500);
    };
    this.once("finalize_done", onFinalized);
    const fallback = setTimeout(() => {
      this.removeListener("finalize_done", onFinalized);
      this.proc?.kill("SIGTERM");
    }, 300_000);
  }

  kill(): void {
    this.proc?.kill("SIGKILL");
  }
}
