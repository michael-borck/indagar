const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

if (process.env.INDAGAR_DESKTOP_USER_DATA) {
  app.setPath("userData", process.env.INDAGAR_DESKTOP_USER_DATA);
}

let serverProcess = null;
let mainWindow = null;
let setupWindow = null;
let setupLogs = [];
let serverUrl = "";
let enginePath = "";
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

function sidecarRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "sidecar")
    : path.join(__dirname, "sidecar");
}

function findSystemIndagar() {
  if (process.env.INDAGAR_BIN) return process.env.INDAGAR_BIN;
  const candidates = [
    path.join(process.env.HOME || "", ".local", "bin", "indagar"),
    "/opt/homebrew/bin/indagar",
    "/usr/local/bin/indagar",
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return "";
}

function venvBin(venv, executable) {
  return process.platform === "win32"
    ? path.join(venv, "Scripts", `${executable}.exe`)
    : path.join(venv, "bin", executable);
}

function bundledUv() {
  let name = "uv-x64";
  if (process.platform === "win32") {
    name = "uv-x64.exe";
  } else if (process.platform === "darwin" && process.arch === "arm64") {
    name = "uv-arm64";
  }
  return path.join(sidecarRoot(), "uv", name);
}

function enginePaths() {
  const runtime = path.join(app.getPath("userData"), "engine");
  const venv = path.join(runtime, "venv");
  return {
    runtime,
    venv,
    marker: path.join(runtime, "version"),
    engine: venvBin(venv, "indagar"),
    python: venvBin(venv, "python"),
  };
}

function installedEngineVersion() {
  const paths = enginePaths();
  if (!fs.existsSync(paths.engine) || !fs.existsSync(paths.marker)) return "";
  try {
    return fs.readFileSync(paths.marker, "utf8").trim();
  } catch {
    return "";
  }
}

function engineNeedsInstall() {
  if (process.env.INDAGAR_BIN) return false;
  if (!app.isPackaged && findSystemIndagar()) return false;
  const uv = bundledUv();
  if (!fs.existsSync(uv)) return false;
  return installedEngineVersion() !== app.getVersion();
}

function setupLog(line) {
  const value = String(line).replace(/\s+$/, "");
  if (!value) return;
  console.log(`[setup] ${value}`);
  setupLogs.push(value);
  if (setupLogs.length > 200) setupLogs = setupLogs.slice(-200);
  setupWindow?.webContents.send("setup:log", value);
}

function runCommand(command, args, env, onLog) {
  return new Promise((resolve, reject) => {
    const proc = spawn(command, args, {
      env: { ...process.env, ...env },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    let buffer = "";
    const consume = (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.trim()) onLog(line);
      }
    };
    proc.stdout.on("data", consume);
    proc.stderr.on("data", consume);
    proc.on("error", reject);
    proc.on("exit", (code) => {
      if (buffer.trim()) onLog(buffer);
      if (code === 0) resolve();
      else reject(new Error(`${path.basename(command)} exited with code ${code}`));
    });
  });
}

async function ensureEngine() {
  if (process.env.INDAGAR_BIN) return process.env.INDAGAR_BIN;

  const paths = enginePaths();
  if (installedEngineVersion() === app.getVersion() && fs.existsSync(paths.engine)) {
    return paths.engine;
  }

  const uv = bundledUv();
  const wheelDir = path.join(sidecarRoot(), "wheel");
  if (!fs.existsSync(uv) || !fs.existsSync(wheelDir)) {
    const system = findSystemIndagar();
    if (system) return system;
    throw new Error(
      "Indagar's bundled Python engine is missing from this build. Reinstall the app.",
    );
  }

  if (process.platform !== "win32") {
    try {
      fs.chmodSync(uv, 0o755);
    } catch {
      // Packaging normally preserves the executable bit.
    }
  }

  fs.mkdirSync(paths.runtime, { recursive: true });
  const env = {
    UV_PYTHON_INSTALL_DIR: path.join(paths.runtime, "python"),
    UV_CACHE_DIR: path.join(paths.runtime, "cache"),
    UV_PYTHON_PREFERENCE: "only-managed",
    UV_LINK_MODE: "copy",
    UV_NO_PROGRESS: "1",
  };

  setupLog(`Preparing the local research engine (${app.getVersion()})…`);
  await runCommand(uv, ["python", "install", "3.12"], env, setupLog);
  await runCommand(
    uv,
    ["venv", "--python", "3.12", "--python-preference", "only-managed", paths.venv],
    env,
    setupLog,
  );
  await runCommand(
    uv,
    [
      "pip",
      "install",
      "--python",
      paths.python,
      "--upgrade",
      "--find-links",
      wheelDir,
      `indagar[web,media]==${app.getVersion()}`,
    ],
    env,
    setupLog,
  );
  fs.writeFileSync(paths.marker, `${app.getVersion()}\n`, "utf8");
  setupLog("Engine ready.");
  return paths.engine;
}

function createSetupWindow() {
  setupWindow = new BrowserWindow({
    width: 560,
    height: 380,
    resizable: false,
    maximizable: false,
    title: "Indagar Setup",
    backgroundColor: "#0f766e",
    webPreferences: {
      preload: path.join(__dirname, "setup-preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  setupWindow.on("closed", () => {
    setupWindow = null;
  });
  setupWindow.webContents.on("did-finish-load", () => {
    for (const line of setupLogs) {
      setupWindow?.webContents.send("setup:log", line);
    }
  });
  setupWindow.loadFile(path.join(__dirname, "setup.html"));
}

function closeSetupWindow() {
  if (setupWindow && !setupWindow.isDestroyed()) setupWindow.close();
  setupWindow = null;
}

async function waitForHealth(url, timeoutMs = 60000) {
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
  const binary = enginePath || findSystemIndagar() || "indagar";
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
    const smoke = process.env.INDAGAR_DESKTOP_SMOKE === "1";
    const needsInstall = engineNeedsInstall();
    if (needsInstall && !smoke) createSetupWindow();
    enginePath = await ensureEngine();
    closeSetupWindow();
    await startServer();
    if (smoke) {
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
    closeSetupWindow();
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
