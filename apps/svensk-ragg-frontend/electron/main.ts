import { app, BrowserWindow } from "electron";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow: BrowserWindow | null = null;

function isWslRuntime(): boolean {
  if (process.platform !== "linux") return false;
  if (process.env.WSL_DISTRO_NAME || process.env.WSL_INTEROP) return true;

  try {
    const procVersion = fs.readFileSync("/proc/version", "utf8").toLowerCase();
    return procVersion.includes("microsoft") || procVersion.includes("wsl");
  } catch {
    return false;
  }
}

if (isWslRuntime()) {
  app.disableHardwareAcceleration();
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: "Svensk Ragg",
    backgroundColor: "#07090C",
    titleBarStyle: "hiddenInset", // Sleek modern titlebar on macOS
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  // Load Vite dev server URL in development, local index.html in production
  const isDev = process.env.NODE_ENV === "development";
  if (isDev) {
    mainWindow.loadURL("http://127.0.0.1:3003");
    if (process.env.ELECTRON_OPEN_DEVTOOLS === "1") {
      mainWindow.webContents.openDevTools();
    }
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
