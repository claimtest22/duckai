'use strict';
const vm = require('node:vm');
const crypto = require('node:crypto');

function nativeFn(name, impl) {
  const f = impl || function () {};
  try { Object.defineProperty(f, 'name', { value: name }); } catch (_) {}
  f.toString = () => `function ${name}() { [native code] }`;
  return f;
}

class Element {}
class HTMLElement extends Element {}
class HTMLDivElement extends HTMLElement {}
class HTMLIFrameElement extends HTMLElement {}

function NodeListFrom(arr) {
  const n = Object.create(Array.prototype);
  for (let i = 0; i < arr.length; i++) n[i] = arr[i];
  n.length = arr.length;
  return n;
}

function parseChildCount(html) {
  const tags = String(html).match(/<[a-zA-Z][^>]*>/g) || [];
  return tags.filter((t) => !t.startsWith('</')).length;
}

function makeDiv() {
  const el = new HTMLDivElement();
  let html = '';
  let text = '';
  el.style = { cssText: '' };
  Object.defineProperty(el, 'innerHTML', {
    get() { return html; },
    set(v) {
      html = String(v);
      text = html.replace(/<[^>]+>/g, '');
    },
  });
  Object.defineProperty(el, 'outerHTML', {
    get() { return html; },
    set(v) { html = String(v); },
  });
  Object.defineProperty(el, 'textContent', {
    get() { return text; },
    set(v) {
      text = String(v);
      html = text;
    },
  });
  Object.defineProperty(el, 'innerText', {
    get() { return text; },
    set(v) {
      text = String(v);
      html = text;
    },
  });
  Object.defineProperty(el, 'offsetWidth', { get() { return 24; } });
  Object.defineProperty(el, 'offsetHeight', { get() { return 24; } });
  Object.defineProperty(el, 'scrollHeight', { get() { return 24; } });
  Object.defineProperty(el, 'clientWidth', { get() { return 24; } });
  Object.defineProperty(el, 'clientHeight', { get() { return 24; } });
  el.getBoundingClientRect = nativeFn('getBoundingClientRect', () => ({
    width: 24, height: 24, top: 0, left: 0, right: 24, bottom: 24, x: 0, y: 0,
  }));
  el.querySelector = nativeFn('querySelector', () => null);
  el.querySelectorAll = nativeFn('querySelectorAll', (sel) => {
    if (sel === '*') {
      const count = parseChildCount(html);
      return NodeListFrom(Array.from({ length: count }, () => makeDiv()));
    }
    return NodeListFrom([]);
  });
  el.getAttribute = nativeFn('getAttribute', () => null);
  el.setAttribute = nativeFn('setAttribute', () => {});
  el.appendChild = nativeFn('appendChild', (c) => c);
  el.removeChild = nativeFn('removeChild', (c) => c);
  return el;
}

function makeIframe() {
  const el = new HTMLIFrameElement();
  const WindowFn = nativeFn('Window', function Window() {});
  const selfObj = { Window: WindowFn, Proxy: {} };
  Object.defineProperty(el, 'srcdoc', {
    get() { return el._srcdoc || ''; },
    set(v) { el._srcdoc = String(v); },
  });
  Object.defineProperty(el, 'src', {
    get() { return el._src || ''; },
    set(v) { el._src = String(v); },
  });
  Object.defineProperty(el, 'contentWindow', {
    get() {
      return { self: selfObj, Window: WindowFn, document: { body: {} } };
    },
  });
  el.querySelector = nativeFn('querySelector', () => null);
  el.querySelectorAll = nativeFn('querySelectorAll', () => NodeListFrom([]));
  el.getAttribute = nativeFn('getAttribute', () => null);
  return el;
}

async function solve(raw, ua) {
  const children = [];
  const document = {
    body: {
      children,
      appendChild: nativeFn('appendChild', (el) => {
        children.push(el);
        return el;
      }),
      removeChild: nativeFn('removeChild', (el) => {
        const i = children.indexOf(el);
        if (i >= 0) children.splice(i, 1);
        return el;
      }),
    },
    documentElement: { clientWidth: 1920, clientHeight: 1080 },
    createElement: nativeFn('createElement', (tag) => {
      const t = String(tag).toLowerCase();
      if (t === 'iframe') return makeIframe();
      return makeDiv();
    }),
    querySelector: nativeFn('querySelector', () => null),
    querySelectorAll: nativeFn('querySelectorAll', () => NodeListFrom([])),
  };

  const windowObj = {
    document,
    parseInt,
    Error,
    Math,
    Array,
    Object,
    String,
    Number,
    JSON,
    Promise,
    Symbol,
    isFinite,
    isNaN,
    parseFloat,
    decodeURIComponent,
    encodeURIComponent,
    getComputedStyle: nativeFn('getComputedStyle', () => ({
      getPropertyValue: nativeFn('getPropertyValue', (p) => (p === 'display' ? 'inline-block' : '')),
    })),
    innerWidth: 1920,
    innerHeight: 1080,
    outerWidth: 1920,
    outerHeight: 1080,
    devicePixelRatio: 1,
    screen: {
      width: 1920,
      height: 1080,
      availWidth: 1920,
      availHeight: 1080,
      colorDepth: 24,
      pixelDepth: 24,
    },
  };
  windowObj.top = windowObj;
  windowObj.self = windowObj;
  windowObj.window = windowObj;
  windowObj.parent = windowObj;
  windowObj.Window = nativeFn('Window', function Window() {});

  const sandbox = {
    Element,
    HTMLElement,
    HTMLDivElement,
    HTMLIFrameElement,
    navigator: {
      userAgent: ua,
      webdriver: false,
      language: 'en-US',
      languages: ['en-US', 'en'],
      platform: 'Linux x86_64',
      vendor: 'Google Inc.',
      hardwareConcurrency: 8,
      maxTouchPoints: 0,
      cookieEnabled: true,
    },
    document,
    window: windowObj,
    top: windowObj,
    self: windowObj,
    parent: windowObj,
    getComputedStyle: windowObj.getComputedStyle,
    parseInt,
    String,
    Number,
    Array,
    Object,
    JSON,
    Promise,
    Error,
    Math,
    Symbol,
    isFinite,
    isNaN,
    parseFloat,
    decodeURIComponent,
    encodeURIComponent,
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
    console: { log() {}, warn() {}, error() {}, info() {}, debug() {} },
  };

  const result = await vm.runInContext(raw, vm.createContext(sandbox), { timeout: 8000 });
  if (!result || !Array.isArray(result.client_hashes)) {
    throw new Error('challenge returned invalid payload');
  }
  const hashed = result.client_hashes.map((x) =>
    crypto.createHash('sha256').update(String(x)).digest('base64')
  );
  const payload = {
    server_hashes: result.server_hashes,
    client_hashes: hashed,
    signals: result.signals || {},
    meta: {
      ...(result.meta || {}),
      origin: 'https://duck.ai',
      stack: 'Error\n    at solve (native)',
      duration: String(12 + Math.floor(Math.random() * 20)),
    },
  };
  return {
    client_hashes: result.client_hashes,
    server_hashes: result.server_hashes,
    meta: result.meta,
    hash: Buffer.from(JSON.stringify(payload)).toString('base64'),
  };
}

const chunks = [];
process.stdin.on('data', (c) => chunks.push(c));
process.stdin.on('end', async () => {
  try {
    const msg = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const raw = Buffer.from(msg.challenge, 'base64').toString('utf8');
    const out = await solve(raw, msg.user_agent || '');
    process.stdout.write(JSON.stringify({ ok: true, ...out }));
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: String(e && e.stack ? e.stack : e) }));
    process.exit(1);
  }
});
