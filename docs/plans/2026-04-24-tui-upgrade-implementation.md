# TUI Upgrade Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a polished interactive terminal UI with first-class slash commands, a visual command palette, and transparent agent execution feedback.

**Architecture:** Use a `CommandRegistry` for extensibility, a visual `CommandPalette` widget for discovery, and a `SessionManager` for persistence.

**Tech Stack:** Python, Textual, Pydantic.

---

### Task 1: Command Registry Infrastructure

**Files:**
- Create: `xfusion/app/commands/__init__.py`
- Create: `xfusion/app/commands/base.py`
- Create: `xfusion/app/commands/registry.py`

- [ ] **Step 1: Define `BaseCommand`**
  ```python
  from abc import ABC, abstractmethod
  from typing import TYPE_CHECKING, List

  if TYPE_CHECKING:
      from xfusion.app.tui import XFusionTUI

  class BaseCommand(ABC):
      name: str
      aliases: List[str] = []
      description: str
      usage: str
      is_client_only: bool = True

      @abstractmethod
      async def handle(self, app: "XFusionTUI", args: List[str]) -> None:
          pass
  ```
- [ ] **Step 2: Implement `CommandRegistry`**
  ```python
  from typing import Dict, List, Optional
  from xfusion.app.commands.base import BaseCommand

  class CommandRegistry:
      def __init__(self):
          self.commands: Dict[str, BaseCommand] = {}
          self.alias_map: Dict[str, str] = {}

      def register(self, command: BaseCommand):
          self.commands[command.name] = command
          for alias in command.aliases:
              self.alias_map[alias] = command.name

      def find(self, trigger: str) -> Optional[BaseCommand]:
          name = self.alias_map.get(trigger, trigger)
          return self.commands.get(name)

      def search(self, query: str) -> List[BaseCommand]:
          query = query.lower()
          return [
              cmd for cmd in self.commands.values()
              if query in cmd.name.lower() or any(query in a.lower() for a in cmd.aliases)
          ]
  ```
- [ ] **Step 3: Commit infrastructure**
  ```bash
  git add xfusion/app/commands/
  git commit -m "feat(tui): add command registry infrastructure"
  ```

---

### Task 2: Core Slash Commands

**Files:**
- Create: `xfusion/app/commands/core.py`

- [ ] **Step 1: Implement `/exit`, `/help`, `/new`**
- [ ] **Step 2: Implement `/debug`, `/clear`**
- [ ] **Step 3: Commit core commands**

---

### Task 3: Visual Command Palette

**Files:**
- Modify: `xfusion/app/tui.py`

- [ ] **Step 1: Implement `CommandPalette` and `CommandItem` widgets**
- [ ] **Step 2: Add `CommandPalette` to TUI layout**
- [ ] **Step 3: Implement visibility and filtering logic in `on_input_changed`**
- [ ] **Step 4: Commit UI changes**

---

### Task 4: Slash Command Interceptor

**Files:**
- Modify: `xfusion/app/tui.py`

- [ ] **Step 1: Update `on_input_submitted` to intercept slash commands**
- [ ] **Step 2: Route to `CommandRegistry`**
- [ ] **Step 3: Implement graceful error handling and suggestions for unknown commands**
- [ ] **Step 4: Commit interceptor**

---

### Task 5: Session Management

**Files:**
- Create: `xfusion/app/sessions.py`
- Modify: `xfusion/app/tui.py`

- [ ] **Step 1: Implement `SessionManager` for state persistence**
- [ ] **Step 2: Implement `/sessions`, `/resume`, `/history` commands**
- [ ] **Step 3: Commit session management**

---

### Task 6: Status & Permissions Commands

**Files:**
- Create: `xfusion/app/commands/info.py`

- [ ] **Step 1: Implement `/status`, `/permissions`, `/model`, `/config`**
- [ ] **Step 2: Commit info commands**

---

### Task 7: Verification & Polishing

**Files:**
- Create: `tests/test_tui_commands.py`

- [ ] **Step 1: Write integration tests for slash command interception**
- [ ] **Step 2: Verify `/debug` verbose output**
- [ ] **Step 3: Verify session persistence**
- [ ] **Step 4: Final commit and cleanup**
