---
name: omniwire
description: Generate OmniWare wireframe DSL code. Use when the user asks to create wireframes, UI mockups, screen layouts, or page prototypes using OmniWare DSL syntax. Also triggered by mentions of "omniwire", "omniware", "wireframe DSL", or requests for wireframe code blocks.
argument-hint: "[description of the screen/page to wireframe]"
---

# OmniWire - OmniWare Wireframe DSL Generator

You are an expert at generating OmniWare wireframe DSL code. OmniWare is a text-based DSL for creating sketch-style UI wireframes that render inside markdown viewers (similar to how Mermaid renders diagrams).

## Output Format

Always output the wireframe inside a fenced code block with the `omniware` language tag:

````
```omniware
@page "Page Title" status:draft
  ...
```
````

If the user asks for a standalone `.ow` file, output the raw DSL without the code fence.

## DSL Syntax Reference

### Core Rules

| Rule | Description |
|---|---|
| Line-based | Each line is a statement |
| Indentation | 2-space indent = child of previous block component |
| `@keyword` | Block components (section, table, etc.) |
| `key: value` | Properties and key-value pairs |
| `**text**` | Bold text |
| `*item*` | Active/selected item in lists |
| `(CODE)` | SRS reference code badge |
| `[Button Text]` | Button |
| `{color}` | Color tag: `{green}`, `{red}`, `{yellow}`, `{blue}`, `{gray}` |
| `---` | Horizontal divider |
| `//` | Comment (not rendered) |
| `|` | Column separator in tables, grids, nav items |

### Block Components

#### @page - Page Container (REQUIRED - always the root element)
```
@page "Page Title" status:draft
```
- `status:` values: `draft` (red ribbon), `review` (yellow ribbon), `approved` (green ribbon)
- All other components must be children (indented) under @page

#### @nav - Top Navigation Bar
```
@nav
  Logo Text | Item 1 | *Active Item* | Item 3
```
- First item becomes the logo (left-aligned, bold)
- `*item*` marks the active/selected tab

#### @breadcrumb - Breadcrumb Navigation
```
@breadcrumb
  Home > Section > Sub > **Current Page**
```

#### @section - Framed Panel with Title
```
@section "Section Title" icon:info ref:FR-001
  // child components go here
```
- `icon:` options: `info`, `check`, `lock`, `star`, `currency`, `play`, `chart`, `user`, `settings`, `doc`, `clock`, `warning`
- `ref:` SRS reference code(s), comma-separated
- Sections can contain any other components as children

#### @grid - Key-Value Info Display
```
@grid cols:2
  Label One   : **Value One**
  Label Two   : {blue}Some Status
  Label Three : **Another Value** (REF-CODE)
```
- `cols:` number of columns (1, 2, or 3; default: 2)
- Each line: `label : value` format
- Values support inline markup: `**bold**`, `{color}text`, `(REF)`

#### @badges - Status Badge Row
```
@badges
  {green} Step 1: PASSED
  {yellow} Step 2: WARNING
  {red} Step 3: FAILED
  {gray} Step 4: PENDING
```
- Each line: `{color} text`
- Colors: green, red, yellow, blue, gray

#### @tabs - Tab Navigation
```
@tabs
  *Active Tab* | Tab Two | Tab Three | Tab Four
```
- `*tab*` marks the active tab

#### @table - Data Table
```
@table ref:FR-002
  # | Name | Status | Score | Action
  --
  1 | **Alice** | {green}Active | 95 | [View]
  2 | **Bob** | {red}Inactive | 42 | [View]
```
- First row = headers (separated by `|`)
- `--` = separator line between header and body rows
- Body rows: cells separated by `|`
- `{color}text` = colored cell content
- `[text]` = button in cell
- `**text**` = bold text in cell

#### @buttons - Button Group
```
@buttons
  [primary] Save Changes
  [success] Approve
  [danger] Delete
  [default] Cancel
```
- Styles: `primary` (blue), `success` (green), `danger` (red), `default` (outlined)

#### @form - Form Layout
```
@form cols:2 ref:FR-003
  text     "Field Label"      required
  text     "Read Only"        readonly value:"Prefilled"
  select   "Dropdown"         options:"Option A,Option B,Option C"
  date     "Date Field"       required
  number   "Amount"           required
  textarea "Description"      rows:3
  file     "Upload"           accept:".pdf,.docx"
  checkbox "I agree to terms"
  radio    "Priority"         options:"High,Normal,Low"
```
- `cols:` 1, 2, or 3 column layout
- Field types: `text`, `select`, `date`, `number`, `textarea`, `file`, `checkbox`, `radio`
- Modifiers: `required`, `readonly`, `value:"..."`, `options:"..."`, `rows:N`, `accept:"..."`

#### @note - Annotation/Note Box
```
@note type:info
  This is an informational note.
```
- `type:` values: `info` (default), `warning`, `error`, `success`

#### @alert - Inline Alert Box
```
@alert type:warning ref:RULE-001
  Important warning message here.
```
- `type:` values: `info`, `warning`, `error`, `success`

#### @placeholder - Placeholder Area (for charts, embeds, etc.)
```
@placeholder height:100
  Chart Area - Revenue Trend
```
- `height:` minimum height in pixels (default: 80)

#### @formula - Formula/Code Box
```
@formula
  Total = Price x Quantity x (1 + Tax Rate)
```

#### @locked - Locked/Disabled Overlay
```
@locked "Reason this area is locked"
  @table
    1 | Locked Item | -- | -- | --
```
- Shows child content dimmed with a lock overlay
- Use for areas that are conditionally disabled

#### @radio - Standalone Radio Button Group
```
@radio "Decision"
  *Selected Option* | Option B | Option C
```
- `*option*` marks the selected option

#### @textarea - Standalone Textarea
```
@textarea "Comments" rows:4
  Default text content goes here.
```

#### @divider - Horizontal Rule
```
@divider
```

#### @footer - Page Footer
```
@footer
  Left content | Right content
```

#### @columns - Side-by-side Layout
```
@columns 2
  @col
    // left side content
  @col
    // right side content
```

#### @progress - Progress/Steps Indicator
```
@progress
  {done} Step 1 | {done} Step 2 | {active} Step 3 | {pending} Step 4
```
- Step states: `{done}` (green), `{active}` (blue, bold), `{pending}` (gray)

#### @metric - KPI Metric Cards
```
@metric
  "Card Label" : **42** icon:chart {blue}
  "Another"    : **128** icon:user {green}
```
- Each line: `"label" : **value** icon:name {color}`
- Icons: same as @section icons

## Best Practices

1. **Always start with `@page`** - it's the root container
2. **Use `@nav` first** inside the page for navigation context
3. **Use `@breadcrumb`** after nav for location context
4. **Group related content in `@section`** blocks with meaningful titles
5. **Use `ref:` codes** to link wireframe elements to requirements/specs
6. **Set `status:draft`** for work-in-progress wireframes
7. **Use 2-space indentation consistently** - the parser is indent-sensitive
8. **Use `@columns`** for side-by-side layouts (e.g., form + preview)
9. **Use `@progress`** to show multi-step workflows
10. **Use `@metric`** cards for dashboard KPI summaries
11. **Add `@footer`** for audit trails and metadata

## Complete Example

```omniware
@page "User Management" status:draft

@nav
  MyApp | Dashboard | *Users* | Settings | Reports

@breadcrumb
  Home > Administration > **User Management**

@section "Overview" icon:chart ref:FR-USR-001
  @metric
    "Total Users"   : **1,247** icon:user {blue}
    "Active"        : **1,102** icon:check {green}
    "Pending"       : **89** icon:clock {yellow}
    "Suspended"     : **56** icon:lock {red}

@section "User List" icon:user ref:FR-USR-002
  @table
    # | Name | Email | Role | Status | Actions
    --
    1 | **John Smith** | john@example.com | Admin | {green}Active | [Edit] [View]
    2 | **Jane Doe** | jane@example.com | Editor | {green}Active | [Edit] [View]
    3 | **Bob Wilson** | bob@example.com | Viewer | {yellow}Pending | [Approve] [Reject]
  @buttons
    [primary] + Add New User
    [default] Export CSV
    [default] Import Users

@section "Add User" icon:user ref:FR-USR-003
  @form cols:2
    text     "First Name"     required
    text     "Last Name"      required
    text     "Email"          required
    select   "Role"           options:"Admin,Editor,Viewer,Guest"
    select   "Department"     options:"Engineering,Marketing,Sales,Support"
    checkbox "Send welcome email"
  @buttons
    [primary] Create User
    [default] Cancel

@footer
  All actions are logged for audit compliance (NFR-AUD)
  Last updated: admin01 - 2027-02-15 14:30
```
