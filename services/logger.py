# -*- coding: utf-8 -*-

# """

PROJECT : AI AGENT V1 - CÔNG AN PHƯỜNG PHÙ LIỄN
FILE    : services/logger.py
VERSION : 1.1.0 Production
AUTHOR  : OpenAI

## Chức năng

* Ghi log hệ thống
* Console Logger
* Định dạng thống nhất
  =========================================================
  """

import logging
import sys

from services.config import (
LOG_LEVEL,
LOG_FORMAT
)

# =========================================================

# LOGGER

# =========================================================

logger = logging.getLogger("AI_AGENT_V1")

if not logger.handlers:

```
logger.setLevel(LOG_LEVEL)

formatter = logging.Formatter(LOG_FORMAT)

console = logging.StreamHandler(sys.stdout)

console.setFormatter(formatter)

logger.addHandler(console)

logger.propagate = False
```

# =========================================================

# INFO

# =========================================================

def log_info(message: str) -> None:

```
logger.info(message)
```

# =========================================================

# WARNING

# =========================================================

def log_warning(message: str) -> None:

```
logger.warning(message)
```

# =========================================================

# ERROR

# =========================================================

def log_error(message: str) -> None:

```
logger.error(message)
```

# =========================================================

# DEBUG

# =========================================================

def log_debug(message: str) -> None:

```
logger.debug(message)
```

# =========================================================

# EXCEPTION

# =========================================================

def log_exception(err: Exception) -> None:

```
logger.exception(err)
```

# =========================================================

# STARTUP

# =========================================================

log_info("Logger initialized successfully.")
