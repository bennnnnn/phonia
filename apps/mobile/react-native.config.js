// `pnpm ios:sim` (PHONIA_IOS_SIMULATOR=1) links ML Kit out: its frameworks carry an Intel
// simulator slice only, so they force an Intel build that an Apple-silicon iOS 26 simulator
// refuses to install. app.config.ts leaves its plugin out too. Every other build links it.
const simulator = process.env.PHONIA_IOS_SIMULATOR?.trim() === "1";

module.exports = simulator
  ? { dependencies: { "react-native-vision-camera-mlkit": { platforms: { ios: null } } } }
  : {};
