# micro_Accordion

Microtonal bisonoric accordion research sketch and virtual instrument.

## Zero External Dependencies

All application pages (`microtonal_accordion_lab_expanded.html`, `microtonal_accordion_lab_pitchbend.html`, and `microtonal_accordion_lab_final.html`) are 100% self-contained and run completely offline:
- No remote CDNs or external stylesheets.
- No external JavaScript libraries or runtime network calls.
- Pure Web Audio API synthesis without external audio samples.
- Self-contained inline SVGs and canvas rendering.

## Single-File Bundler & Verification

A bundling and verification tool is provided to audit existing files and create single-file bundles after each development iteration. It inlines linked stylesheets, `@import` CSS rules, external JavaScript scripts, images, and fonts into a self-contained HTML file.

The bundler is available across Bun, Node.js, and Python:

### Check / Audit for External Dependencies

Verify that all HTML files have zero external dependencies:

```bash
# Using Bun
bun run check

# Using Node
node bundle.js --check

# Using Python
python3 bundle.py --check
```

### Bundle an HTML File

Bundle an HTML file with its assets into a single standalone file:

```bash
# Using Bun
bun bundle.ts input.html output.html

# Using Node
node bundle.js input.html output.html

# Using Python
python3 bundle.py input.html output.html
```

### Running Tests

Run the bundler test suite:

```bash
python3 tests/test_bundle.py
# or
bun test
```
