const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

let serverProcess = null;
let mainWindow = null;
let serverUrl = "";
let quitting = false;

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

function resolveIndagar() {
  if (process.env.INDAGAR_BIN) return process.env.INDAGAR_BIN;
  const candidates = [
    path.join(process.env.HOME || "", ".local", "bin", "indagar"),
    "/opt/homebrew/bin/indagar",
    "/usr/local/bin/indagar",
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return "indagar";
}

async function waitForHealth(url, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${url}/api/health`);
      if (response.ok) return;
    } catch {
      // Server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("The Indagar server did not become ready.");
}

async function startServer() {
  const port = await findFreePort();
  serverUrl = `http://127.0.0.1:${port}`;
  const binary = resolveIndagar();
  console.log(`[indagar] ${binary} serve --host 127.0.0.1 --port ${port}`);
  serverProcess = spawn(
    binary,
    ["serve", "--host", "127.0.0.1", "--port", String(port)],
    {
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  serverProcess.stdout.on("data", (data) => process.stdout.write(`[server] ${data}`));
  serverProcess.stderr.on("data", (data) => process.stderr.write(`[server] ${data}`));
  serverProcess.on("exit", (code) => {
    if (!quitting && code) {
      console.error(`[indagar] server exited with code ${code}`);
    }
  });
  await new Promise((resolve, reject) => {
    serverProcess.once("spawn", resolve);
    serverProcess.once("error", reject);
  });
  await waitForHealth(serverUrl);
}

function stopServer() {
  if (!serverProcess || serverProcess.killed) {
    serverProcess = null;
    return;
  }
  const processToStop = serverProcess;
  serverProcess = null;
  processToStop.kill("SIGTERM");
  setTimeout(() => {
    if (!processToStop.killed) processToStop.kill("SIGKILL");
  }, 3000).unref();
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 980,
    minHeight: 700,
    title: "Indagar",
    backgroundColor: "#f3f5f7",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--indagar-server=${serverUrl}`],
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(serverUrl)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
  await mainWindow.loadURL(serverUrl);
}

function setupAutoUpdater() {
  if (!app.isPackaged) return;
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.logger = console;
  autoUpdater.on("error", (error) => {
    console.error("[updates]", error);
  });
  autoUpdater.on("update-available", (info) => {
    console.log(`[updates] available ${info.version}`);
  });
  autoUpdater.on("update-downloaded", (info) => {
    console.log(`[updates] downloaded ${info.version}`);
  });
  autoUpdater.checkForUpdatesAndNotify().catch((error) => {
    console.error("[updates]", error);
  });
  const timer = setInterval(() => {
    autoUpdater.checkForUpdatesAndNotify().catch((error) => {
      console.error("[updates]", error);
    });
  }, 6 * 60 * 60 * 1000);
  timer.unref();
}

function buildMenu() {
  const template = [
    ...(process.platform === "darwin" ? [{ role: "appMenu" }] : []),
    { label: "File", submenu: [{ role: "close" }, { role: "quit" }] },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
      ],
    },
    {
      role: "help",
      submenu: [
        {
          label: "Check for Updates…",
          click: () => {
            if (!app.isPackaged) {
              dialog.showMessageBox({
                message: "Updates are checked in packaged builds.",
              });
              return;
            }
            autoUpdater.checkForUpdatesAndNotify().catch((error) => {
              dialog.showErrorBox("Update check failed", String(error));
            });
          },
        },
        {
          label: "Indagar on GitHub",
          click: () => shell.openExternal("https://github.com/michael-borck/indagar"),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(async () => {
  try {
    await startServer();
    if (process.env.INDAGAR_DESKTOP_SMOKE === "1") {
      console.log(`SMOKE_OK ${serverUrl}`);
      stopServer();
      app.quit();
      return;
    }
    buildMenu();
    await createWindow();
    setupAutoUpdater();
  } catch (error) {
    console.error(error);
    dialog.showErrorBox("Indagar could not start", String(error));
    stopServer();
    app.quit();
  }
});

app.on("before-quit", () => {
  quitting = true;
  stopServer();
});

app.on("window-all-closed", () => {
  stopServer();
  app.quit();
});
