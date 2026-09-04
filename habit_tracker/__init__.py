"""habit-tracker: a small command-line habit tracker.

The package is deliberately thin:

* :mod:`habit_tracker.cli` parses arguments and dispatches to command handlers.
* :mod:`habit_tracker.render` turns habit data into the lines the CLI prints.
* :mod:`habit_tracker.storage` owns everything that touches the JSON data file.

Nothing else should read or write the data file directly.
"""

__version__ = "0.3.0"

__all__ = ["__version__"]
