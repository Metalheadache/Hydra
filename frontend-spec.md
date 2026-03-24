# OpenClaw Prompt: LLM Chat Frontend (React Single-File)

## Overview

Build a **single-file React component** (`App.jsx`) for an LLM chat interface. The design language is **glassmorphism with neon-blue accents** — frosted glass panels, backdrop-filter blur, subtle glow effects, and spring-curve animations. Think Apple Control Center meets iMessage, rendered in a dark sci-fi palette.

The attached `react-app.js` is the **canonical style reference**. Match its exact design tokens, animation curves, and glassmorphism treatment. Do not deviate from its aesthetic.

---

## Design System (extracted from reference)

### Color Tokens (CSS-in-JS, theme-aware)

```
// DARK MODE
--bg-color: #05070a
--bg-gradient: radial-gradient(circle at 20% 20%, rgba(0,37,201,0.1) 0%, transparent 40%),
               radial-gradient(circle at 80% 80%, rgba(74,109,229,0.06) 0%, transparent 40%)
--glass-bg-base: linear-gradient(180deg, rgba(200,220,255,0.05) 0%, rgba(255,255,255,0.02) 100%)
--glass-bg-focus: linear-gradient(180deg, rgba(160,210,255,0.08) 0%, rgba(255,255,255,0.04) 100%)
--glass-border: rgba(192,192,192,0.2)
--glass-border-focus: rgba(160,230,255,0.6)
--glass-shadow: inset 0 1px 1px rgba(255,255,255,0.1), 0 0 20px rgba(0,0,0,0.4)
--neon-glow: 0 0 20px rgba(0,37,201,0.35), inset 0 0 5px rgba(255,255,255,0.05)
--text-primary: #f0f2f5
--text-secondary: #94a3b8
--accent-primary: #0025C9
--accent-hover: #4a6de5
--accent-glow: rgba(0,37,201,0.35)

// LIGHT MODE
--bg-color: #f0f4f8
--bg-gradient: radial-gradient(circle at 15% 20%, rgba(0,37,201,0.15) 0%, transparent 45%),
               radial-gradient(circle at 85% 75%, rgba(26,71,255,0.1) 0%, transparent 40%),
               radial-gradient(circle at 50% 50%, rgba(255,255,255,0.5) 0%, transparent 70%)
--glass-bg-base: linear-gradient(180deg, rgba(255,255,255,0.7) 0%, rgba(255,255,255,0.4) 100%)
--glass-bg-focus: linear-gradient(180deg, rgba(255,255,255,0.9) 0%, rgba(255,255,255,0.6) 100%)
--glass-border: rgba(255,255,255,0.6)
--glass-border-focus: rgba(160,230,255,0.6)
--text-primary: #0f172a
--text-secondary: #64748b
--control-center-bg: rgba(255,255,255,0.7)
--control-center-border: rgba(255,255,255,0.8)
```

### Animation Curves
- **Spring easing (primary):** `cubic-bezier(0.16, 1, 0.3, 1)` — used for all major transitions (panel open/close, input morph, bubble entry)
- **Soft ease:** `ease 0.3s` — used for hover states, color transitions
- **Duration:** 0.3s–0.5s for interactions, 0.6s–0.8s for the input-bar fold animation

### Glass Treatment (apply to ALL panels/containers)
```css
backdrop-filter: blur(24px);
-webkit-backdrop-filter: blur(24px);
border: 1px solid var(--glass-border);
border-radius: 20px; /* panels */ | 999px /* pill shapes */;
box-shadow: var(--glass-shadow);
```

### Typography
```
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
-webkit-font-smoothing: antialiased;
```

---

## Architecture

### State Machine

The app has two primary states:

```
IDLE → (user sends prompt) → CHAT_ACTIVE
```

- **IDLE state:** Input bar is centered vertically on screen, full width (max ~520px). No chat history visible. Clean landing state.
- **CHAT_ACTIVE state:** First message has morphed into a bubble in the upper-right area. A chat container fills the screen. A new input bar is docked at the bottom.

### Component Hierarchy

```
<App>
  ├── <SettingsButton />          // fixed top-left, gear icon
  │   └── <ControlCenterPanel />  // macOS-style dropdown
  ├── <InitialInputBar />         // centered, visible in IDLE state
  ├── <ChatContainer />           // visible in CHAT_ACTIVE state
  │   ├── <MessageBubble />[]     // iMessage-style, user=right, assistant=left
  │   └── <ChatInputBar />        // docked bottom
  └── <MorphingBubble />          // animation overlay for the fold transition
```

---

## Feature Specifications

### 1. Initial Input Bar (IDLE State)

- Centered both horizontally and vertically on screen
- Pill-shaped container (border-radius: 999px), matching the reference's search bar style
- Height: 52px, max-width: 520px, responsive width (90vw on mobile)
- Interior layout: `[📎 Upload] [divider] [text input] [divider] [Send ▶]`
- The upload button (📎 paperclip icon) opens a native file picker (`<input type="file" multiple hidden>`)
- Uploaded files show as small pill-shaped chips below the input bar with filename + ✕ remove button
- Send button: circular, neon-blue glow on hover, disabled when input is empty
- Placeholder text: `"Describe your task..."` in accent blue, matching reference's placeholder style
- On focus: input bar expands width slightly (like the reference search bar), border glows with `--glass-border-focus`, box-shadow transitions to `--neon-glow`

### 2. Settings Button & Control Center Panel

- **Settings button:** Fixed position, top: 24px, left: 24px. Circular (44×44px), gear icon (SVG). Exact same hover/active states as the reference — scale(1.05), neon border glow, background color shift.
- **Control Center panel:** Drops down below the button (top: calc(100% + 12px)), 360px wide. Same glassmorphism treatment, same open/close animation (opacity + translateY + scale with spring curve). Click-outside-to-close behavior.

**Panel contents (top to bottom):**
### Note: detailed section and default values should refer to config.py and .env.example. Below is an example for section name and description
| Section | UI Element | Description |
|---------|-----------|-------------|
| API Base URL | Text input field | Glass-styled input, placeholder: `https://api.example.com/v1` |
| API Key | Password input field | Masked by default, eye-toggle to reveal. Glass-styled. |
| Model | Dropdown select | Glass-styled select or custom dropdown. Default options: `gpt-4o`, `claude-sonnet-4-20250514`, `deepseek-r1`, `qwen-max`. Editable — user can type a custom model string. |
| Max Tokens | Slider + numeric display | Range: 256–32768, default: 4096. Slider styled like the reference's brightness/volume sliders (thin track, gradient fill `#4a6de5 → #0025C9`, glow). |
| Max Tokens per Agent | Slider + numeric display | Range: 256–16384, default: 2048. Same slider style. |
| Temperature | Slider + numeric display | Range: 0.0–2.0, step: 0.1, default: 0.7. Same slider style. |
| Top P | Slider + numeric display | Range: 0.0–1.0, step: 0.05, default: 1.0. Same slider style. |
| Stop Sequences | Tag input | User can type and press Enter to add stop sequence tags. Each tag is a removable pill. |
| Timeout (seconds) | Number input | Default: 120. Glass-styled input. |
| Dark Mode | Toggle switch | Exact same toggle as reference — pill shape, sliding circle, neon glow when active. Placed at bottom of panel as a visual separator. |

All settings should be stored in a single `config` state object and persisted to `localStorage` so they survive page reload.

### 3. The Fold Animation (IDLE → CHAT_ACTIVE Transition)

This is the signature interaction. When the user hits Send:

**Step-by-step animation sequence (total ~800ms):**

1. **Frame 0–200ms:** The initial input bar's text content fades out slightly. The pill container begins shrinking in width and translating toward the upper-right corner of the viewport.
2. **Frame 200–500ms:** The container continues moving to its final position (top-right, with padding ~24px from edges). It morphs from full-width pill → compact chat bubble shape (max-width: 60%, border-radius: 20px 20px 4px 20px — iMessage style with the sharp corner at bottom-right for user messages).
3. **Frame 500–800ms:** The chat container fades/slides in from the bottom. The bottom-docked input bar appears with a subtle upward slide.

**Implementation approach:**
- Use a `position: fixed` overlay element that captures the initial input bar's bounding rect via `getBoundingClientRect()`
- Animate `top`, `left`, `width`, `height`, `border-radius` using CSS transitions with the spring curve
- Use `requestAnimationFrame` or `onTransitionEnd` to sequence the phases
- The morphing element contains the user's actual message text, so it becomes the first chat bubble seamlessly
- After the animation completes, unmount the overlay and render the message as a normal `<MessageBubble>` component

### 4. Chat Interface (CHAT_ACTIVE State)

**Layout:**
```
┌──────────────────────────────────────────┐
│ [⚙ Settings]                             │  ← fixed top-left (always visible)
│                                          │
│        ┌──────────────────┐              │
│        │  User's message  │──────────────│  ← right-aligned bubble
│        └──────────────────┘              │
│  ┌──────────────────┐                    │
│  │ LLM response     │                   │  ← left-aligned bubble
│  │ (streaming...)   │                   │
│  └──────────────────┘                    │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │ [📎] │ Continue chatting...  │[⏹/▶]│  │  ← bottom-docked input
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

**Message Bubbles:**
- User messages: right-aligned, accent blue background (`rgba(0,37,201,0.15)` dark / `rgba(0,37,201,0.1)` light), border-radius: `20px 20px 4px 20px`
- Assistant messages: left-aligned, glass background (`--glass-bg-base`), border-radius: `20px 20px 20px 4px`
- Both bubble types: padding 14px 18px, max-width 70% of container, glassmorphism border treatment
- Text: 15px, `--text-primary` color, line-height 1.5
- Bubbles should have entry animations — slide up + fade in, staggered by 50ms if multiple
- **Responsive:** bubble max-width adapts to viewport. On mobile (<640px), max-width: 85%. On desktop (>1024px), max-width: 60%.
- Auto-scroll to bottom on new messages. Use `scrollIntoView({ behavior: 'smooth' })`.

**Bottom Chat Input Bar:**
- Docked at bottom with padding (24px sides, 16px bottom)
- Same pill-shaped glass container as the initial input bar
- Interior: `[📎 Upload] [divider] [text input] [divider] [Send/Stop]`
- **Send button** (▶ icon): visible when LLM is NOT streaming
- **Stop button** (⏹ icon): replaces Send when LLM IS streaming. Red-tinted glow (`rgba(239,68,68,0.3)`). Clicking it aborts the fetch/stream via `AbortController`.
- Smooth crossfade animation between Send ↔ Stop icons (opacity + scale transition, 200ms)

### 5. Streaming & API Integration

**API call structure (placeholder — user will customize later):**

```javascript
const response = await fetch(`${config.apiBaseUrl}/chat/completions`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${config.apiKey}`,
  },
  signal: abortController.signal,
  body: JSON.stringify({
    model: config.model,
    messages: conversationHistory,  // [{role, content}]
    max_tokens: config.maxTokens,
    temperature: config.temperature,
    top_p: config.topP,
    stream: true,
  }),
});
```

- Parse SSE stream (`text/event-stream`): read line-by-line, extract `data:` payloads, parse JSON, concatenate `choices[0].delta.content` tokens
- Handle `[DONE]` signal to mark stream complete
- On stream complete: flip `isStreaming` to false, re-enable Send button
- On abort: append `[Stopped]` indicator to the partial message
- On error: show error as a system message bubble (centered, muted red glass treatment)

**File upload handling:**
- Store uploaded files in state as `{ name, size, file }` objects
- Display as removable pills below the input
- When sending, include file info in the message payload (base64 encode or FormData — leave as a TODO comment for user to implement their backend's expected format)

### 6. Dark Mode / Light Mode

- Default: dark mode ON
- Toggle in Settings panel controls `isDark` state
- ALL color values must branch on `isDark` — backgrounds, text, borders, shadows, bubble colors
- Transition between modes: `transition: background-color 0.4s ease` on root container
- Persist preference to `localStorage`

### 7. Responsive Design

- Breakpoints: mobile (<640px), tablet (640–1024px), desktop (>1024px)
- Initial input bar: 90vw on mobile, 520px max on desktop
- Chat bubbles: max-width scales (85% mobile, 70% tablet, 60% desktop)
- Settings panel: full-width overlay on mobile (with backdrop dim), dropdown on desktop
- Bottom input bar: full-width with 12px side padding on mobile, centered max-width 720px on desktop
- Use CSS `@media` queries injected via `<style>` element (matching reference's pattern) or inline responsive logic

### 8. Keyboard & UX Details

- `Enter` to send (when input is focused and non-empty)
- `Shift+Enter` for newline in input (use `<textarea>` with auto-resize, not `<input>`)
- `Escape` to close Settings panel
- Auto-focus input on page load
- Textarea auto-grows up to 120px height, then scrolls internally
- Smooth scroll-to-bottom in chat container on each new token during streaming

---

## Code Conventions

- **Single file:** Everything in one `App.jsx`. No external CSS files. All styles inline (CSS-in-JS objects), matching the reference's approach.
- **No external dependencies** beyond React itself. All icons are inline SVGs.
- **State management:** `useState` + `useRef` + `useEffect`. No Redux, no context (unless you need theme context — keep it simple).
- **Dynamic styles:** Inject a `<style>` element in a `useEffect` for pseudo-elements and media queries (same pattern as the reference file).
- **Clean code:** Well-commented sections, descriptive variable names, logical component grouping within the file.

---

## Deliverable

1. Renders immediately with no build errors
2. Matches the reference's glassmorphism aesthetic pixel-perfectly
3. Implements the full IDLE → fold animation → CHAT_ACTIVE flow
4. Has a working Settings panel with all config fields
5. Streams LLM responses with Send/Stop toggle
6. Supports dark/light mode with smooth transitions
7. Persists settings and theme preference to localStorage
