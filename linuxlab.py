#!/usr/bin/env python3
"""Public LinuxLab entry point; preserve the legacy engine and error handling."""
import runpy


if __name__ == '__main__':
    runpy.run_module('orbit', run_name='__main__')
