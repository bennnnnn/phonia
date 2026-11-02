Vendored `image-size` for Metro (`metro` → `image-size@1.2.1`).

Upstream has no release past 2.0.2 that fixes GHSA-5p2g-fcmc-qvqq / GHSA-w3rx-r6r6-pgpr.
This copy keeps the 1.x CJS API Metro expects, applies the ICNS/JXL loop guards, and
reports version 2.0.3 so Dependabot’s `<= 2.0.2` range clears.

Remove when upstream publishes a real patched release and Expo/Metro adopt it.
