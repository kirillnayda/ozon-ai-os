from app.core.security import html_escape
from app.developer_agent.task_models import DeveloperTask


def build_task_report(task: DeveloperTask) -> str:
    files = "\n".join(f"• <code>{html_escape(path)}</code>" for path in task.changed_files) or "нет"
    tests = task.test_output[-2000:] or "не запускались"
    error = f"\n\n<b>Ошибка</b>\n<code>{html_escape(task.error[-1500:])}</code>" if task.error else ""
    return (
        f"<b>Developer Agent · задача #{task.id}</b>\n"
        f"Состояние: {task.state.value}\n"
        f"Ветка: <code>{html_escape(task.branch)}</code>\n\n"
        f"<b>Результат</b>\n{html_escape(task.summary or 'Нет описания')}\n\n"
        f"<b>Изменённые файлы</b>\n{files}\n\n"
        f"<b>Тесты</b>\n<code>{html_escape(tests)}</code>{error}"
    )
