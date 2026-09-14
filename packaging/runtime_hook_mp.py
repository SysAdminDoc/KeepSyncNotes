"""Protect frozen Windows workers before the application import graph loads."""

import multiprocessing

multiprocessing.freeze_support()
