#!/usr/bin/env node
/**
 * `pnpm ios:sim`: build the app and open it in the iOS Simulator, with no signing certificate.
 *
 * Sign in with Apple's entitlement makes Expo demand a development certificate even for a
 * simulator. PHONIA_IOS_SIMULATOR=1 leaves it out (app.config.ts); dev login and Google
 * still work. It also leaves out ML Kit, whose simulator slice is Intel only
 * (react-native.config.js); the live scanner is unavailable there. An ios/ folder that still
 * carries the entitlement or ML Kit is regenerated once.
 * Extra arguments go to `expo run:ios`: `pnpm ios:sim --device "iPhone 17 Pro Max"`.
 */
import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
// ios/ is generated and ignored by git, so regenerating it needs no git check.
const env = { ...process.env, PHONIA_IOS_SIMULATOR: "1", EXPO_NO_GIT_STATUS: "1" };

function iosHasAppleSignIn() {
  const ios = join(root, "ios");
  if (!existsSync(ios)) return false;
  return readdirSync(ios, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== "Pods")
    .flatMap((entry) =>
      readdirSync(join(ios, entry.name))
        .filter((file) => file.endsWith(".entitlements"))
        .map((file) => join(ios, entry.name, file)),
    )
    .some((file) => readFileSync(file, "utf8").includes("com.apple.developer.applesignin"));
}

function expo(args) {
  const result = spawnSync("expo", args, { cwd: root, env, stdio: "inherit" });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function iosHasMLKit() {
  const lock = join(root, "ios", "Podfile.lock");
  return existsSync(lock) && readFileSync(lock, "utf8").includes("VisionCameraMLKit");
}

if (iosHasAppleSignIn() || iosHasMLKit()) {
  console.log("Regenerating ios/ without Sign in with Apple and ML Kit, for the simulator.");
  expo(["prebuild", "--platform", "ios", "--clean"]);
}
expo(["run:ios", ...process.argv.slice(2)]);
