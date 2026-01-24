# Summary: Why Fields Were Changed from 'by postinit' to Default Values

## Problem with 'by postinit'
Fields marked `by postinit` don't exist until explicitly created in the postinit method.
Accessing them before assignment causes `AttributeError`.

## Categories of Changes

### Category 1: Fields Checked Before Assignment (MUST change)
**Problem:** postinit tries to check field value before creating it
**Solution:** Use `= None` so field exists immediately

Files:
- memory_hierarchy.jac: MongoBackend (client, db, collection), RedisBackend (redis_client)
- llm.jac: Model (proxy, http_client, _mock_delegate)
- types.jac (byllm): Image (mime_type)
- client_bundle.jac: ClientBundleBuilder (runtime_path)
- type_utils.jac: ParamAssignmentTracker (varargs, kwargs)

Example:
```jac
// BEFORE (broken):
has client: MongoClient | None by postinit;
impl postinit {
    if self.client is None {  // ❌ AttributeError!
        self.client = MongoClient(...);
    }
}

// AFTER (fixed):
has client: MongoClient | None = None;
impl postinit {
    if self.client is None {  // ✅ Works!
        self.client = MongoClient(...);
    }
}
```

### Category 2: Fields Passed to Constructor (MUST change)
**Problem:** Code tries to pass field value to constructor, but `by postinit` excludes it
**Solution:** Use `= None` or `= ""` to make field optional constructor parameter

Files:
- types.jac (byllm): Tool (description, params_desc)
- types.jac (type_system): ClassType (private), UnionType (types), OverloadedType (overloads)
- corelib_fmt.jac: Root, GenericEdge, Master (__jac__)

**Example 1: Tool fields**
```jac
// BEFORE (broken):
has description: str by postinit;
// Constructor call:
Tool(func=my_func, description="test")  // ❌ TypeError: unexpected keyword argument 'description'

// AFTER (fixed):
has description: str = "";
// Constructor call:
Tool(func=my_func, description="test")  // ✅ Works!
```

**Example 2: __jac__ fields in corelib_fmt.jac**
```jac
// BEFORE (broken):
obj Master {
    has __jac__: Anchor | None by postinit;  // ❌ Excluded from constructor
}
// Usage (lines 198, 457):
Master(__jac__=some_value)  // ❌ Error: unexpected keyword argument '__jac__'

// AFTER (fixed):
obj Master {
    has __jac__: Anchor | None = None;  // ✅ Optional constructor parameter
}
// Usage:
Master(__jac__=some_value)  // ✅ Works!
```

### Category 3: Fields with Required Default Values (Already had defaults)
**Not changed:** These always had defaults, never used `by postinit`

Files:
- types.jac (type_system): ClassDetailsShared (mro = [])

Reason: Production code doesn't pass `mro` to constructor, so default is required.

## Future Enhancement: Support `by postinit = value` Syntax

### Current Limitation
The Jac grammar currently treats `by postinit` and `= value` as mutually exclusive (OR, not AND):
```lark
typed_has_clause: named_ref type_tag (EQ expression | KW_BY KW_POST_INIT)?
```

This means you can have:
- ✅ `name: type = value` (constructor parameter with default)
- ✅ `name: type by postinit` (excluded from constructor)
- ❌ `name: type by postinit = value` (NOT supported - syntax error)

### Proposed Enhancement
**Support `by postinit = value` to combine both behaviors:**

```jac
obj PluginConfigBase {
    has project_dir: Path | None = None,        // Constructor parameter
        config_file: Path | None by postinit = None,    // Computed, with default
        _config: dict[str, Any] by postinit = None,     // Computed, with default
        _jac_config: JacConfig | None by postinit = None;  // Computed, with default

    def postinit -> None {
        if self.project_dir {
            self.config_file = self.project_dir / "jac.toml";  // Override default
            // ... load config
        }
    }
}
```

### Benefits (Comparison with Python Dataclasses)

Python's `dataclasses` supports this pattern:
```python
from dataclasses import dataclass, field

@dataclass
class Example:
    # Field not in __init__, but has default value
    computed: str = field(init=False, default="default_value")
    
    def __post_init__(self):
        # Can override or use the default
        if some_condition:
            self.computed = "new_value"
```

**Why this is better:**
1. **Field exists immediately** (no AttributeError)
2. **Excluded from constructor** (clean API)
3. **Has default value** (safe to access before postinit completes)
4. **Can be overridden in postinit** (flexible)

### Current Workaround
Until `by postinit = value` is supported, use `= value` for all fields that need defaults:

```jac
obj MyClass {
    has computed_field: str | None = None;  // Use this instead of 'by postinit'
    
    def postinit -> None {
        if not self.computed_field {  // Safe to check
            self.computed_field = compute();
        }
    }
}
```

## Recommendations for Current Jac Code

### When to use `by postinit`:
1. Field is ONLY assigned in postinit (never checked before assignment)
2. Field should NOT be passable to constructor
3. You're certain no code will access it before postinit assigns it

### When to use `= None` or `= value`:
1. Field needs to be checked in postinit (e.g., `if self.field is None`)
2. Field should be passable to constructor (optional parameter)
3. Field has a computed default that might be overridden
4. **When in doubt** - safer choice!

### Recommended Pattern:
```jac
obj MyClass {
    has required_param: str,                    // Required constructor param
        optional_param: str = "default",        // Optional with default
        computed_field: str | None = None;      // Computed in postinit

    def postinit -> None {
        if not self.computed_field {            // Safe to check
            self.computed_field = compute();    // Compute if not provided
        }
    }
}
```

## Final Recommendation
**Prefer `= None` over `by postinit`** unless you have a specific reason to exclude the field from the constructor entirely. Once `by postinit = value` is supported, you can use that for computed fields with defaults.
