#!/usr/bin/env node
/**
 * Standalone single-file HTML bundler and dependency auditor.
 * Can be run with Node.js (`node bundle.js`) or Bun (`bun bundle.js`).
 * Inlines scripts, styles, imported CSS, fonts, and images into a single self-contained bundle.
 * Audits pages to guarantee no external dependencies.
 */

const fs = require('fs');
const path = require('path');

const MIME_TYPES = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.eot': 'application/vnd.ms-fontobject',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.ogg': 'audio/ogg',
  '.json': 'application/json'
};

function getMimeType(filePath) {
  const ext = path.extname(filePath.split('?')[0].split('#')[0]).toLowerCase();
  return MIME_TYPES[ext] || 'application/octet-stream';
}

function resolveAssetPath(baseDir, assetRef) {
  const cleanRef = assetRef.split('?')[0].split('#')[0].trim();
  if (!cleanRef || cleanRef.startsWith('data:') || cleanRef.startsWith('blob:') || cleanRef.startsWith('javascript:')) {
    return null;
  }
  const resolved = path.isAbsolute(cleanRef) ? cleanRef : path.resolve(baseDir, cleanRef);
  if (fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
    return resolved;
  }
  return null;
}

function toDataUri(filePath) {
  const mime = getMimeType(filePath);
  const data = fs.readFileSync(filePath);
  return `data:${mime};base64,${data.toString('base64')}`;
}

function processCssContent(cssText, baseDir, visited = new Set()) {
  // 1. Process @import
  let outCss = cssText.replace(/@import\s+(?:url\(['"]?|['"])([^'"\)\s]+)(?:['"]?\)|['"])\s*;?/gi, (match, importPath) => {
    const resolved = resolveAssetPath(baseDir, importPath);
    if (!resolved || visited.has(resolved)) {
      return `/* @import could not be resolved or already imported: ${importPath} */`;
    }
    visited.add(resolved);
    try {
      const importedCss = fs.readFileSync(resolved, 'utf-8');
      return processCssContent(importedCss, path.dirname(resolved), visited);
    } catch (e) {
      console.warn(`Warning: Failed to inline @import: ${importPath}`);
      return match;
    }
  });

  // 2. Process url(...) references
  outCss = outCss.replace(/(?<![A-Za-z0-9_$.])url\(\s*(['"]?)([^'")]+)\1\s*\)/gi, (match, quote, urlRef) => {
    const trimmed = urlRef.trim();
    if (trimmed.startsWith('data:') || trimmed.startsWith('blob:') || trimmed.startsWith('#')) {
      return match;
    }
    const resolved = resolveAssetPath(baseDir, trimmed);
    if (resolved) {
      const dataUri = toDataUri(resolved);
      return `url("${dataUri}")`;
    }
    return match;
  });

  return outCss;
}

function bundleHtml(inputHtmlPath) {
  const absPath = path.resolve(inputHtmlPath);
  if (!fs.existsSync(absPath)) {
    throw new Error(`File not found: ${inputHtmlPath}`);
  }
  const baseDir = path.dirname(absPath);
  let html = fs.readFileSync(absPath, 'utf-8');

  // Inline linked stylesheets: <link rel="stylesheet" ... href="...">
  html = html.replace(/<link\b([^>]*)\/?>/gi, (match, attrs) => {
    const isStylesheet = /\brel\s*=\s*['"]?stylesheet['"]?/i.test(attrs);
    if (!isStylesheet) return match;
    const hrefMatch = attrs.match(/\bhref\s*=\s*(['"])([^'"]+)\1/i) || attrs.match(/\bhref\s*=\s*([^\s>]+)/i);
    if (!hrefMatch) return match;
    const href = hrefMatch[2] || hrefMatch[1];
    const resolved = resolveAssetPath(baseDir, href);
    if (resolved) {
      try {
        const cssContent = fs.readFileSync(resolved, 'utf-8');
        const inlinedCss = processCssContent(cssContent, path.dirname(resolved));
        return `<style>\n${inlinedCss}\n</style>`;
      } catch (e) {
        console.warn(`Warning: Failed to inline stylesheet: ${href}`);
      }
    }
    return match;
  });

  // Inline external scripts: <script ... src="..."></script>
  html = html.replace(/<script\b([^>]*)>(.*?)<\/script>/gis, (match, attrs, inlineContent) => {
    const srcMatch = attrs.match(/\bsrc\s*=\s*(['"])([^'"]+)\1/i) || attrs.match(/\bsrc\s*=\s*([^\s>]+)/i);
    if (!srcMatch) return match;
    const src = srcMatch[2] || srcMatch[1];
    const resolved = resolveAssetPath(baseDir, src);
    if (resolved) {
      try {
        const scriptCode = fs.readFileSync(resolved, 'utf-8');
        const cleanAttrs = attrs.replace(/\bsrc\s*=\s*(['"][^'"]*['"]|[^\s>]+)/i, '').trim();
        const attrStr = cleanAttrs ? ` ${cleanAttrs}` : '';
        return `<script${attrStr}>\n${scriptCode}\n</script>`;
      } catch (e) {
        console.warn(`Warning: Failed to inline script: ${src}`);
      }
    }
    return match;
  });

  // Process inline <style>...</style> blocks
  html = html.replace(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi, (match, attrs, content) => {
    const processed = processCssContent(content, baseDir);
    return `<style${attrs ? ' ' + attrs.trim() : ''}>${processed}</style>`;
  });

  // Inline img / audio / video / source src
  html = html.replace(/<(img|source|audio|video|input)\b([^>]*)\/?>/gi, (match, tag, attrs) => {
    const srcMatch = attrs.match(/\bsrc\s*=\s*(['"])([^'"]+)\1/i) || attrs.match(/\bsrc\s*=\s*([^\s>]+)/i);
    if (!srcMatch) return match;
    const src = srcMatch[2] || srcMatch[1];
    const resolved = resolveAssetPath(baseDir, src);
    if (resolved) {
      const dataUri = toDataUri(resolved);
      const newAttrs = attrs.replace(srcMatch[0], `src="${dataUri}"`);
      return `<${tag} ${newAttrs.trim()}>`;
    }
    return match;
  });

  return html;
}

function auditHtml(htmlContent) {
  const issues = [];

  // Check external script src
  const scripts = htmlContent.match(/<script[^>]+src=['"]([^'"]+)['"]/gi) || [];
  for (const s of scripts) {
    issues.push(`External script: ${s}`);
  }

  // Check external link tags (stylesheet, preconnect, etc.)
  const links = htmlContent.match(/<link[^>]+href=['"]([^'"]+)['"]/gi) || [];
  for (const l of links) {
    if (!l.toLowerCase().includes('data:')) {
      issues.push(`External link: ${l}`);
    }
  }

  // Check CSS @import
  const imports = htmlContent.match(/@import\s+(?:url\()?['"]?([^'")\s;]+)/gi) || [];
  for (const imp of imports) {
    issues.push(`CSS @import found: ${imp}`);
  }

  // Check CSS url(...)
  const styleBlocks = htmlContent.match(/<style[^>]*>([\s\S]*?)<\/style>/gi) || [];
  for (const sb of styleBlocks) {
    const urls = sb.match(/(?<![A-Za-z0-9_$.])url\(\s*['"]?([^'")]+)['"]?\s*\)/gi) || [];
    for (const u of urls) {
      if (!u.toLowerCase().includes('data:') && !u.toLowerCase().includes('blob:') && !u.includes('#')) {
        issues.push(`CSS external url(): ${u}`);
      }
    }
  }

  // Check tags with remote URLs
  const clean = htmlContent.replace(/<!--[\s\S]*?-->/g, '');
  const tagMatches = clean.match(/<[^>]+>/g) || [];
  for (const tag of tagMatches) {
    const remote = tag.match(/['"](https?:\/\/[^'"]+)['"]/i);
    if (remote) {
      issues.push(`Remote URL inside HTML tag: ${remote[1]}`);
    }
  }

  return { issues, passed: issues.length === 0 };
}

function runAuditAll() {
  const htmlFiles = fs.readdirSync('.').filter(f => f.endsWith('.html'));
  console.log(`Auditing ${htmlFiles.length} HTML files for external dependencies...`);
  let failCount = 0;
  for (const f of htmlFiles) {
    const content = fs.readFileSync(f, 'utf-8');
    const { issues, passed } = auditHtml(content);
    if (!passed) {
      console.error(`❌ [FAIL] ${f} has ${issues.length} external dependency issues:`);
      issues.forEach(iss => console.error(`   - ${iss}`));
      failCount++;
    } else {
      console.log(`✅ [PASS] ${f} is 100% self-contained (zero external dependencies).`);
    }
  }
  return failCount === 0;
}

if (require.main === module) {
  const args = process.argv.slice(2);
  let checkOnly = false;
  let inputPath = '';
  let outputPath = '';

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--check') {
      checkOnly = true;
    } else if (!inputPath) {
      inputPath = args[i];
    } else if (!outputPath) {
      outputPath = args[i];
    }
  }

  if (checkOnly || (!inputPath && !outputPath)) {
    const ok = runAuditAll();
    if (!ok) {
      process.exit(1);
    } else {
      console.log('\nAll pages verified: No external dependencies found!');
    }
  }

  if (inputPath) {
    const bundled = bundleHtml(inputPath);
    const { issues, passed } = auditHtml(bundled);
    if (!passed) {
      console.warn('⚠️ Warning: Bundled output still has unresolved references:');
      issues.forEach(i => console.warn('  - ' + i));
    }
    if (outputPath) {
      fs.writeFileSync(outputPath, bundled, 'utf-8');
      console.log(`Bundled ${inputPath} -> ${outputPath} (${bundled.length} bytes, self-contained: ${passed})`);
    } else {
      console.log(`Successfully bundled ${inputPath} (${bundled.length} bytes, self-contained: ${passed})`);
    }
  }
}

module.exports = { bundleHtml, auditHtml };
