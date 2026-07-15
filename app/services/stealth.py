"""Playwright init script that patches the most common bot-detection signals."""
STEALTH_INIT_SCRIPT = """
// 1) Hide webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2) Patch permissions API quirk Chromium leaves behind
const _query = window.navigator.permissions && window.navigator.permissions.query;
if (_query) {
  window.navigator.permissions.query = (params) =>
    _query(params).then((res) => {
      if (params && params.name === 'notifications') {
        return Object.assign(res, { state: Notification.permission });
      }
      return res;
    });
}

// 3) Plugins / languages (Instagram fingerprints these)
Object.defineProperty(navigator, 'plugins', {
  get: () => [1, 2, 3, 4, 5].map((i) => ({ name: 'Plugin ' + i })),
});
Object.defineProperty(navigator, 'languages', {
  get: () => ['en-US', 'en'],
});

// 4) WebGL vendor/renderer leaks are a big tell, mask to a generic GPU
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (p) {
  if (p === 37445) return 'Intel Inc.';
  if (p === 37446) return 'Intel Iris OpenGL Engine';
  return getParameter.call(this, p);
};
const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
WebGL2RenderingContext.prototype.getParameter = function (p) {
  if (p === 37445) return 'Intel Inc.';
  if (p === 37446) return 'Intel Iris OpenGL Engine';
  return getParameter2.call(this, p);
};

// 5) Chrome runtime stub
window.chrome = window.chrome || { runtime: {}, csi: () => ({}), loadTimes: () => ({}) };

// 6) Connection type (Instagram checks for 'cellular' oddities)
Object.defineProperty(navigator, 'connection', {
  get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10, saveData: false }),
});
"""


async def apply_stealth(context):
    await context.add_init_script(STEALTH_INIT_SCRIPT)
