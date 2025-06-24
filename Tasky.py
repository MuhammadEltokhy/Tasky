import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Static, Input, Footer, Header, Label, Button, ListView, ListItem
from textual.screen import ModalScreen
from textual.reactive import reactive
from textual.message import Message
from textual.binding import Binding
from textual import events
from rich.text import Text
from rich.console import Console


@dataclass
class Task:
    id: str
    title: str
    completed: bool = False
    priority: str = "normal"  
    tags: List[str] = None
    created_at: str = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
    
    @property
    def status_icon(self) -> str:
        return "✅" if self.completed else "❗"
    
    @property
    def priority_icon(self) -> str:
        icons = {"low": "🔽", "normal": "➖", "high": "🔴"}
        return icons.get(self.priority, "➖")


class TaskDetailModal(ModalScreen):
    def __init__(self, task: Task) -> None:
        self.task = task
        super().__init__()
    
    def compose(self) -> ComposeResult:
        with Container(id="detail-modal"):
            yield Static(f"[bold blue]Task Details[/bold blue]", id="modal-title")
            yield Static(f"[bold]Title:[/bold] {self.task.title}")
            yield Static(f"[bold]Status:[/bold] {'Completed' if self.task.completed else 'Pending'}")
            yield Static(f"[bold]Priority:[/bold] {self.task.priority.title()}")
            yield Static(f"[bold]Tags:[/bold] {', '.join(self.task.tags) if self.task.tags else 'None'}")
            yield Static(f"[bold]Created:[/bold] {self.task.created_at[:19]}")
            yield Button("Close", variant="primary", id="close-button")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-button":
            self.dismiss()


class AddTaskModal(ModalScreen):    
    def compose(self) -> ComposeResult:
        with Container(id="add-modal"):
            yield Static("[bold green]Add New Task[/bold green]", id="modal-title")
            yield Label("Task Title:")
            yield Input(placeholder="Enter task title...", id="title-input")
            yield Label("Priority:")
            yield Input(placeholder="low, normal, high (default: normal)", id="priority-input")
            yield Label("Tags (comma-separated):")
            yield Input(placeholder="work, personal, urgent...", id="tags-input")
            with Horizontal():
                yield Button("Add Task", variant="success", id="add-button")
                yield Button("Cancel", variant="error", id="cancel-button")
    
    def on_mount(self) -> None:
        self.query_one("#title-input").focus()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-button":
            title = self.query_one("#title-input").value.strip()
            priority = self.query_one("#priority-input").value.strip() or "normal"
            tags_input = self.query_one("#tags-input").value.strip()
            
            if title:
                tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()]
                task_data = {
                    "title": title,
                    "priority": priority if priority in ["low", "normal", "high"] else "normal",
                    "tags": tags
                }
                self.dismiss(task_data)
            else:
                pass
        elif event.button.id == "cancel-button":
            self.dismiss(None)


class TaskManagerApp(App):
    
    CSS = """
    Screen {
        background: $background;
    }
    
    .light {
        background: white;
        color: black;
    }
    
    .dark {
        background: $background;
        color: $text;
    }
    
    Header {
        dock: top;
        height: 3;
        background: $primary;
        color: $text;
    }
    
    Footer {
        dock: bottom;
        height: 3;
        background: $primary;
        color: $text;
    }
    
    #main-container {
        height: 1fr;
        margin: 1;
    }
    
    #task-table {
        width: 3fr;
        border: solid $primary;
        margin-right: 1;
    }
    
    #detail-panel {
        width: 2fr;
        border: solid $accent;
        padding: 1;
        background: $surface;
    }
    
    #search-container {
        dock: top;
        height: 3;
        padding: 1;
        background: $surface;
    }
    
    #search-input {
        width: 1fr;
    }
    
    DataTable {
        background: $background;
    }
    
    DataTable > .datatable--header {
        background: $primary;
        color: $text;
        text-style: bold;
    }
    
    DataTable > .datatable--odd-row {
        background: $surface;
    }
    
    DataTable > .datatable--even-row {
        background: $background;
    }
    
    DataTable > .datatable--cursor {
        background: $secondary;
        color: $text;
    }
    
    #detail-modal {
        width: 60;
        height: 20;
        background: $surface;
        border: solid $primary;
        padding: 2;
    }
    
    #add-modal {
        width: 60;
        height: 25;
        background: $surface;
        border: solid $primary;
        padding: 2;
    }
    
    #modal-title {
        text-align: center;
        margin-bottom: 1;
    }
    
    Input {
        margin-bottom: 1;
    }
    
    Button {
        margin: 1;
    }
    """
    
    BINDINGS = [
        Binding("a", "add_task", "Add Task"),
        Binding("c", "complete_task", "Complete"),
        Binding("d", "delete_task", "Delete"),
        Binding("t", "toggle_theme", "Theme"),
        Binding("slash", "search", "Search"),
        Binding("escape", "clear_search", "Clear Search"),
        Binding("enter", "show_details", "Details"),
        Binding("q", "quit", "Quit"),
    ]
    
    # Reactive state
    tasks: reactive[List[Task]] = reactive([])
    current_task: reactive[Optional[Task]] = reactive(None)
    search_filter: reactive[str] = reactive("")
    dark_mode: reactive[bool] = reactive(True)
    
    def __init__(self):
        super().__init__()
        self.tasks_file = Path("tasks.json")
        self.task_counter = 0
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container(id="search-container"):
            yield Input(placeholder="Search tasks... (Press / to focus, Esc to clear)", 
                       id="search-input")
        
        with Horizontal(id="main-container"):
            # Task table on the left
            yield DataTable(id="task-table", cursor_type="row", zebra_stripes=True)
            
            # Detail panel on the right
            with Vertical(id="detail-panel"):
                yield Static("[bold blue]Task Details[/bold blue]", id="detail-title")
                yield Static("Select a task to view details", id="detail-content")
        
        yield Footer()
    
    def on_mount(self) -> None:
        self.load_tasks()
        self.setup_table()
        self.refresh_table()
        self.apply_theme()
    
    def setup_table(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.add_columns("Status", "Priority", "Title", "Tags")
    
    def load_tasks(self) -> None:
        if self.tasks_file.exists():
            try:
                with open(self.tasks_file, 'r') as f:
                    data = json.load(f)
                    self.tasks = [Task(**task) for task in data]
                    if self.tasks:
                        self.task_counter = max(int(task.id) for task in self.tasks) + 1
            except (json.JSONDecodeError, KeyError, ValueError):
                self.tasks = []
    
    def save_tasks(self) -> None:
        try:
            with open(self.tasks_file, 'w') as f:
                json.dump([asdict(task) for task in self.tasks], f, indent=2)
        except Exception as e:
            pass
    
    def get_filtered_tasks(self) -> List[Task]:
        if not self.search_filter:
            return self.tasks
        
        search_lower = self.search_filter.lower()
        return [
            task for task in self.tasks
            if (search_lower in task.title.lower() or 
                any(search_lower in tag.lower() for tag in task.tags))
        ]
    
    def refresh_table(self) -> None:
        table = self.query_one("#task-table", DataTable)
        table.clear()
        
        filtered_tasks = self.get_filtered_tasks()
        
        for task in filtered_tasks:
            tags_str = ", ".join(task.tags) if task.tags else ""
            table.add_row(
                task.status_icon,
                task.priority_icon,
                task.title,
                tags_str,
                key=task.id
            )
        
        if filtered_tasks and not table.cursor_coordinate:
            table.move_cursor(row=0)
            self.update_current_task()
    
    def update_current_task(self) -> None:
        table = self.query_one("#task-table", DataTable)
        if table.cursor_coordinate:
            row_key = table.get_row_at(table.cursor_coordinate.row)[0]  
            filtered_tasks = self.get_filtered_tasks()
            if 0 <= table.cursor_coordinate.row < len(filtered_tasks):
                self.current_task = filtered_tasks[table.cursor_coordinate.row]
            else:
                self.current_task = None
        else:
            self.current_task = None
        
        self.update_detail_panel()
    
    def update_detail_panel(self) -> None:
        detail_content = self.query_one("#detail-content", Static)
        
        if self.current_task:
            task = self.current_task
            content = f"""[bold]Title:[/bold] {task.title}

[bold]Status:[/bold] {'✅ Completed' if task.completed else '❗ Pending'}

[bold]Priority:[/bold] {task.priority_icon} {task.priority.title()}

[bold]Tags:[/bold] {', '.join(task.tags) if task.tags else 'None'}

[bold]Created:[/bold] {task.created_at[:19]}

[dim]Press Enter for detailed view[/dim]"""
        else:
            content = "Select a task to view details"
        
        detail_content.update(content)
    
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.update_current_task()
    
    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self.search_filter = event.value
            self.refresh_table()
    
    async def action_add_task(self) -> None:
        result = await self.push_screen_wait(AddTaskModal())
        if result:
            new_task = Task(
                id=str(self.task_counter),
                title=result["title"],
                priority=result["priority"],
                tags=result["tags"]
            )
            self.task_counter += 1
            self.tasks.append(new_task)
            self.save_tasks()
            self.refresh_table()
    
    def action_complete_task(self) -> None:
        if self.current_task:
            self.current_task.completed = not self.current_task.completed
            self.save_tasks()
            self.refresh_table()
            self.update_detail_panel()
    
    def action_delete_task(self) -> None:
        if self.current_task:
            self.tasks = [task for task in self.tasks if task.id != self.current_task.id]
            self.save_tasks()
            self.refresh_table()
    
    def action_toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self.apply_theme()
    
    def apply_theme(self) -> None:
        if self.dark_mode:
            self.remove_class("light")
            self.add_class("dark")
        else:
            self.remove_class("dark")
            self.add_class("light")
    
    def action_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        search_input.focus()
    
    def action_clear_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        search_input.value = ""
        self.search_filter = ""
        self.refresh_table()
    
    async def action_show_details(self) -> None:
        if self.current_task:
            await self.push_screen_wait(TaskDetailModal(self.current_task))


def main():
    app = TaskManagerApp()
    app.run()


if __name__ == "__main__":
    main()