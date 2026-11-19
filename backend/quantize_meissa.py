import os
from pathlib import Path

from datasets import load_dataset
from llmcompressor import oneshot
from llmcompressor.modifiers.awq import AWQModifier
from transformers import AutoModelForCausalLM, AutoTokenizer

# --- Configuration ---
# Override with MEISSA_MODEL_ID / MEISSA_OUTPUT_DIR, or edit the defaults below.
# All defaults are public model IDs or repo-relative paths: never a personal
# absolute path.
model_id = os.environ.get("MEISSA_MODEL_ID", "Orion-zhen/Meissa-Qwen2.5-7B-Instruct")
output_dir = os.environ.get("MEISSA_OUTPUT_DIR") or str(
    Path(__file__).resolve().parent / "assets" / "models" / "meissa-7b-awq"
)

# --- 1. Load Model and Tokenizer ---
print(f"Loading model: {model_id}")
model = AutoModelForCausalLM.from_pretrained(
    model_id, torch_dtype="auto", device_map="auto", trust_remote_code=True
)
tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)

# --- 2. Prepare Calibration Dataset ---
# Using the standard neuralmagic calibration dataset
print("Loading calibration dataset...")
ds = load_dataset("neuralmagic/calibration", name="LLM", split="train[:256]")

# --- 3. Configure AWQ Quantization ---
# W4A16: 4-bit weights, 16-bit activations. Ignoring lm_head is standard practice.
recipe = AWQModifier(
    ignore=["lm_head"],
    scheme="W4A16",
    targets=["Linear"],
)

# --- 4. Apply Quantization ---
print("Starting quantization... This may take 10-15 minutes.")
oneshot(
    model=model,
    dataset=ds,
    recipe=recipe,
    max_seq_length=2048,
    num_calibration_samples=256,
    output_dir=output_dir,
)

print(f"✅ Quantized model saved to: {output_dir}")