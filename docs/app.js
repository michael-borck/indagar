const REPO = "michael-borck/indagar";
const RELEASE_BASE = `https://github.com/${REPO}/releases/latest/download/`;

const downloads = {
  mac: {
    label: "macOS",
    note: "Universal · macOS 11+ · right-click Open if Gatekeeper blocks",
    file: "Indagar-mac-universal.dmg",
    pattern: /mac.*\.dmg$/i,
  },
  win: {
    label: "Windows",
    note: "64-bit installer · Windows 10+",
    file: "Indagar-win-x64-setup.exe",
    pattern: /win.*setup\.exe$/i,
  },
  linux: {
    label: "Linux",
    note: "x64 AppImage · most desktop distributions",
    file: "Indagar-linux-x64.AppImage",
    pattern: /linux.*\.AppImage$/i,
  },
};

for (const item of Object.values(downloads)) {
  item.url = RELEASE_BASE + item.file;
}

const primary = document.getElementById("primary-download");
const primaryNote = document.getElementById("primary-note");
const cta = document.getElementById("cta-download");
const version = document.getElementById("release-version");
const platformLinks = [...document.querySelectorAll("[data-platform]")];

function detectPlatform() {
  const ua = navigator.userAgent;
  if (/Macintosh|Mac OS X/i.test(ua)) return "mac";
  if (/Windows/i.test(ua)) return "win";
  if (/Linux|X11/i.test(ua)) return "linux";
  return null;
}

function applyLinks(platform) {
  if (platform && downloads[platform]) {
    const item = downloads[platform];
    primary.hidden = false;
    primary.href = item.url;
    primary.textContent = `Download for ${item.label}`;
    primaryNote.textContent = item.note;
    cta.hidden = false;
    cta.href = item.url;
    cta.textContent = `Download for ${item.label}`;
    platformLinks.forEach((link) => {
      link.classList.toggle("current", link.dataset.platform === platform);
    });
  } else {
    primary.hidden = true;
    primaryNote.textContent = "Choose your platform below.";
    cta.hidden = true;
  }

  platformLinks.forEach((link) => {
    const item = downloads[link.dataset.platform];
    if (item) {
      link.href = item.url;
      link.title = `Download for ${item.label}`;
    }
  });
}

async function loadLatestRelease() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 6000);
    const response = await fetch(
      `https://api.github.com/repos/${REPO}/releases/latest`,
      {
        signal: controller.signal,
        headers: { Accept: "application/vnd.github+json" },
      },
    );
    clearTimeout(timer);
    if (!response.ok) return;
    const release = await response.json();
    const assets = Array.isArray(release.assets) ? release.assets : [];

    for (const item of Object.values(downloads)) {
      const asset = assets.find((candidate) => item.pattern.test(candidate.name));
      if (asset && asset.browser_download_url) {
        item.url = asset.browser_download_url;
      }
    }
    if (release.tag_name) {
      version.textContent = `Latest release ${release.tag_name}`;
    }
    applyLinks(detectPlatform());
  } catch {
    // Keep the fixed latest/download links and the generic version label.
  }
}

applyLinks(detectPlatform());
loadLatestRelease();
