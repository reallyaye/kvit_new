"""
Модуль тестирования и диагностики почтового шлюза и доставки email (ТОО «КРЭК»).
"""
"""
Модуль тестирования и диагностики почтового шлюза и доставки email (ТОО «КРЭК»).
"""

def __getattr__(name):
    if name in ('check_smtp_connection', 'check_domain_dns', 'send_test_email', 'run_diagnostics'):
        from . import test_delivery
        return getattr(test_delivery, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    'check_smtp_connection',
    'check_domain_dns',
    'send_test_email',
    'run_diagnostics',
]
