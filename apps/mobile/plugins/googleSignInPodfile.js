const { withDangerousMod } = require("expo/config-plugins");
const fs = require("fs");
const path = require("path");

/** AppCheckCore (Google Sign-In) needs modular headers on GoogleUtilities. */
function withGoogleSignInPodfile(config) {
  return withDangerousMod(config, [
    "ios",
    async (cfg) => {
      const podfilePath = path.join(cfg.modRequest.platformProjectRoot, "Podfile");
      let contents = await fs.promises.readFile(podfilePath, "utf8");
      const patch =
        "\n  pod 'GoogleUtilities', :modular_headers => true\n  pod 'RecaptchaInterop', :modular_headers => true\n";

      if (!contents.includes("GoogleUtilities', :modular_headers")) {
        contents = contents.replace("  use_expo_modules!\n", `  use_expo_modules!${patch}`);
        await fs.promises.writeFile(podfilePath, contents);
      }
      return cfg;
    },
  ]);
}

module.exports = withGoogleSignInPodfile;
