const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("setupAPI", {
  onLog: (callback) => {
    ipcRenderer.on("setup:log", (_event, line) => callback(String(line)));
  },
});
