"""backend/api/scraping/stealth/fingerprint.py — Playwright stealth patches.

Patches are idempotent — safe to call multiple times on the same page.
"""
from __future__ import annotations

_STEALTH_SCRIPT = """
(function() {
    // Prevent multiple applications
    if (window.__nanovia_stealth_applied) return;
    window.__nanovia_stealth_applied = true;

    // 1. navigator.webdriver → undefined
    try {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true,
        });
    } catch(e) {}

    // 2. navigator.plugins — simulate 3 real-looking plugins
    try {
        const fakePlugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
        ];
        Object.defineProperty(navigator, 'plugins', {
            get: () => {
                const arr = fakePlugins.map(p => Object.assign(Object.create(Plugin.prototype || {}), p));
                Object.defineProperty(arr, 'length', { value: fakePlugins.length });
                return arr;
            },
            configurable: true,
        });
    } catch(e) {}

    // 3. navigator.languages
    try {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true,
        });
    } catch(e) {}

    // 4. window.chrome — Chrome runtime object present
    try {
        if (!window.chrome) {
            Object.defineProperty(window, 'chrome', {
                value: { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} },
                writable: false,
                configurable: true,
            });
        }
    } catch(e) {}

    // 5. Permissions API — avoid automation fingerprint
    try {
        const origQuery = window.navigator.permissions && window.navigator.permissions.query.bind(window.navigator.permissions);
        if (origQuery) {
            window.navigator.permissions.query = (params) => {
                if (params.name === 'notifications') {
                    return Promise.resolve({ state: Notification.permission });
                }
                return origQuery(params);
            };
        }
    } catch(e) {}

    // 6. WebGL vendor/renderer — coherent with platform
    try {
        const getParam = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParam.apply(this, arguments);
        };
    } catch(e) {}

    // 7. Canvas fingerprint — deterministic mild noise per session
    try {
        const _noise = (Math.random() * 0.01) - 0.005;
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {
            if (type === 'image/png') {
                const ctx = this.getContext('2d');
                if (ctx && this.width > 0 && this.height > 0) {
                    try {
                        const img = ctx.getImageData(0, 0, 1, 1);
                        img.data[0] = Math.max(0, Math.min(255, img.data[0] + Math.round(_noise * 100)));
                        ctx.putImageData(img, 0, 0);
                    } catch(e) {}
                }
            }
            return origToDataURL.apply(this, arguments);
        };
    } catch(e) {}
})();
"""


async def apply_stealth_patches(page) -> None:
    """Inject stealth JavaScript patches into a Playwright page.

    Idempotent — uses a guard flag so multiple calls are safe.

    Args:
        page: Playwright Page object.
    """
    await page.add_init_script(_STEALTH_SCRIPT)
