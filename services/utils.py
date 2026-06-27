# -*- coding: utf-8 -*-

# """

PROJECT : AI AGENT V1 - CÔNG AN PHƯỜNG PHÙ LIỄN
FILE    : services/utils.py
VERSION : 1.0.0 Production
AUTHOR  : OpenAI

## Chức năng

* Chuẩn hóa chuỗi
* Kiểm tra dữ liệu
* UUID
* Thời gian
* JSON
  =========================================================
  """

import json
import uuid
import re
from datetime import datetime
from typing import Any

# =========================================================

# NORMALIZE TEXT

# =========================================================

def normalize_text(text: Any) -> str:

```
if text is None:
    return ""

text = str(text).strip()

text = re.sub(r"\s+", " ", text)

return text
```

# =========================================================

# IS EMPTY

# =========================================================

def is_empty(value: Any) -> bool:

```
return normalize_text(value) == ""
```

# =========================================================

# UUID

# =========================================================

def generate_uuid() -> str:

```
return str(uuid.uuid4())
```

# =========================================================

# DATETIME

# =========================================================

def now() -> datetime:

```
return datetime.now()
```

def now_string() -> str:

```
return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

# =========================================================

# JSON

# =========================================================

def json_load(text: str) -> dict:

```
if is_empty(text):
    return {}

return json.loads(text)
```

def json_dump(data: dict) -> str:

```
return json.dumps(

    data,

    ensure_ascii=False,

    indent=2

)
```

# =========================================================

# SAFE GET

# =========================================================

def safe_get(data: dict, key: str, default=None):

```
if not isinstance(data, dict):
    return default

return data.get(key, default)
```

# =========================================================

# BOOLEAN

# =========================================================

def to_bool(value: Any) -> bool:

```
return str(value).lower() in (

    "true",

    "1",

    "yes",

    "y"

)
```

# =========================================================

# END OF FILE

# =========================================================

