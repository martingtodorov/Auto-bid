// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build
const isDevServer = process.env.NODE_ENV !== "production";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

// Define the bot-share dev middleware separately so we can re-apply it
// AFTER withVisualEdits wraps the config — otherwise visual-edits'
// `setupDevServer` clobbers the `setupMiddlewares` hook we set here.
const applySocialBotMiddleware = (devServerConfig) => {
  // Social-bot share middleware — mirrors the production nginx rule so the
  // preview environment (which has no nginx in front of the dev server)
  // also serves our Open Graph template to Facebook/WhatsApp/Telegram.
  // Matches `/auctions/<slug-or-id>` GET requests with a known bot UA and
  // proxies them to the backend's `/api/share/auction/<id>` renderer.
  const SOCIAL_BOTS_RE = /(facebookexternalhit|facebot|twitterbot|slackbot|whatsapp|telegrambot|linkedinbot|discordbot|pinterestbot|skypeuripreview|redditbot|vkshare|applebot|googlebot-image)/i;
  const AUCTION_PATH_RE = /^\/auctions\/([^/?#]+)\/?$/;

  // Also proxy SEO root endpoints to the backend — otherwise the React
  // dev server falls through to index.html, returns HTML, and Cloudflare's
  // AI Shield layer wraps the HTML body with "Content-Signal" directives
  // that PageSpeed flags as robots.txt syntax errors.
  const SEO_PATHS = new Set([
    "/robots.txt",
    "/sitemap.xml",
    "/sitemap-images.xml",
  ]);

  const proxyToBackend = (req, res, backendPath, next) => {
    const http = require("http");
    const proxyReq = http.request(
      {
        host: "127.0.0.1",
        port: 8001,
        path: backendPath,
        method: "GET",
        headers: {
          Host: req.headers.host || "localhost",
          "User-Agent": req.headers["user-agent"] || "",
          "X-Forwarded-Proto": req.headers["x-forwarded-proto"] || "https",
          "X-Forwarded-For": req.headers["x-forwarded-for"] || req.socket?.remoteAddress || "",
        },
      },
      (upstream) => {
        res.statusCode = upstream.statusCode || 502;
        Object.entries(upstream.headers).forEach(([k, v]) => {
          if (k.toLowerCase() === "transfer-encoding") return;
          res.setHeader(k, v);
        });
        upstream.pipe(res);
      },
    );
    proxyReq.on("error", () => next());
    proxyReq.end();
  };

  const botShareMiddleware = (req, res, next) => {
    if (req.method !== "GET") return next();
    const url = (req.url || "").split("?")[0] || "";
    // SEO root passthroughs (always hit backend regardless of UA)
    if (SEO_PATHS.has(url)) {
      return proxyToBackend(req, res, `/api${url}`, next);
    }
    const m = AUCTION_PATH_RE.exec(url);
    if (!m) return next();
    const ua = req.headers["user-agent"] || "";
    if (!SOCIAL_BOTS_RE.test(ua)) return next();
    return proxyToBackend(
      req, res,
      `/api/share/auction/${encodeURIComponent(m[1])}`,
      next,
    );
  };

  const originalSetupMiddlewares = devServerConfig.setupMiddlewares;
  devServerConfig.setupMiddlewares = (middlewares, devServer) => {
    if (originalSetupMiddlewares) {
      middlewares = originalSetupMiddlewares(middlewares, devServer);
    }
    // `unshift` so the bot proxy runs BEFORE the SPA fallback / history-
    // api-fallback middleware (which would otherwise serve index.html).
    middlewares.unshift({
      name: "social-bot-share-proxy",
      middleware: botShareMiddleware,
    });
    if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
      setupHealthEndpoints(devServer, healthPluginInstance);
    }
    return middlewares;
  };

  return devServerConfig;
};

webpackConfig.devServer = applySocialBotMiddleware;

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
    // withVisualEdits injects its own `setupDevServer` that OVERWRITES
    // our `setupMiddlewares`. Re-wrap the final devServer function so
    // our bot middleware is registered *after* their setup runs.
    const wrappedDevServer = webpackConfig.devServer;
    webpackConfig.devServer = (config) => {
      if (typeof wrappedDevServer === "function") {
        config = wrappedDevServer(config);
      }
      return applySocialBotMiddleware(config);
    };
  } catch (err) {
    if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

module.exports = webpackConfig;
