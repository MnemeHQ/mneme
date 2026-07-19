"""Allow `python -m mneme` invocation."""
import sys
from mneme.cli import main

sys.exit(main())
