// Tauri 2.0 IPC bridge — all helpers check isTauri() before calling native APIs.
// Safe to import in browser context: all methods degrade gracefully to no-ops.

export const isTauri = (): boolean =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

// Generic invoke — returns null in browser context
export async function tauriInvoke<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T | null> {
  if (!isTauri()) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<T>(cmd, args);
  } catch {
    return null;
  }
}

// Native notification (requires tauri-plugin-notification)
export async function showNativeNotification(
  title: string,
  body: string,
): Promise<void> {
  if (!isTauri()) return;
  try {
    const { sendNotification, isPermissionGranted, requestPermission } =
      await import("@tauri-apps/plugin-notification");
    let ok = await isPermissionGranted();
    if (!ok) {
      const r = await requestPermission();
      ok = r === "granted";
    }
    if (ok) sendNotification({ title, body });
  } catch {
    // Not in Tauri context or permission denied — ignore
  }
}

// Auto-launch helpers (requires tauri-plugin-autostart)
export async function getAutolaunch(): Promise<boolean> {
  if (!isTauri()) return false;
  try {
    const { isEnabled } = await import("@tauri-apps/plugin-autostart");
    return await isEnabled();
  } catch {
    return false;
  }
}

export async function setAutolaunch(enable: boolean): Promise<void> {
  if (!isTauri()) return;
  try {
    const { enable: pluginEnable, disable: pluginDisable } =
      await import("@tauri-apps/plugin-autostart");
    if (enable) {
      await pluginEnable();
    } else {
      await pluginDisable();
    }
  } catch {
    // Ignore in browser
  }
}

// Return the platform-specific Majestic data directory path
export async function getDataDir(): Promise<string> {
  return (await tauriInvoke<string>("get_data_dir")) ?? "";
}

// Read agent token from data/agent_token — empty string if absent
export async function readAgentToken(): Promise<string> {
  return (await tauriInvoke<string>("read_agent_token")) ?? "";
}

// Start the agent background process for a given profile
export async function startAgent(profile = "default"): Promise<void> {
  await tauriInvoke("start_agent", { profile });
}

// Check Python installation — returns { ok, version } where ok = Python ≥ 3.11
export async function checkPython(): Promise<{ ok: boolean; version: string }> {
  if (!isTauri()) return { ok: false, version: "" };
  const version = await tauriInvoke<string>("check_python");
  if (!version) return { ok: false, version: "" };
  const m = version.match(/(\d+)\.(\d+)/);
  if (!m) return { ok: false, version };
  const [major, minor] = [parseInt(m[1]), parseInt(m[2])];
  return { ok: major > 3 || (major === 3 && minor >= 11), version };
}
