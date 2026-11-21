const { contextBridge } = require("electron");

const prefix = "--indagar-server=";
const argument = process.argv.find((value) => value.startsWith(prefix));

contextBridge.exposeInMainWorld("indagarDesktop", {
  serverUrl: argument ? argument.slice(prefix.length) : "",
  platform: process.platform,
});
