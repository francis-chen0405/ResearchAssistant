'use strict';
// Opt-in Developer ID candidate only; credentials stay in the local Keychain.
const path = require('node:path');
const base = require('./package.json').build;
if (!process.env.CSC_NAME || !process.env.APPLE_KEYCHAIN_PROFILE) {
  throw new Error('Signed delivery requires CSC_NAME and an existing local APPLE_KEYCHAIN_PROFILE');
}
module.exports = {
  ...base,
  forceCodeSigning: true,
  mac: {
    ...base.mac,
    identity: process.env.CSC_NAME,
    hardenedRuntime: true,
    notarize: true,
    entitlements: path.join(__dirname, 'release-entitlements.plist'),
    entitlementsInherit: path.join(__dirname, 'release-entitlements.plist'),
  },
};
