/**
 * The component test environment, plus `setTestTimeZone(zone)`: a test moves the
 * process to another IANA zone, and local `Date` fields and Intl's default zone both
 * follow (Node re-reads TZ when process.env.TZ is assigned). A test only sees a copy
 * of process.env, so this environment, which runs in the worker, sets the real one and
 * puts it back when the file ends. Opt in at the top of a `.test.tsx` file:
 * `@jest-environment ./jest.timeZoneEnvironment.js`.
 */
const ReactNativeEnv = require("@react-native/jest-preset/jest/react-native-env.js");

module.exports = class TimeZoneEnvironment extends ReactNativeEnv {
  constructor(config, context) {
    super(config, context);
    this.initialTimeZone = process.env.TZ;
    this.global.setTestTimeZone = (zone) => {
      process.env.TZ = zone;
    };
  }

  async teardown() {
    if (this.initialTimeZone === undefined) delete process.env.TZ;
    else process.env.TZ = this.initialTimeZone;
    await super.teardown();
  }
};
