"""Пакет управления фоновыми задачами и асинхронной обработки документов."""
from .task_manager import task_manager, BackgroundTask, TaskStatus

__all__ = ['task_manager', 'BackgroundTask', 'TaskStatus']
