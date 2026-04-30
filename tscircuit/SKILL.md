---
name: tscircuit
description: Generate tscircuit schematic TSX code. Use when the user asks to draw, design, or sketch an electronics schematic — resistors, capacitors, LEDs, diodes, transistors, ICs, voltage dividers, RC filters, oscillators, op-amp circuits, microcontroller wiring — for rendering inside Omnicore Markdown Viewer. Triggered by mentions of "tscircuit", "schematic", "circuit diagram", or requests for `.circuit.tsx` files / ` ```tscircuit ` code blocks.
argument-hint: "[description of the circuit to draw]"
---

# tscircuit Schematic Generator

You are an expert at generating **tscircuit** schematic TSX code. tscircuit is a React-based DSL for describing electronics. Inside Omnicore Markdown Viewer, ` ```tscircuit ` code blocks and `.circuit.tsx` files are compiled by `@tscircuit/eval` to Circuit JSON, then rendered to SVG by `circuit-to-svg`.

This skill is **schematic-only** — ignore PCB-specific props (`pcbX`, `pcbY`, `layer`, `routingDisabled`, etc.). Always emit schematic placement (`schX`, `schY`, `schRotation`).

## Output Format

Always wrap output in a fenced ` ```tscircuit ` code block so the viewer renders it:

````
```tscircuit
export default () => (
  <board width="20mm" height="20mm" schAutoLayoutEnabled={false}>
    {/* components */}
  </board>
)
```
````

If the user explicitly asks for a standalone `.circuit.tsx` file, output the raw TSX without the code fence.

### Required structure

1. **`export default`** a React component (arrow function or named function) — the eval worker looks for the default export.
2. The component must return a single root `<board>` (or `<group>` inside a board).
3. Use **JSX**; tscircuit elements are lowercase (`<resistor>`, `<capacitor>`).
4. Comments use `{/* ... */}` JSX style, not `//`.
5. No imports needed for built-in elements — they are globals inside the eval sandbox. Only import `sel` if you're building selector helpers, and only when the user explicitly asks for it.

## Schematic Coordinate System

| Prop | Meaning |
|---|---|
| `schX={n}` | Horizontal position in **schematic millimeters**; positive = right, negative = left, `0` = board center |
| `schY={n}` | Vertical position; positive = up, negative = down |
| `schRotation={deg}` | Rotate the symbol in degrees: `0`, `90`, `180`, `270` |
| `schOrientation` | `"horizontal"` (default) or `"vertical"` for some symbols |

Spacing rule of thumb: **2 mm between adjacent components** keeps wires readable. For a row of 3 parts, try `schX={-3}`, `schX={0}`, `schX={3}`.

Set `schAutoLayoutEnabled={false}` on the `<board>` whenever you provide explicit `schX`/`schY` — otherwise tscircuit may override your placement.

## Component Reference (schematic-relevant props)

### Two-terminal passives — `<resistor>`, `<capacitor>`, `<inductor>`

```tsx
<resistor  name="R1" resistance="10k"   schX={-3} schY={0} />
<capacitor name="C1" capacitance="100nF" schX={0}  schY={0} />
<inductor  name="L1" inductance="10uH"  schX={3}  schY={0} />
```

| Prop | Notes |
|---|---|
| `name` | Reference designator (`R1`, `C1`, `L1`). **Required.** Used by trace selectors. |
| `resistance` / `capacitance` / `inductance` | Value as a string with SI suffix: `"10k"`, `"4.7uF"`, `"100nH"`. Numbers (`1000`) are also accepted but strings are clearer. |
| `footprint` | Optional; only matters for PCB. Skip in schematic-only diagrams. |
| `polarized` | On `<capacitor>`, set `true` for electrolytics. |

**Pin aliases:** `pin1` ≡ `left` ≡ `pos` ; `pin2` ≡ `right` ≡ `neg`.

### Light & semiconductor — `<led>`, `<diode>`

```tsx
<led   name="LED1" color="red"   schX={2} schY={0} />
<diode name="D1"   schX={-2} schY={0} />
```

**Pin aliases:** `anode` ≡ `pin1` ≡ `pos` ; `cathode` ≡ `pin2` ≡ `neg`.

### `<transistor>` (BJT) and `<mosfet>`

```tsx
<transistor name="Q1" type="npn" schX={0} schY={0} />
<mosfet     name="M1" channelType="n" mosfetMode="enhancement" schX={0} schY={0} />
```

| Element | Pins |
|---|---|
| `<transistor>` | `base`, `collector`, `emitter` (also `pin1`/`pin2`/`pin3`) |
| `<mosfet>` | `gate`, `drain`, `source` |

`type` for transistor: `"npn"` or `"pnp"`. `channelType` for mosfet: `"n"` or `"p"`.

### `<chip>` — generic IC

```tsx
<chip
  name="U1"
  pinLabels={{
    pin1: "VCC", pin2: "DISCH", pin3: "THRES", pin4: "CTRL",
    pin5: "GND", pin6: "TRIG",  pin7: "OUT",   pin8: "RESET",
  }}
  schPinArrangement={{
    leftSide:  { direction: "top-to-bottom", pins: ["DISCH", "THRES", "CTRL"] },
    rightSide: { direction: "bottom-to-top", pins: ["TRIG", "OUT", "RESET"] },
    topSide:   { direction: "left-to-right", pins: ["VCC"] },
    bottomSide:{ direction: "left-to-right", pins: ["GND"] },
  }}
  connections={{ VCC: "net.V5", GND: "net.GND" }}
  schX={0}
  schY={0}
/>
```

- `pinLabels` maps physical pin numbers → human names. After this, `.U1 > .VCC` works in selectors.
- `schPinArrangement` controls **where each labeled pin appears on the symbol**. Each side gets a list of pin names in order.
- `connections` is a shorthand that wires labeled pins directly to nets or other pins, **avoiding `<trace>` clutter**.

### `<board>`, `<group>`

```tsx
<board width="30mm" height="20mm" schAutoLayoutEnabled={false}>
  <group name="input_stage">
    {/* sub-circuit */}
  </group>
</board>
```

- `<board>` is the root. `width`/`height` are in PCB millimeters (any sensible value works for schematic-only).
- `<group>` is purely organizational — useful for naming sub-circuits in larger schematics.

### `<net>` and `<netlabel>`

```tsx
<net name="V5"  isForPower={true} />
<net name="GND" isGround={true}   />

<netlabel net="V5"  schX={0} schY={3}  anchorSide="bottom" />
<netlabel net="GND" schX={0} schY={-3} anchorSide="top"    />
```

- `<net>` defines a named electrical connection. `isForPower` and `isGround` are hints for the renderer.
- Nets do **not** need to be declared explicitly — referencing `"net.V5"` in a trace creates one automatically. Declare them when you want power/ground hints or netlabel placement.
- `<netlabel>` draws the visible label on the schematic. `anchorSide` is which side of the label attaches to the wire: `"top"`, `"bottom"`, `"left"`, `"right"`.

### `<trace>` — explicit wire

```tsx
<trace from=".R1 > .pin2" to=".C1 > .pin1" />
<trace from=".R1 > .pin1" to="net.V5" />
<trace from=".LED1 > .cathode" to="net.GND" />
```

Selector grammar: `.<componentName> > .<pinNameOrAlias>`. Use `net.<NetName>` for net endpoints (no leading dot).

## Connection Idioms — Pick the Right One

**Use `<trace>` when:** wiring two specific pins, the connection is short and visually obvious, or you want explicit control over what gets drawn.

**Use `connections={{...}}` when:** wiring an IC with many pins. It produces cleaner schematics than ten `<trace>` lines.

**Use a `<net>` reference (`"net.GND"`) when:** the same signal touches more than two pins (power, ground, common buses). Routing through a named net beats fan-out traces.

```tsx
{/* Cleanest pattern for a chip with mixed connections */}
<chip
  name="U1"
  pinLabels={{ pin1: "IN", pin2: "GND", pin3: "OUT", pin4: "VCC" }}
  connections={{
    VCC: "net.V5",
    GND: "net.GND",
    IN:  ".R1 > .pin2",
    OUT: ".LED1 > .anode",
  }}
/>
```

## Common Circuit Recipes

### Voltage divider (10k / 10k → mid-rail)

```tsx
export default () => (
  <board width="20mm" height="20mm" schAutoLayoutEnabled={false}>
    <net name="VIN" isForPower />
    <net name="GND" isGround />

    <resistor name="R1" resistance="10k" schX={0} schY={2} schRotation={90} />
    <resistor name="R2" resistance="10k" schX={0} schY={-2} schRotation={90} />

    <trace from=".R1 > .pin1" to="net.VIN" />
    <trace from=".R1 > .pin2" to=".R2 > .pin1" />
    <trace from=".R2 > .pin2" to="net.GND" />

    <netlabel net="VIN" schX={0} schY={4} anchorSide="bottom" />
    <netlabel net="GND" schX={0} schY={-4} anchorSide="top" />
    <netlabel net="VOUT" schX={2} schY={0} anchorSide="left" />
    <trace from=".R1 > .pin2" to="net.VOUT" />
  </board>
)
```

### LED with current-limiting resistor

```tsx
export default () => (
  <board width="20mm" height="10mm" schAutoLayoutEnabled={false}>
    <net name="V5" isForPower />
    <net name="GND" isGround />

    <resistor name="R1" resistance="330" schX={-2} schY={0} />
    <led      name="LED1" color="red"    schX={2}  schY={0} />

    <trace from=".R1 > .pin1"     to="net.V5" />
    <trace from=".R1 > .pin2"     to=".LED1 > .anode" />
    <trace from=".LED1 > .cathode" to="net.GND" />
  </board>
)
```

### RC low-pass filter

```tsx
export default () => (
  <board width="25mm" height="15mm" schAutoLayoutEnabled={false}>
    <net name="GND" isGround />

    <resistor  name="R1" resistance="1k"    schX={-3} schY={0} />
    <capacitor name="C1" capacitance="100nF" schX={2}  schY={-2} schRotation={90} />

    <trace from=".R1 > .pin2" to=".C1 > .pin1" />
    <trace from=".C1 > .pin2" to="net.GND" />

    <netlabel net="VIN"  schX={-5} schY={0} anchorSide="right" />
    <netlabel net="VOUT" schX={4}  schY={0} anchorSide="left"  />
    <trace from=".R1 > .pin1" to="net.VIN" />
    <trace from=".R1 > .pin2" to="net.VOUT" />
  </board>
)
```

### 555 astable oscillator (chip with `pinLabels` + `connections`)

```tsx
export default () => (
  <board width="40mm" height="30mm" schAutoLayoutEnabled={false}>
    <net name="V5"  isForPower />
    <net name="GND" isGround />

    <chip
      name="U1"
      pinLabels={{
        pin1: "GND",  pin2: "TRIG", pin3: "OUT",   pin4: "RESET",
        pin5: "CTRL", pin6: "THRES",pin7: "DISCH", pin8: "VCC",
      }}
      schPinArrangement={{
        leftSide:  { direction: "top-to-bottom", pins: ["TRIG", "THRES", "DISCH"] },
        rightSide: { direction: "top-to-bottom", pins: ["RESET", "CTRL", "OUT"] },
        topSide:   { direction: "left-to-right", pins: ["VCC"] },
        bottomSide:{ direction: "left-to-right", pins: ["GND"] },
      }}
      connections={{
        VCC:   "net.V5",
        GND:   "net.GND",
        RESET: "net.V5",
        TRIG:  ".C1 > .pos",
        THRES: ".C1 > .pos",
        DISCH: ".R2 > .pin1",
      }}
      schX={0}
      schY={0}
    />

    <resistor  name="R1" resistance="10k"   schX={-6} schY={4} />
    <resistor  name="R2" resistance="100k"  schX={-6} schY={0} />
    <capacitor name="C1" capacitance="10uF" polarized schX={-6} schY={-4} schRotation={90} />

    <trace from=".R1 > .pin1" to="net.V5" />
    <trace from=".R1 > .pin2" to=".R2 > .pin1" />
    <trace from=".C1 > .neg"  to="net.GND" />

    <netlabel net="V5"  schX={0} schY={5}  anchorSide="bottom" />
    <netlabel net="GND" schX={0} schY={-5} anchorSide="top"    />
  </board>
)
```

## Best Practices

1. **Always set `schAutoLayoutEnabled={false}` on the board** when you supply explicit `schX`/`schY`, or your placement will be rearranged.
2. **Give every component a `name`.** Trace selectors and `connections` rely on it.
3. **Prefer named nets over long traces** for power, ground, and any signal touching ≥3 pins.
4. **Use `connections={{...}}` for chips** — much more readable than a wall of `<trace>` lines.
5. **Group power up, ground down** — power netlabels at top of board, ground at bottom. Matches schematic-reading conventions.
6. **Keep `schX`/`schY` on a 1–2 mm grid** for visual alignment; avoid arbitrary fractions.
7. **Rotate two-terminal parts with `schRotation={90}`** when wiring vertically (e.g. resistor between rail and a horizontal signal line).
8. **Don't include `footprint`, `pcbX`, `pcbY`, layer info, or `<pcbtrace>`** unless the user explicitly asked for PCB output — it's noise in a schematic-only diagram.
9. **Pin aliases matter:** use `.LED1 > .anode` not `.LED1 > .pin1` — the alias makes the wire's intent obvious to a human reader.
10. **One `<board>` per code block.** If the user wants multiple unrelated schematics, emit multiple ` ```tscircuit ` blocks.

## Failure Modes to Avoid

- ❌ Forgetting `export default` — the eval worker will return an empty Circuit JSON and the diagram will be blank.
- ❌ Using `//` comments outside JSX braces — TSX will parse them, but anything resembling JSX after a stray `//` breaks. Prefer `{/* ... */}`.
- ❌ Selectors with spaces (`. R1 > .pin1`) — selectors are whitespace-tolerant *between* `>` but the leading dot must hug the name.
- ❌ Mixing schematic placement with no `schAutoLayoutEnabled={false}` — auto-layout silently overrides your coordinates.
- ❌ Referencing a pin alias that doesn't exist on that component (e.g. `.R1 > .anode`) — produces a confusing "pin not found" error.

## When the User Asks Vague Things

- "Draw an LED circuit" → assume 5 V supply, current-limit resistor, LED to ground. Show the recipe above.
- "Show me a low-pass filter" → RC with 1 kΩ / 100 nF unless they specify a corner frequency. If they specify f, compute R or C.
- "Op-amp follower" → use `<chip>` with two pins labeled `IN+`, `IN-`, `OUT`, plus `VCC`/`GND`, wired as a unity-gain buffer.
- "Microcontroller" → use a `<chip>` with the relevant pinout. Don't invent footprint codes; the schematic doesn't need them.

## Self-Verification (REQUIRED before presenting non-trivial schematics)

After generating any schematic with **more than three components, any chip, or any new circuit topology you have not produced before in this conversation**, verify it actually compiles and renders. Skip verification only for single-component or very small (≤3 part) sketches.

The skill ships with a verification harness at `~/.claude/skills/tscircuit/verify.html`. The bundle is **symlinked into the same directory** (`tscircuit-bundle.js`) so the harness loads with a relative `<script>` path — works equally over `file://` or `http://`.

> **Why HTTP, not file://?** Playwright Chromium blocks `file://` navigation in this harness (security policy). The bundle and harness must be served. The skill provides a one-shot HTTP server to bypass this.

### Verification procedure

1. **Save the generated TSX** as `tsx-source.txt` inside the skill directory so it sits next to the harness and can be fetched relatively. Save **only** the TSX (no fences, no markdown):

   ```
   Write file_path=/home/omni/.claude/skills/tscircuit/tsx-source.txt
   ```

2. **Start a local HTTP server** in the skill directory (one time per session — `lsof -i:8765` to check if already running):

   ```bash
   cd /home/omni/.claude/skills/tscircuit && python3 -m http.server 8765 >/tmp/tscircuit-srv.log 2>&1 &
   ```

3. **Open the harness in Playwright** via HTTP:

   ```
   mcp__plugin_playwright_playwright__browser_navigate
     url: http://localhost:8765/verify.html
   ```

4. **Render the TSX** via `browser_evaluate`. Use a cache-busting query so re-runs always pick up the latest TSX:

   ```js
   async () => {
     const resp = await fetch("/tsx-source.txt?v=" + Date.now());
     const code = await resp.text();
     return await window.__renderTscircuit(code);
   }
   ```

5. **Inspect the result**. The evaluate call returns `{ ok: true, width, height, svgInnerLength }` on success or `{ ok: false, error }` on failure.

   - `ok: false` → fix the TSX (read the error, re-emit, repeat from step 1). Common causes: missing `export default`, bad pin alias, malformed selector, undefined component.
   - `svgInnerLength` < ~500 → the schematic likely rendered empty; check `<board>` exists and components have valid props.

6. **Take a screenshot** for visual confirmation:

   ```
   mcp__plugin_playwright_playwright__browser_take_screenshot
     filename: tscircuit-verify.png
     fullPage: true
   ```

7. **Look at the screenshot** by reading the saved PNG file with the `Read` tool. Confirm:
   - All component reference designators (R1, C1, U1, …) are visible.
   - Wires actually connect — no floating pins.
   - Power/ground netlabels are positioned where you intended.

8. **If you can't tell from the screenshot** whether labels are correct, fall back to OCR via `mcp__imagesorcery__ocr` on the screenshot path — it will extract every text label so you can confirm component names appear.

9. **Console errors** — call `mcp__plugin_playwright_playwright__browser_console_messages` after rendering. Anything with `level: "error"` from `@tscircuit/eval` indicates a compile problem.

   > **IMPORTANT: console errors persist across renders within the same page load.** When iterating, do a fresh `browser_navigate` (e.g., bump a `?reload=N` query) before checking errors — otherwise stale errors from earlier failed renders will be reported and you'll think your fix didn't work.

   The most common runtime error is:

   > `(source_port_id: source_port_X) for trace source_trace_Y does not have x/y coordinates. Skipping this trace.`

   This means the trace endpoint port has no schematic position assigned — the trace will not be drawn. Triggers and workarounds:

   - **Single-side `<chip>` `schPinArrangement`** (e.g., a 2-pin terminal block with only `leftSide` populated) — split pins across `leftSide` + `rightSide`, or use netlabels instead of a chip for external terminals.
   - **Mixing `connections={{}}` with `<trace>` for the same chip pin** — pick one. `connections` is cleaner for fully-wired chips; `<trace>` is cleaner when you need explicit visual layout.
   - **Direct chip-pin → component-pin trace** sometimes fails to assign coords. **Workaround:** route via an intermediate `net.NAME`:
     ```jsx
     {/* fails: */}
     <trace from=".U1 > .OUT" to=".R1 > .pin1" />
     {/* works: */}
     <trace from=".U1 > .OUT" to="net.U1_OUT" />
     <trace from=".R1 > .pin1" to="net.U1_OUT" />
     ```
   - **Pin labels that collide with built-in aliases** — avoid `ANODE`, `CATHODE`, `POS`, `NEG`, `LEFT`, `RIGHT`, `GATE`, `DRAIN`, `SOURCE`, `BASE`, `COLLECTOR`, `EMITTER` as chip pin labels. Use unambiguous names (`LEDA`, `LEDK`, `COLL`, `EMIT`, etc.).
   - **`<mosfet>` extra props** — `mosfetMode="enhancement"` is sometimes silently ignored and breaks port placement. Stick to just `channelType="n"` / `"p"`.

### When verification fails

Tell the user **before** they read your code that you tried to verify and what you saw. Then either:
- Show the corrected version (after a successful re-verify), or
- Show the original code with a clear caveat about what didn't work and why.

Never present unverified non-trivial output as if it were known-good.

### Light-touch alternative for tiny snippets

For 1–3 component sketches where verification overhead exceeds the value, you may skip the harness. But still:
- Re-read your own code mentally for the **failure modes** listed above (missing `export default`, wrong pin aliases, etc.).
- Mention "not verified — small snippet" in a single line at the end so the user knows.

---

Always finish by reminding the user, in one short line, that they can drop the block into any `.md` file (or save it as `.circuit.tsx`) and Omnicore Markdown Viewer will render it.
