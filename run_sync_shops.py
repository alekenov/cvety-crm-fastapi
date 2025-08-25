#!/usr/bin/env python3
"""
Автоматический запуск синхронизации магазинов
"""

import sync_shops_via_ssh
import sys

# Переопределяем input чтобы автоматически подтвердить
original_input = input
def auto_yes_input(prompt):
    print(prompt + "yes")
    return "yes"

# Заменяем функцию input
__builtins__.input = auto_yes_input

# Запускаем синхронизацию
try:
    sync_shops_via_ssh.main()
except Exception as e:
    print(f"Ошибка: {e}")
finally:
    # Восстанавливаем оригинальную функцию
    __builtins__.input = original_input