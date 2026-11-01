#!/bin/bash
cd "${OPENHANDS_PROJECT_DIR:-$PWD}"

# 1. Check Python compilation
echo "Checking Python compilation..."
if ! find backend/app -name "*.py" -exec python -m py_compile {} +; then
  echo '{"decision":"deny","reason":"Python compilation failed. Fix the syntax errors."}'
  exit 2
fi

# 2. Check TypeScript compilation
echo "Checking TypeScript..."
cd frontend
if ! npx tsc --noEmit; then
  echo '{"decision":"deny","reason":"TypeScript compilation failed. Fix the React/TypeScript errors."}'
  exit 2
fi

exit 0
