import subprocess
import tempfile
from pathlib import Path

def test_audit_clean_repo():
    """Verify that all repository HTML files pass the audit with zero external dependencies."""
    res_bun = subprocess.run(["bun", "bundle.ts", "--check"], capture_output=True, text=True)
    assert res_bun.returncode == 0, f"Bun audit failed:\n{res_bun.stderr}\n{res_bun.stdout}"
    assert "100% self-contained" in res_bun.stdout

    res_js = subprocess.run(["node", "bundle.js", "--check"], capture_output=True, text=True)
    assert res_js.returncode == 0, f"Node audit failed:\n{res_js.stderr}\n{res_js.stdout}"

    res_py = subprocess.run(["python3", "bundle.py", "--check"], capture_output=True, text=True)
    assert res_py.returncode == 0, f"Python audit failed:\n{res_py.stderr}\n{res_py.stdout}"

def test_bundle_inlining():
    """Verify that external css, js, fonts, and images are properly inlined into a single self-contained file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # 1. External stylesheet with @import and image url
        img_file = tmp_path / "bg.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82")

        imported_css = tmp_path / "imported.css"
        imported_css.write_text(".banner { background-image: url('bg.png'); }", encoding="utf-8")

        main_css = tmp_path / "styles.css"
        main_css.write_text("@import 'imported.css';\nbody { color: #fff; }", encoding="utf-8")

        # 2. External script
        js_file = tmp_path / "app.js"
        js_file.write_text("console.log('App started');", encoding="utf-8")

        # 3. HTML referencing external css and js
        html_file = tmp_path / "index.html"
        html_file.write_text(f"""<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <h1>Test App</h1>
  <img src="bg.png" alt="logo">
  <script src="app.js"></script>
</body>
</html>""", encoding="utf-8")

        # Bundle with bun
        bun_out = tmp_path / "bun_out.html"
        res_bun = subprocess.run(["bun", "bundle.ts", str(html_file), str(bun_out)], capture_output=True, text=True)
        assert res_bun.returncode == 0, f"Bun bundle error:\n{res_bun.stderr}"
        bun_html = bun_out.read_text(encoding="utf-8")
        assert "data:image/png;base64," in bun_html
        assert "App started" in bun_html
        assert "color: #fff" in bun_html
        assert '<link rel="stylesheet"' not in bun_html
        assert '<script src=' not in bun_html

        # Bundle with python
        py_out = tmp_path / "py_out.html"
        res_py = subprocess.run(["python3", "bundle.py", str(html_file), str(py_out)], capture_output=True, text=True)
        assert res_py.returncode == 0, f"Python bundle error:\n{res_py.stderr}"
        py_html = py_out.read_text(encoding="utf-8")
        assert "data:image/png;base64," in py_html
        assert "App started" in py_html
        assert "color: #fff" in py_html
        assert '<link rel="stylesheet"' not in py_html
        assert '<script src=' not in py_html

if __name__ == "__main__":
    test_audit_clean_repo()
    test_bundle_inlining()
    print("All tests passed successfully!")
