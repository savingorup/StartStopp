#!/usr/bin/env python
import os
import sys

# add current dir to pythonpath!
sys.path.append(os.path.dirname(__file__))

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webapp.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
