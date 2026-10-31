import re

# Read the file
with open('frontend/src/pages/UploadStudio.tsx', 'r') as file:
    content = file.read()

# Fix orphaned comma on line 96
content = re.sub(r'\s*,\s*\n\s+\{', ' {', content)

# Fix malformed fetch call - move it inside the try block and fix indentation
content = content.replace(
    r'\s*}\s*,\s*\n\s+\s+body: JSON.stringify({',
    '    } catch (error) {\n      console.error(\'Pipeline error:\', error);\n      setIsProcessing(false);\n    }\n    try {\n      // Start processing\n      await fetch(`http://127.0.0.1:8000/api/videos/${videoId}/process`, {\n        method: \'POST\',\n        body: JSON.stringify({\n          fileId: videos.find(v => v.filename === selectedFile.name)?.id,\n          clips: 5,\n          template: templates[0]?.id || null,\n        }),\n      });\n    } catch (error) {\n      console.error(\'Pipeline error:\', error);\n      setIsProcessing(false);\n    }\n    }\s+,
    ')

# Write the fixed content back to the file
with open('frontend/src/pages/UploadStudio.tsx', 'w') as file:
    file.write(content)

print("Frontend syntax error fixed.")