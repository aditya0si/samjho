import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  /**
   * Pin the tracing root to this directory. Without it Next walks up looking for a lockfile, finds
   * an unrelated `package-lock.json` in the user's home directory, and treats that as the workspace
   * root — which changes what gets traced into the standalone output.
   */
  outputFileTracingRoot: here,

  /**
   * A build and a `next dev` running in the same directory share `.next` and corrupt each other
   * ("__webpack_modules__[moduleId] is not a function", PageNotFoundError on /_document). Seven
   * builders work in this repo at once, so the output directory is overridable:
   *
   *   SAMJHO_NEXT_DIST_DIR=.next-web npm run build && SAMJHO_NEXT_DIST_DIR=.next-web npm start
   *
   * Default stays `.next`, so the plain `npm run build` everyone expects is unchanged.
   */
  distDir: process.env.SAMJHO_NEXT_DIST_DIR || ".next",

  /**
   * Standalone output for the container image: `.next/standalone` carries only the traced
   * dependencies plus `server.js`, so `web/Dockerfile` does not need node_modules or the Next CLI at
   * runtime. Additive — `next start` and `npm run dev` behave exactly as before.
   */
  output: "standalone",

  /**
   * `scripts/sync-syllabus.mjs` copies the shipped syllabus to `web/data/syllabus/` at build time, and
   * server components read it from disk at request time. A file read through a computed path is not
   * traced automatically, so the directory is named explicitly — without this, a deployment would
   * upload the copy and still find no syllabus.
   */
  outputFileTracingIncludes: {
    "/**": ["./data/syllabus/**"],
  },

  /**
   * The syllabus lives outside web/ (data/syllabus/, owned by the ingest builder) and is read at
   * runtime with fs, never bundled. Nothing textbook-derived is part of the web build.
   *
   * NOTE for deployment: `NEXT_PUBLIC_API_URL` is inlined at build time (that is how Next treats
   * NEXT_PUBLIC_* — for server code as well as client code), so the web image has to be built with
   * the API URL it will actually talk to.
   */
};

export default nextConfig;
