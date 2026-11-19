#!/usr/bin/env node
/**
 * Duck.ai x-vqd-hash-1 solver (jsdom).
 * Usage: node solver.js <challenge.js> <userAgent>
 * Prints JSON: { solved, raw_client, server_hashes }
 */
const fs = require('fs');
const crypto = require('crypto');
const { JSDOM } = require('jsdom');

const src = fs.readFileSync(process.argv[2], 'utf8');
const UA =
  process.argv[3] ||
  'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36';

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'https://duck.ai/',
  userAgent: UA,
  runScripts: 'outside-only',
  pretendToBeVisual: true,
});
const w = dom.window;

try {
  Object.defineProperty(w.navigator, 'userAgent', {
    get: () => UA,
    configurable: true,
  });
  Object.defineProperty(w.navigator, 'appVersion', {
    get: () => UA.replace('Mozilla/', ''),
    configurable: true,
  });
  Object.defineProperty(w.navigator, 'webdriver', {
    get: () => false,
    configurable: true,
  });
} catch (e) {}

const proto = w.Element.prototype;
for (const [prop, val] of [
  ['offsetWidth', 24],
  ['offsetHeight', 24],
  ['scrollHeight', 24],
  ['clientWidth', 24],
  ['clientHeight', 24],
]) {
  Object.defineProperty(proto, prop, {
    get() {
      return this.__fake || val;
    },
    configurable: true,
  });
}
proto.getBoundingClientRect = function () {
  return {
    width: 24,
    height: 24,
    top: 0,
    left: 0,
    right: 24,
    bottom: 24,
    x: 0,
    y: 0,
  };
};

(async () => {
  try {
    const result = await w.eval(src);
    if (!result || !Array.isArray(result.client_hashes)) {
      process.stdout.write(
        JSON.stringify({ __error: 'bad challenge result', result })
      );
      process.exit(1);
    }

    const hashed = result.client_hashes.map((item) =>
      crypto.createHash('sha256').update(String(item)).digest('base64')
    );

    const payload = {
      server_hashes: result.server_hashes || [],
      client_hashes: hashed,
      signals: result.signals || {},
      meta: {
        ...(result.meta || {}),
        origin: 'https://duck.ai',
        stack: 'Error\n    at solve (native)',
        duration: String((result.meta && result.meta.duration) || '15'),
      },
    };

    // Match browser: btoa(JSON.stringify(...))
    const solved = Buffer.from(JSON.stringify(payload)).toString('base64');

    process.stdout.write(
      JSON.stringify({
        solved,
        raw_client: result.client_hashes,
        server_hashes: result.server_hashes || [],
      })
    );
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ __error: String((e && e.stack) || e) })
    );
    process.exit(1);
  }
})();
