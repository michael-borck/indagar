const fs = require("node:fs");
const path = require("node:path");

exports.default = async function afterPack(context) {
  // Universal mac builds run afterPack for the x64 and arm64 temp dirs first.
  // Only inject the sidecar into the merged/final app.
  if (context.appOutDir.includes("-temp")) return;

  const source = path.join(context.packager.projectDir, "sidecar");
  if (!fs.existsSync(source)) {
    throw new Error(
      "desktop/sidecar is missing. Run scripts/bundle_uv.py and build the Indagar wheel.",
    );
  }

  const product = context.packager.appInfo.productFilename || "Indagar";
  const resources =
    context.electronPlatformName === "darwin"
      ? path.join(context.appOutDir, `${product}.app`, "Contents", "Resources")
      : path.join(context.appOutDir, "resources");
  const target = path.join(resources, "sidecar");
  fs.rmSync(target, { recursive: true, force: true });
  fs.cpSync(source, target, { recursive: true });
  console.log(`[afterPack] sidecar -> ${target}`);
};
