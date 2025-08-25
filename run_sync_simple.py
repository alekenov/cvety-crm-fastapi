#!/usr/bin/env python3
"""Автоматический запуск упрощенной синхронизации"""
import sync_shops_simple

# Переопределяем input
original_input = input
__builtins__.input = lambda prompt: (print(prompt + "yes"), "yes")[1]

try:
    sync_shops_simple.main()
finally:
    __builtins__.input = original_input