import re

# Read the file
with open('frontend/src/pages/UploadStudio.tsx', 'r', encoding='utf-8') as file:
    content = file.read()

# Define the regex pattern to match the entire onClick handler
pattern = r'onClick={async \(.*?\) =\s*\{([\s\S]*?)\s*\}', re.DOTALL

# Define the replacement content
replacement = '''onClick={async () => {
  if (videos.length > 0) {
    const videoId = videos[0].id;
    setIsProcessing(true);
    
    try {
      // Start processing
      await fetch(`http://127.0.0.1:8000/api/videos/${videoId}/process`, {
        method: 'POST',
      });
      
      // Poll for status updates
      const intervalId = setInterval(async () => {
        const response = await fetch('http://127.0.0.1:8000/api/videos');
        const data = await response.json();
        const video = data.find(v => v.id === videoId);
        
        if (video && (video.status === 'done' || video.status === 'error')) {
          clearInterval(intervalId);
          setIsProcessing(false);
          window.location.reload();
        }
      }, 3000);
      
    } catch (error) {
      console.error('Pipeline error:', error);
      setIsProcessing(false);
    }
  }
}}
'''

# Compile the pattern
compiled_pattern = re.compile(pattern, re.DOTALL)

# Replace the onClick handler
new_content = compiled_pattern.sub(replacement, content)

# Write the new content back to the file
with open('frontend/src/pages/UploadStudio.tsx', 'w', encoding='utf-8') as file:
    file.write(new_content)

print("onClick handler replaced successfully.")