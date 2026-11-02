module.exports = function (api) {
  // Re-evaluate when NODE_ENV flips so the test env gets its extra plugin.
  api.cache.using(() => process.env.NODE_ENV);
  const plugins = [];
  if (process.env.NODE_ENV === 'test') {
    // Jest (CJS) cannot execute native import(); Metro handles it in app
    // builds, so only lower it away for tests.
    plugins.push('@babel/plugin-transform-dynamic-import');
  }
  // VisionCamera frame callbacks and Reanimated 4 share the Worklets runtime.
  // Keep this last so worklet functions are transformed after other plugins.
  plugins.push('react-native-worklets/plugin');
  return {
    presets: ['babel-preset-expo'],
    plugins,
  };
};
