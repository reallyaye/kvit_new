"""Пакет управления фоновыми задачами и асинхронной обработки документов."""
from .task_manager import BackgroundTask, TaskStatus, task_manager

__all__ = ['task_manager', 'BackgroundTask', 'TaskStatus']
