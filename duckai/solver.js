#!/usr/bin/env node
/**
 * Duck.ai x-vqd-hash-1 solver using jsdom.
 * Usage: node solver.js <challenge.js> <userAgent>
 * Prints JSON: {server_hashes, client_hashes (raw), signals, meta}
 */
const fs = require('fs');
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
  ['offsetWidth', 17],
  ['offsetHeight', 35],
  ['scrollHeight', 19],
  ['clientWidth', 17],
  ['clientHeight', 35],
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
    width: 17,
    height: 35,
    top: 0,
    left: 0,
    right: 17,
    bottom: 35,
    x: 0,
    y: 0,
  };
};

(async () => {
  try {
    const result = await w.eval(src);
    process.stdout.write(JSON.stringify(result));
  } catch (e) {
    process.stdout.write(
      JSON.stringify({ __error: String((e && e.stack) || e) })
    );
    process.exit(1);
  }
})();
