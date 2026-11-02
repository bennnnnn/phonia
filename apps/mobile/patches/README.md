# Dependency compatibility patches

`decode-uri-component@0.5.0.patch` keeps the upstream security fix while exposing the
package as CommonJS for Expo Router's `query-string@7` dependency. It changes only
the package module type and export declaration; the decoding algorithm is unchanged.
The patched release addresses [GHSA-vcc3-ghjq-m6fr](https://github.com/advisories/GHSA-vcc3-ghjq-m6fr).

Remove this patch when Expo Router supports a query-string version that imports the
decoder's ESM default export. Run the URL dependency regression test and Metro exports
when updating either package. The test exercises the actual Expo dependency chain,
including a bounded malformed-input case.

`react-native-vision-camera-mlkit@2.0.1.patch` lets the iOS app build with barcode scanning
off (`app.json` sets `barcodeScanning: false`). Two bridge files use the barcode types without
the `MLKIT_BARCODE_SCANNING` guard the library puts on every other barcode file, so Swift fails
with "cannot find type 'BarcodeScanningOptions'". The patch adds that guard and changes nothing
else. Remove it when the library guards those files itself.

The existing draggable-flatlist patch is separate and remains unchanged.
