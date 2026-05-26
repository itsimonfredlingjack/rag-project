import { contextBridge } from "electron";

// Safe API exposition for renderer process
contextBridge.exposeInMainWorld("electronAPI", {
  platform: process.platform,
});
