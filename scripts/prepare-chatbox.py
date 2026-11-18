"""Apply MailPilot's changes to the pinned upstream source before electron-vite builds it."""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".build/chatbox"
COMMIT = "d3cd0ad1e6a1127bbbf3991bb5296c181f4cbdeb"
if not SRC.exists():
    subprocess.run(["git", "clone", "--depth", "1", "--branch", "v1.20.3",
                    "https://github.com/chatboxai/chatbox.git", str(SRC)], check=True)
if subprocess.check_output(["git", "-C", str(SRC), "rev-parse", "HEAD"], text=True).strip() != COMMIT:
    raise SystemExit("Unexpected Chatbox source revision")

def original(name):
    return subprocess.check_output(["git", "-C", str(SRC), "show", "HEAD:" + name]).decode()

# The CE tag retains unused commercial/test importer entries in its pnpm lock.
# Reconcile importer specifiers only, keeping every actual resolved package and integrity hash.
pkg = json.loads(original("package.json"))
lock = original("pnpm-lock.yaml")
before, middle = lock.split("  .:\n", 1)
importer, after = middle.split("  release/app:\n", 1)
groups = re.split(r"^    (\w+):\n", importer, flags=re.M)
rebuilt = groups[0]
for section, entries in zip(groups[1::2], groups[2::2]):
    items = re.split(r"^      ([^\n]+):\n", entries, flags=re.M)
    kept = []
    for quoted, spec in zip(items[1::2], items[2::2]):
        key = quoted.strip("'\"")
        if key in pkg.get(section, {}):
            target = pkg["pnpm"].get("overrides", {}).get(key, pkg[section][key])
            spec = re.sub(r"(?m)^        specifier: .+$", "        specifier: " + target, spec)
            kept.append("      " + quoted + ":\n" + spec)
    if kept:
        rebuilt += "    " + section + ":\n" + "".join(kept)
(SRC / "pnpm-lock.yaml").write_text(before + "  .:\n" + rebuilt + "\n  release/app:\n" + after, encoding="utf-8")
main = original("src/main/main.ts")
def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("Source mismatch: " + old[:70])
    return text.replace(old, new)
main = replace_once(main, "      ensureTray()", "      // MailPilot exits when its window closes.")
main = replace_once(main, "      new AppUpdater(() => mainWindow?.webContents.send('update-downloaded', {}))",
                    "      // MailPilot updates with the portable bundle.")
(SRC / "src/main/main.ts").write_text(main, encoding="utf-8")

# The public CE tag references four modules absent from its source tree.
# Keep the original model / request / MCP implementations and omit their unavailable siblings.
name = "src/shared/providers/index.ts"
(SRC / name).write_text(replace_once(original(name), "import './definitions/github-copilot'\n", ""), encoding="utf-8")
name = "src/renderer/stores/session/tools-builder.ts"
builder = re.sub(r"^import .*(?:toolsets/sandbox|skills/controller)'\n", "", original(name), flags=re.M)
builder = re.sub(r"  if \(sandboxEnabled\) \{[^}]*?\n  \}\n", "", builder)
builder = builder.replace("  if (sandboxEnabled) {\n    tools = { ...tools, ...sandboxToolSet.tools }\n  }\n", "")
left, rest = builder.split("  // Skills integration", 1)
builder = left + "  return { tools, instructions }\n}\n"
(SRC / name).write_text(builder, encoding="utf-8")
name = "src/renderer/components/chat/MessageErrTips.tsx"
tips = replace_once(original(name), "import { translateTexts } from '@/packages/translation'\n", "")
left, rest = tips.split("  const showTranslateButton = language", 1)
tips = left + "  const showTranslateButton = false\n  const handleTranslate = () => {}\n\n  if (!msg.error)" + rest.split("  if (!msg.error)", 1)[1]
(SRC / name).write_text(tips, encoding="utf-8")
name = "src/renderer/hooks/useOAuth.ts"
(SRC / name).write_text("""// The public CE provides API-key authentication.
const unavailable = async () => ({success: false, error: 'Provider OAuth is unavailable in Chatbox CE'})
export function useOAuth(..._args: unknown[]) {
  return {isDesktop: false, hasOAuth: false, isOAuthActive: false, flowType: undefined,
    loginCallback: unavailable, startLogin: unavailable, exchangeCode: unavailable,
    startDeviceFlow: unavailable, waitForDeviceToken: unavailable, cancel: unavailable,
    logout: unavailable, refreshToken: unavailable}
}
""", encoding="utf-8")
