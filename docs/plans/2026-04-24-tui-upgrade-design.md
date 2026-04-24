# TUI Upgrade: Modern Agent CLI for XFusion Guardian

## Overview
Upgrade the XFusion TUI to provide a polished, interactive "Guardian" experience with first-class slash commands, a visual command palette, and robust session management.

## Goals
- Professional, keyboard-first interaction.
- Visual command palette for discovery.
- Transparent agent execution feedback (Debug mode).
- Robust session persistence and lifecycle management.
- Zero token consumption for local commands.

## Architecture

### 1. Command Registry (`xfusion/app/commands/`)
- `BaseCommand`: Abstract base class for all slash commands.
- `CommandRegistry`: Singleton-like registry for command discovery and dispatch.
- `CommandHandler`: Logic to parse and route input.

### 2. Command Palette UI (`xfusion/app/tui.py`)
- `CommandPalette(Vertical)`: A floating overlay widget.
- `CommandItem(Static)`: Individual command display in the palette.
- Fuzzy filtering logic using simple substring matching (extensible).

### 3. Session Management (`xfusion/app/sessions.py`)
- `SessionManager`: Handles saving/loading `AgentGraphState` to/from `~/.xfusion/sessions/`.
- UUID-based session IDs.

### 4. Implementation Details

#### Slash Commands
- `/help`: Lists registered commands and their descriptions.
- `/debug`: Toggles a verbose rendering mode in the TUI.
- `/new`: Resets current `AgentGraphState` and generates a new session ID.
- `/clear`: Visually clears the `#timeline` widget.
- `/status`: Displays environment and session metadata.
- `/permissions`: Summarizes active policy and risk levels.
- `/exit` / `/quit`: Gracefully shuts down the Textual app.

#### UI/UX
- Persistent status bar at the top showing current session, mode, and target.
- Bottom input area with `/` trigger for palette.
- Arrow-key/Enter navigation for command selection.

## Testing Strategy
- **Unit Tests**: Test `CommandRegistry` discovery and `CommandHandler` parsing.
- **Integration Tests**: Verify slash commands are intercepted before agent dispatch.
- **TUI Tests**: Use Textual's testing framework to simulate typing `/` and selecting commands.

## Implementation Plan (Summary)
1. Create `xfusion/app/commands/` and `xfusion/app/sessions.py`.
2. Implement `CommandRegistry` and core commands (`/help`, `/exit`, `/new`).
3. Update `xfusion/app/tui.py` with `CommandPalette` and interceptor logic.
4. Implement remaining slash commands.
5. Add TUI enhancements (Status bar, Debug view).
6. Verify and Test.
