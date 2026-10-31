import re

file_path = "frontend/src/pages/UploadStudio.tsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# The pattern matches the onClick block which is hard to match exactly with edit tool's whitespace rules.
# We look for the Button's onClick property that contains the manual mutation call.
pattern = r"onClick={() => {\s+if\(\!\s*selectedVideoId\)\s+return\s+toast\.error\(\"Please\s+select\s+a\s+video\s+first\"\);\s+processMut\.mutate\(\{\s+id:\s+selectedVideoId,\s+body:\s+\{\s+video_id:\s+selectedVideoId,\s+\...\(selectedTemplate\s+\?\s+\{.*?\}\s+\:\s+\{}\)\s*,\s+numClips:\s+numClips,\s+vibe,\s+\}\s+\},\);\s+}}"

# A simpler approach might be searching for the specific mutate body.
# Let's try to replace the specific chunk.
# Actually, the easiest way to do this via bash/python is to replace the multi-line block.

# Let's find the exact lines to replace.
# Based on previous reads, it's a block of 12 lines (approx)
# I'll use a more robust regex.
old_block = """            onClick={() => {
              if (!selectedVideoId) return toast.error("Please select a video first");
              processMut.mutate({
                id: selectedVideoId,
                body: {
                  video_id: selectedVideoId,
                  ...(selectedTemplate ? { template_id: selectedTemplate } : {}),
                  numClips: numClips,
                  vibe,
                },
              });
            }}"""

# Since whitespaces are tricky, I'll use a script that finds the Button and replaces the onClick logic.
# Or even better, just use a direct string replacement for the whole button if needed, 
# but it's better to just replace the content of the onClick.

# Let's try a different approach: read the file, do the substitution in Python, and write it back.
# Because the file is large, I'll read it in chunks or just the whole thing if it fits.

# Actually, I'll just try a very targeted sed command or shell command first.
# But I'll start with a python script to be safe.
