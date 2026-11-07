import { test, expect } from "bun:test";
import { bundleHtml, auditHtml } from "../bundle.ts";
import fs from "fs";
import path from "path";
import os from "os";

test("repository html pages have zero external dependencies", () => {
  const htmlFiles = fs.readdirSync(".").filter(f => f.endsWith(".html"));
  expect(htmlFiles.length).toBeGreaterThan(0);
  for (const f of htmlFiles) {
    const content = fs.readFileSync(f, "utf-8");
    const { issues, passed } = auditHtml(content);
    expect(issues).toEqual([]);
    expect(passed).toBe(true);
  }
});

test("bundleHtml inlines external css, imported css, and scripts into a single file", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "bun-test-"));
  const cssFile = path.join(tmpDir, "styles.css");
  const jsFile = path.join(tmpDir, "app.js");
  const htmlFile = path.join(tmpDir, "index.html");

  fs.writeFileSync(cssFile, "body { margin: 0; background: red; }");
  fs.writeFileSync(jsFile, "console.log('inlined script');");
  fs.writeFileSync(
    htmlFile,
    `<!DOCTYPE html><html><head><link rel="stylesheet" href="styles.css"></head><body><script src="app.js"></script></body></html>`
  );

  const bundled = bundleHtml(htmlFile);
  expect(bundled).toContain("<style>");
  expect(bundled).toContain("background: red");
  expect(bundled).toContain("<script>");
  expect(bundled).toContain("inlined script");
  expect(bundled).not.toContain('<link rel="stylesheet"');
  expect(bundled).not.toContain('<script src=');

  const { passed } = auditHtml(bundled);
  expect(passed).toBe(true);

  fs.rmSync(tmpDir, { recursive: true, force: true });
});
