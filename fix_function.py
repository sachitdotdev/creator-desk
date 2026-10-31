# Python script to fix the VideoRow function signature
with open("frontend/src/pages/UploadStudio.tsx", "r") as file:
    content = file.read()

# Find the VideoRow function signature and fix it
lines = content.split("\n")
for i, line in enumerate(lines):
    if "export function VideoRow(" in line:
        # Replace the entire function signature with the correct one
        lines[i] = "export function VideoRow({
"
        # Add the parameters on the next lines
        lines.insert(i+1, "  value: number | null;")
        lines.insert(i+2, "  onValueChange: (v: number | null) => void;")
        lines.insert(i+3, "  templates: any[];")
        lines.insert(i+4, "  loading: boolean;")
        # Close the parameters and function
        lines[i+5] = "}) {"
        break

# Write the corrected content back to the file
corrected_content = "\n".join(lines)
with open("frontend/src/pages/UploadStudio.tsx", "w") as file:
    file.write(corrected_content)

print("Fixed the VideoRow function signature in UploadStudio.tsx")