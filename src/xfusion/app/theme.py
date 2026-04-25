from __future__ import annotations

APP_CSS = """
Screen {
    background: transparent;
    color: $text;
}

#status-bar {
    dock: top;
    height: 1;
    background: transparent;
    color: $text-muted;
    padding: 0 1;
}

#timeline {
    height: 1fr;
    padding: 1 2 0 2;
    overflow-y: scroll;
}

#sidebar {
    width: 40;
    border-left: solid $border;
    background: transparent;
    display: none;
    padding: 1;
}

#sidebar .sidebar-title {
    color: $accent;
    text-style: bold;
}

.user-message {
    margin: 1 0 0 0;
    color: $text;
    text-style: bold;
}

.welcome-line {
    margin: 0 0 1 0;
    color: $text-muted;
}

AgentMessage {
    margin: 1 0;
    padding: 0;
}

#turn-header {
    color: $accent;
    text-style: bold;
}

#plan-info {
    margin: 0 0 1 0;
    color: $primary;
}

#steps {
    margin: 1 0;
    height: auto;
}

StepWidget {
    margin: 0 0 1 0;
    padding: 0 1;
    border-left: tall $border;
}

#policy-info {
    color: $warning;
}

#debug-info {
    margin-top: 1;
    border: solid $border;
    padding: 0 1;
}

.debug-header {
    color: $warning;
    text-style: bold;
}

.debug-entry {
    text-style: dim;
}

#explanation-block {
    margin-top: 1;
}

#interpretation-header {
    margin-bottom: 0;
    color: $accent;
}

Markdown {
    padding: 0;
}

Markdown H1 {
    color: $accent;
    text-style: bold;
}

Markdown H2 {
    color: $primary;
    text-style: bold;
}

Markdown Bullet {
    color: $warning;
}

#input-container {
    dock: bottom;
    height: 3;
    padding: 0 1;
    background: transparent;
    border-top: solid $border;
}

#prompt-label {
    color: $accent;
    text-style: bold;
    margin-right: 1;
    width: auto;
}

#main-input {
    border: none;
    background: transparent;
    color: $text;
    width: 1fr;
    height: 1;
    padding: 0 1;
}

#main-input:focus {
    border: none;
    background: $boost;
}
"""


def command_table_styles() -> dict[str, str]:
    return {
        "primary": "bold",
        "muted": "dim",
        "text": "",
    }
