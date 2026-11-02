const { withEntitlementsPlist } = require("expo/config-plugins");

/**
 * `pnpm ios:sim`: drop Sign in with Apple's entitlement, which makes Expo demand a
 * signing certificate even for a simulator. Expo applies the Apple plugin on its own
 * once the package is installed, after the app's plugins, so this mod runs after it.
 */
function withoutAppleSignIn(config) {
  return withEntitlementsPlist(config, (cfg) => {
    delete cfg.modResults["com.apple.developer.applesignin"];
    return cfg;
  });
}

module.exports = withoutAppleSignIn;
