// Lets the app import plain TypeScript shared with the website (guide text, formatting, debt
// reminder wording, API types) straight from ../frontend/src, so the two never drift apart.
const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
config.watchFolders = [path.resolve(__dirname, '../frontend/src')];
// The shared files import no packages at run time (only `import type`), so nothing is resolved
// from the website's node_modules.

module.exports = config;
