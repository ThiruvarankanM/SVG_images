# Python to Jac Go-to-Definition: Implementation Summary

## TL;DR - The Good News! 🎉

**The line number mapping is NOT a problem!** When you convert Python to Jac AST using `PyastBuildPass`, the AST **preserves the original Python file's line numbers**. This means we can accurately map cursor positions from Python files to the AST.

## What I Discovered

### 1. **Existing Infrastructure is Excellent**

You already have everything you need:

✅ **Python AST to Jac AST Conversion** (`PyastBuildPass`)
- Converts Python code to Jac AST
- **Preserves original Python line numbers** in the AST
- Used by `jac tool ir ast` and `jac py2jac` commands

✅ **Module Resolution** (`modresolver.py`)
- Resolves module names to file paths
- Supports both Jac and Python files
- Uses Python's importlib as fallback

✅ **Symbol Lookup** (Jac AST Symbol Tables)
- Every Jac module has a symbol table
- Can search for symbols by name
- Already used for go-to-definition in Jac files

✅ **Language Server** (`JacLangServer`)
- Already implements go-to-definition for Jac files
- Just needs to be extended to handle Python files

### 2. **The Line Number "Issue" is Actually Not an Issue**

When you run:
```bash
jac tool ir ast test.py
```

The output shows:
```
2:1 - 2:46      +-- Import,
2:13 - 2:21     |   +-- ModulePath - mymodule
2:24 - 2:31     |   +-- ModuleItem - MyClass
```

These line numbers (2:1, 2:13, etc.) refer to the **original Python file**, not the generated Jac code!

**Proof**: I tested this with the uploaded image and confirmed that:
- Python line 2: `from mymodule import MyClass, my_function`
- AST shows: Line 2, columns 13-21 for "mymodule"
- AST shows: Line 2, columns 24-31 for "MyClass"

This is **exactly what we need** for go-to-definition!

### 3. **Why the Current VSCode Approach Fails**

The current `jacDefinitionProvider.ts`:
- Uses simple file system search (looking for .jac files)
- Doesn't parse Python AST
- Doesn't use Jac's module resolution
- Can't accurately find symbols

## Recommended Solution

### **Extend the Jac Language Server** (Best Approach)

Add Python file support to the existing `JacLangServer.get_definition()` method.

#### Flow:

```
Python File (app.py)
    ↓
User clicks on "MyClass" in import statement
    ↓
VSCode sends: textDocument/definition request
    ↓
Jac Language Server receives request
    ↓
Detects .py file → calls get_definition_from_python()
    ↓
1. Parse Python file using ast.parse()
2. Convert to Jac AST using PyastBuildPass (preserves line numbers!)
3. Find AST node at cursor position
4. Extract import info (module name, symbol name)
5. Resolve module path using modresolver.resolve_module()
6. Load target Jac file's AST
7. Find symbol in Jac file's symbol table
8. Return location
    ↓
VSCode jumps to definition in Jac file
```

## Implementation Steps

### Phase 1: MVP (Import Statements Only)

**Goal**: Support `from module import Symbol` only

**Files to Modify**:

1. **`jaseci/jac/jaclang/langserve/engine.jac`**
   - Add method signature: `get_definition_from_python()`

2. **`jaseci/jac/jaclang/langserve/impl/engine.impl.jac`**
   - Implement `get_definition_from_python()`
   - Add helper methods:
     - `find_node_at_position_in_ast()`
     - `extract_import_info()`
     - `find_symbol_in_jac_file()`

3. **`jac-vscode/src/extension.ts`** (optional)
   - Ensure Python files are registered with the language client
   - May need to add `.py` to document selector

**Estimated Effort**: 2-3 days

### Phase 2: Enhanced Support

**Goal**: Support more import styles and features

- `import module`
- `import module as alias`
- Hover support (show type info from Jac files)
- Completion support (suggest symbols from Jac modules)

**Estimated Effort**: 3-5 days

### Phase 3: Full Integration

**Goal**: Complete Python-Jac interop

- Go-to-definition for all Python symbols (not just imports)
- Find references (find usages of Jac symbols in Python)
- Rename refactoring across Python and Jac files

**Estimated Effort**: 1-2 weeks

## Key Code Locations

### Files You Need to Understand:

1. **`jaseci/jac/jaclang/compiler/passes/main/pyast_load_pass.jac`**
   - Python AST to Jac AST conversion
   - Study how it preserves location info

2. **`jaseci/jac/jaclang/pycore/modresolver.py`**
   - Module resolution logic
   - Function: `resolve_module(target, base_path)`

3. **`jaseci/jac/jaclang/langserve/impl/engine.impl.jac`**
   - Existing go-to-definition implementation
   - Method: `get_definition()` (lines 88-150)

4. **`jaseci/jac/jaclang/utils/impl/lang_tools.impl.jac`**
   - CLI tool implementation
   - Shows how to use `PyastBuildPass`

### Example Usage:

```jac
// How to convert Python to Jac AST
import ast as py_ast;
import from jaclang.compiler.passes.main { PyastBuildPass }

file_source = read_file_with_encoding("app.py");
py_ast_tree = py_ast.parse(file_source);

jac_ast = PyastBuildPass(
    ir_in=uni.PythonModuleAst(
        py_ast_tree, 
        orig_src=uni.Source(file_source, "app.py")
    ),
    prog=JacProgram()
).ir_out;

// Now jac_ast contains the Jac AST with original Python line numbers!
```

## Testing Strategy

### Test Cases:

1. **Basic Imports**:
   ```python
   from mymodule import MyClass  # Click on MyClass
   from mymodule import my_function  # Click on my_function
   ```

2. **Multiple Imports**:
   ```python
   from mymodule import MyClass, my_function  # Click on each
   ```

3. **Nested Modules**:
   ```python
   from package.submodule import Symbol  # Click on Symbol
   ```

4. **Edge Cases**:
   - Module not found
   - Symbol not found in module
   - Circular imports
   - Invalid Python syntax

### How to Test:

1. Create test Python files in `jaseci/jac/tests/langserve/fixtures/`
2. Create corresponding Jac files
3. Write unit tests in `jaseci/jac/tests/langserve/test_python_goto_def.py`
4. Test manually in VSCode

## Common Pitfalls to Avoid

❌ **Don't try to map generated Jac code line numbers**
- The AST already has the original Python line numbers!

❌ **Don't implement custom Python parsing**
- Use Python's built-in `ast.parse()`

❌ **Don't reinvent module resolution**
- Use existing `modresolver.resolve_module()`

❌ **Don't search files manually**
- Use Jac's symbol tables

## Questions & Answers

**Q: Do we need to handle .pyi stub files?**
A: Not for MVP. The module resolver already handles .pyi files, so it should work automatically.

**Q: What about Python-to-Python go-to-definition?**
A: Not needed for MVP. Focus on Python-to-Jac only.

**Q: Should we cache parsed ASTs?**
A: Not initially. The language server already has caching for compiled modules. We can add Python AST caching later if needed.

**Q: How do we handle dynamic imports?**
A: Not supported in MVP. Only static imports.

## Next Steps (Actionable)

### Step 1: Verify Understanding (1 hour)
- [ ] Read `pyast_load_pass.jac` to understand AST conversion
- [ ] Test `jac tool ir ast` on various Python files
- [ ] Confirm line numbers are preserved

### Step 2: Design (2 hours)
- [ ] Review the pseudocode in `IMPLEMENTATION_PSEUDOCODE.jac`
- [ ] Identify exact methods to add/modify
- [ ] Plan testing strategy

### Step 3: Implement MVP (2-3 days)
- [ ] Add `get_definition_from_python()` to language server
- [ ] Implement helper methods
- [ ] Write unit tests
- [ ] Test in VSCode

### Step 4: Iterate (ongoing)
- [ ] Get user feedback
- [ ] Add more import styles
- [ ] Add hover and completion support

## Resources

- **Analysis Document**: `PYTHON_TO_JAC_GOTO_DEF_ANALYSIS.md`
- **Pseudocode**: `IMPLEMENTATION_PSEUDOCODE.jac`
- **Architecture Diagram**: `python_jac_goto_architecture.png`
- **Test Files**: `test_py_ast.py`, `test_imports.py`

## Conclusion

You have all the pieces you need! The key insight is:

> **The Jac AST preserves original Python line numbers, so cursor position mapping is straightforward.**

The implementation is mostly about **wiring together existing components**:
1. Parse Python → Jac AST (✅ already exists)
2. Find node at cursor (✅ already exists for Jac)
3. Resolve module (✅ already exists)
4. Find symbol (✅ already exists)

Just need to connect them for Python files!

Good luck! 🚀
