from __future__ import annotations

from dataclasses import dataclass

from app.core.security import html_escape
from app.developer_agent.report_builder import build_task_report
from app.developer_agent.task_models import ACTIVE_STATES, DeveloperTaskState
from app.developer_agent.task_repository import SQLiteDeveloperTaskRepository


@dataclass(frozen=True)
class DeveloperHandlerResult:
    text: str
    keyboard: dict | None = None


def task_keyboard(task_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "Отправить ветку в GitHub", "callback_data": f"dev:push:{task_id}"},
        {"text": "Отклонить", "callback_data": f"dev:reject:{task_id}"},
    ]]}


class DeveloperAgentTelegramHandlers:
    def __init__(self, repository: SQLiteDeveloperTaskRepository, allowed_chat_id: int, max_attempts: int = 2) -> None:
        self.repository, self.allowed_chat_id, self.max_attempts = repository, allowed_chat_id, max_attempts
        self.repository.migrate()

    async def message(self, chat_id: int, text: str) -> DeveloperHandlerResult | None:
        if chat_id != self.allowed_chat_id:
            return None
        stripped = text.strip()
        command, _, argument = stripped.partition(" ")
        command = command.split("@", 1)[0].lower()
        if command == "/dev":
            if not argument.strip():
                return DeveloperHandlerResult("Формат: <code>/dev описание задачи</code>")
            task = self.repository.create(chat_id, argument, self.max_attempts)
            return DeveloperHandlerResult(f"Задача #{task.id} добавлена в очередь.\nВетка: <code>{html_escape(task.branch)}</code>")
        if command == "/dev_status":
            task = self.repository.latest_for_chat(chat_id)
            return DeveloperHandlerResult(build_task_report(task) if task else "Задач пока нет.")
        if command == "/dev_queue":
            tasks = self.repository.list_recent(chat_id)
            lines = [f"#{task.id} · {task.state.value} · {html_escape(task.description[:80])}" for task in tasks]
            return DeveloperHandlerResult("<b>Очередь Developer Agent</b>\n" + ("\n".join(lines) or "Пусто"))
        if command == "/dev_plan":
            task = self.repository.latest_for_chat(chat_id)
            return DeveloperHandlerResult(f"<b>План задачи #{task.id}</b>\n{html_escape(task.plan or 'План ещё не подготовлен.')}" if task else "Задач пока нет.")
        if command == "/dev_cancel":
            if argument.strip() and not argument.strip().isdigit():
                return DeveloperHandlerResult("Формат: <code>/dev_cancel [номер задачи]</code>")
            task = self.repository.get(int(argument)) if argument.strip() else self.repository.latest_for_chat(chat_id)
            if not task:
                return DeveloperHandlerResult("Задач пока нет.")
            task = self.repository.request_cancel(task.id, chat_id)
            return DeveloperHandlerResult(f"Задача #{task.id}: запрос отмены принят ({task.state.value}).")
        return None

    async def callback(self, chat_id: int, data: str) -> DeveloperHandlerResult | None:
        if chat_id != self.allowed_chat_id:
            return None
        parts = data.split(":")
        if len(parts) != 3 or parts[0] != "dev" or not parts[2].isdigit():
            return None
        task_id = int(parts[2])
        task = self.repository.get(task_id)
        if not task or task.chat_id != chat_id:
            raise PermissionError("Задача не найдена")
        if parts[1] == "push":
            if task.state != DeveloperTaskState.READY:
                return DeveloperHandlerResult("Отправить можно только готовую задачу.")
            if task.pushed:
                return DeveloperHandlerResult(f"Ветка задачи #{task.id} уже отправлена.")
            self.repository.update(task.id, push_requested=True)
            return DeveloperHandlerResult(f"Push ветки задачи #{task.id} поставлен в очередь.")
        if parts[1] == "reject":
            if task.pushed:
                return DeveloperHandlerResult("Уже отправленную ветку нельзя отклонить через бота.")
            if task.state in ACTIVE_STATES:
                self.repository.update(task.id, cancel_requested=True)
            elif task.state in {DeveloperTaskState.QUEUED, DeveloperTaskState.READY}:
                self.repository.update(task.id, state=DeveloperTaskState.CANCELLED)
            else:
                return DeveloperHandlerResult(f"Задача #{task.id} уже завершена ({task.state.value}).")
            return DeveloperHandlerResult(f"Задача #{task.id} отклонена. Ветка не отправлена.")
        return None
