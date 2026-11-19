'use strict';

const vm = require('node:vm');
const crypto = require('node:crypto');

function createSandbox(userAgent) {
  class Element {}
  class HTMLElement extends Element {}
  class HTMLDivElement extends HTMLElement {}
  class HTMLIFrameElement extends HTMLElement {}

  function NodeList() {}
  NodeList.prototype = Object.create(Array.prototype);
  Object.defineProperty(NodeList.prototype, 'constructor', { value: NodeList });

  const mockWindow = {
    get [Symbol.toStringTag]() {
      return 'Window';
    },
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
  };

  mockWindow.Window = function Window() {};
  mockWindow.Window.toString = () => 'function Window() { [native code] }';

  const childrenList = [];

  const mockDocument = {
    body: {
      children: childrenList,
      appendChild: (el) => {
        childrenList.push(el);
      },
      removeChild: (el) => {
        const idx = childrenList.indexOf(el);
        if (idx !== -1) childrenList.splice(idx, 1);
      },
    },
    createElement: (tag) => {
      const lower = String(tag).toLowerCase();
      if (lower === 'div') {
        return Object.assign(new HTMLDivElement(), {
          style: { cssText: '' },
          offsetHeight: 24,
          offsetWidth: 24,
          scrollHeight: 24,
          getBoundingClientRect: () => ({ width: 24, height: 24, top: 0, left: 0 }),
          querySelector: () => null,
          querySelectorAll: () => new NodeList(),
          getAttribute: () => null,
        });
      }
      const dummyFn = function () {};
      dummyFn.toString = () => 'function get() { [native code] }';
      const selfObj = {
        Window: mockWindow.Window,
        get: dummyFn,
        Proxy: { get: dummyFn },
      };
      return Object.assign(new HTMLElement(), {
        srcdoc: '',
        contentWindow: { self: selfObj },
        querySelector: () => null,
        querySelectorAll: () => new NodeList(),
        getAttribute: () => null,
      });
    },
    querySelector: () => null,
    querySelectorAll: () => {
      const nl = new NodeList();
      nl.push({});
      return nl;
    },
  };

  mockWindow.document = mockDocument;
  mockWindow.top = mockWindow;
  mockWindow.self = mockWindow;
  mockWindow.window = mockWindow;

  return {
    Element,
    HTMLElement,
    HTMLDivElement,
    HTMLIFrameElement,
    NodeList,
    navigator: {
      userAgent,
      webdriver: false,
      language: 'en-US',
      languages: ['en-US', 'en'],
      platform: 'Win32',
    },
    document: mockDocument,
    window: mockWindow,
    getComputedStyle: () => ({
      getPropertyValue: (prop) => (prop === 'display' ? 'inline-block' : ''),
    }),
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
    console: { log() {}, warn() {}, error() {} },
  };
}

async function solve(rawScript, userAgent) {
  const sandbox = createSandbox(userAgent);
  const context = vm.createContext(sandbox);
  const challengeResult = await vm.runInContext(rawScript, context, {
    timeout: 8000,
  });

  if (!challengeResult || !Array.isArray(challengeResult.client_hashes)) {
    throw new Error('invalid challenge result');
  }

  const signals = challengeResult.client_hashes.slice();
  if (signals.length > 0) {
    signals[0] = userAgent;
  } else {
    signals.push(userAgent);
  }

  const hashedClients = signals.map((item) =>
    crypto.createHash('sha256').update(String(item)).digest('base64')
  );

  const payload = {
    server_hashes: challengeResult.server_hashes || [],
    client_hashes: hashedClients,
    signals: challengeResult.signals || {},
    meta: {
      ...(challengeResult.meta || {}),
      origin: 'https://duck.ai',
      stack: 'Error\n    at solve (native)',
      duration: String(12 + Math.floor(Math.random() * 25)),
    },
  };

  return Buffer.from(JSON.stringify(payload)).toString('base64');
}

async function main() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  const input = Buffer.concat(chunks).toString('utf8');
  let parsed;
  try {
    parsed = JSON.parse(input);
  } catch {
    process.stderr.write('bad input json\n');
    process.exit(2);
  }

  const scriptB64 = parsed.challenge || '';
  const ua = parsed.user_agent || 'Mozilla/5.0';
  const raw = Buffer.from(scriptB64, 'base64').toString('utf8');

  try {
    const solved = await solve(raw, ua);
    process.stdout.write(JSON.stringify({ ok: true, hash: solved }));
  } catch (err) {
    process.stdout.write(
      JSON.stringify({ ok: false, error: String(err && err.message ? err.message : err) })
    );
    process.exit(1);
  }
}

main();
