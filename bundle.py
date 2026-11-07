#!/usr/bin/env python3
"""
Standalone single-file HTML bundler and dependency auditor.
Can be executed with Python (`python3 bundle.py`), Bun (`bun run bundle`), or npm (`npm run bundle`).
Resolves and inlines external scripts, stylesheets, @import rules, images, and fonts
into a completely self-contained single-file HTML document with zero external dependencies.
"""

import sys
import os
import re
import mimetypes
import base64
from pathlib import Path

MIME_OVERRIDES = {
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.otf': 'font/otf',
    '.eot': 'application/vnd.ms-fontobject',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.json': 'application/json',
}

def get_mime_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in MIME_OVERRIDES:
        return MIME_OVERRIDES[ext]
    mime, _ = mimetypes.guess_type(str(file_path))
    return mime or 'application/octet-stream'

def to_data_uri(file_path: Path) -> str:
    mime = get_mime_type(file_path)
    data = file_path.read_bytes()
    encoded = base64.b64encode(data).decode('ascii')
    return f"data:{mime};base64,{encoded}"

def resolve_path(base_dir: Path, ref: str) -> Path | None:
    clean_ref = ref.split('?')[0].split('#')[0].strip()
    if not clean_ref or clean_ref.startswith(('data:', 'blob:', 'javascript:')):
        return None
    target = Path(clean_ref) if os.path.isabs(clean_ref) else (base_dir / clean_ref).resolve()
    if target.is_file():
        return target
    return None

def process_css(css_text: str, base_dir: Path, visited: set | None = None) -> str:
    if visited is None:
        visited = set()

    # 1. Handle @import
    def replace_import(match):
        import_path = match.group(1).strip()
        target = resolve_path(base_dir, import_path)
        if not target or str(target) in visited:
            return f"/* @import unresolved or circular: {import_path} */"
        visited.add(str(target))
        try:
            content = target.read_text(encoding='utf-8')
            return process_css(content, target.parent, visited)
        except Exception:
            return match.group(0)

    css_text = re.sub(
        r'@import\s+(?:url\([\'"]?|[\'"])([^\'"\)\s]+)(?:[\'"]?\)|[\'"])\s*;?',
        replace_import,
        css_text,
        flags=re.IGNORECASE
    )

    # 2. Handle url(...)
    def replace_url(match):
        url_ref = match.group(1).strip()
        if url_ref.startswith(('data:', 'blob:', '#')):
            return match.group(0)
        target = resolve_path(base_dir, url_ref)
        if target:
            data_uri = to_data_uri(target)
            return f'url("{data_uri}")'
        return match.group(0)

    css_text = re.sub(
        r'(?<![A-Za-z0-9_$.])url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)',
        replace_url,
        css_text,
        flags=re.IGNORECASE
    )

    return css_text

def bundle_html(input_path: Path) -> str:
    input_path = input_path.resolve()
    base_dir = input_path.parent
    html = input_path.read_text(encoding='utf-8')

    # Inline <link rel="stylesheet" href="...">
    def replace_link(match):
        attrs = match.group(1)
        if not re.search(r'\brel\s*=\s*[\'"]?stylesheet[\'"]?', attrs, re.IGNORECASE):
            return match.group(0)
        href_match = re.search(r'\bhref\s*=\s*([\'"])(.*?)\1', attrs, re.IGNORECASE) or re.search(r'\bhref\s*=\s*([^\s>]+)', attrs, re.IGNORECASE)
        if not href_match:
            return match.group(0)
        href = href_match.group(2) if href_match.lastindex >= 2 else href_match.group(1)
        target = resolve_path(base_dir, href)
        if target:
            try:
                css_content = target.read_text(encoding='utf-8')
                inlined = process_css(css_content, target.parent)
                return f"<style>\n{inlined}\n</style>"
            except Exception:
                pass
        return match.group(0)

    html = re.sub(r'<link\b([^>]*)\/?>', replace_link, html, flags=re.IGNORECASE)

    # Inline <script src="..."></script>
    def replace_script(match):
        attrs = match.group(1)
        src_match = re.search(r'\bsrc\s*=\s*([\'"])(.*?)\1', attrs, re.IGNORECASE) or re.search(r'\bsrc\s*=\s*([^\s>]+)', attrs, re.IGNORECASE)
        if not src_match:
            return match.group(0)
        src = src_match.group(2) if src_match.lastindex >= 2 else src_match.group(1)
        target = resolve_path(base_dir, src)
        if target:
            try:
                js_content = target.read_text(encoding='utf-8')
                clean_attrs = re.sub(r'\bsrc\s*=\s*([\'"][^\'"]*[\'"]|[^\s>]+)', '', attrs, flags=re.IGNORECASE).strip()
                attr_str = f" {clean_attrs}" if clean_attrs else ""
                return f"<script{attr_str}>\n{js_content}\n</script>"
            except Exception:
                pass
        return match.group(0)

    html = re.sub(r'<script\b([^>]*)>(.*?)</script>', replace_script, html, flags=re.IGNORECASE | re.DOTALL)

    # Process inline <style> tags
    def replace_style(match):
        attrs = match.group(1)
        content = match.group(2)
        processed = process_css(content, base_dir)
        attr_str = f" {attrs.strip()}" if attrs.strip() else ""
        return f"<style{attr_str}>{processed}</style>"

    html = re.sub(r'<style\b([^>]*)>(.*?)</style>', replace_style, html, flags=re.IGNORECASE | re.DOTALL)

    # Inline media src: <img src="...">, <audio src="...">, <video src="...">, <source src="...">
    def replace_media(match):
        tag = match.group(1)
        attrs = match.group(2)
        src_match = re.search(r'\bsrc\s*=\s*([\'"])(.*?)\1', attrs, re.IGNORECASE) or re.search(r'\bsrc\s*=\s*([^\s>]+)', attrs, re.IGNORECASE)
        if not src_match:
            return match.group(0)
        src = src_match.group(2) if src_match.lastindex >= 2 else src_match.group(1)
        target = resolve_path(base_dir, src)
        if target:
            data_uri = to_data_uri(target)
            new_attrs = attrs[:src_match.start()] + f'src="{data_uri}"' + attrs[src_match.end():]
            return f"<{tag} {new_attrs.strip()}>"
        return match.group(0)

    html = re.sub(r'<(img|source|audio|video|input)\b([^>]*)\/?>', replace_media, html, flags=re.IGNORECASE)

    return html

def audit_html(html: str) -> tuple[list[str], bool]:
    issues = []

    # Check external scripts
    for s in re.findall(r'<script[^>]+src=[\'"]([^\'"]+)[\'"]', html, re.IGNORECASE):
        issues.append(f"External script: {s}")

    # Check external links
    for l in re.findall(r'<link[^>]+href=[\'"]([^\'"]+)[\'"]', html, re.IGNORECASE):
        if not l.lower().startswith('data:'):
            issues.append(f"External link: {l}")

    # Check CSS @import
    for imp in re.findall(r'@import\s+(?:url\()?[\'"]?([^[\'")\s;]+)', html, re.IGNORECASE):
        issues.append(f"CSS @import found: {imp}")

    # Check CSS url() in style blocks
    for sb in re.findall(r'<style[^>]*>(.*?)</style>', html, re.IGNORECASE | re.DOTALL):
        for u in re.findall(r'(?<![A-Za-z0-9_$.])url\(\s*[\'"]?([^[\'")]+)[\'"]?\s*\)', sb, re.IGNORECASE):
            u_clean = u.strip()
            if not u_clean.startswith(('data:', 'blob:', '#')):
                issues.append(f"CSS external url(): {u_clean}")

    # Check remote URLs in tags
    clean = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    for tag in re.findall(r'<[^>]+>', clean):
        for remote in re.findall(r'[\'"](https?://[^\'"]+)[\'"]', tag, re.IGNORECASE):
            issues.append(f"Remote URL in tag: {remote}")

    return issues, len(issues) == 0

def audit_all():
    html_files = sorted(Path('.').glob('*.html'))
    print(f"Auditing {len(html_files)} HTML files for external dependencies...")
    fail_count = 0
    for f in html_files:
        content = f.read_text(encoding='utf-8')
        issues, passed = audit_html(content)
        if not passed:
            print(f"❌ [FAIL] {f.name} has {len(issues)} external dependency issues:")
            for iss in issues:
                print(f"   - {iss}")
            fail_count += 1
        else:
            print(f"✅ [PASS] {f.name} is 100% self-contained (zero external dependencies).")
    return fail_count == 0

def main():
    args = sys.argv[1:]
    check_only = '--check' in args
    filtered_args = [a for a in args if a != '--check']

    if check_only or len(filtered_args) == 0:
        ok = audit_all()
        if not ok:
            sys.exit(1)
        else:
            print("\nAll pages verified: No external dependencies found!")
            sys.exit(0)

    input_file = Path(filtered_args[0])
    output_file = Path(filtered_args[1]) if len(filtered_args) > 1 else None

    bundled = bundle_html(input_file)
    issues, passed = audit_html(bundled)
    if not passed:
        print("⚠️ Warning: Bundled output has unresolved external dependencies:")
        for iss in issues:
            print(f"  - {iss}")

    if output_file:
        output_file.write_text(bundled, encoding='utf-8')
        print(f"Bundled {input_file} -> {output_file} ({len(bundled)} bytes, self-contained: {passed})")
    else:
        print(f"Successfully bundled {input_file} ({len(bundled)} bytes, self-contained: {passed})")

if __name__ == '__main__':
    main()
