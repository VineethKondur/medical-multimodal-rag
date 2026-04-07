#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import warnings

# 🔥 SUPPRESS ALL DEPRECATION WARNINGS AND ARC4 WARNINGS
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message="ARC4 has been moved")
warnings.filterwarnings("ignore", module="cryptography")
warnings.filterwarnings("ignore", module="pypdf")

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
