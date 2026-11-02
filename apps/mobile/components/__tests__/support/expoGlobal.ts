/**
 * The `expo` global that jest-expo's preset installs, with an inert stand-in
 * for each native module. This project runs the React Native preset, so a
 * test that loads the real Expo Router (its `testing-library`) imports this
 * first: the router reads optional native modules (linking, glass effect) as
 * it loads, and none of them is what such a test checks.
 */
import { installExpoGlobalPolyfill } from "expo-modules-core/src/polyfill/dangerous-internal";

installExpoGlobalPolyfill();

/** Every method answers nothing; a listener comes back removable. */
const inertModule: object = new Proxy(
  {},
  {
    get: (_target, name) =>
      name === "addListener" ? () => ({ remove: () => undefined }) : () => undefined,
  },
);

globalThis.expo.modules = new Proxy(globalThis.expo.modules, {
  get: (modules, name) => (name in modules ? Reflect.get(modules, name) : inertModule),
});
