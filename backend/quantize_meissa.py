from transformers import AutoModelForCausalLM, AutoTokenizer
from llmcompressor import oneshot
from llmcompressor.modifiers.awq import AWQModifier
from datasets import load_dataset
import torch

# --- Configuration ---
model_id = "Orion-zhen/Meissa-Qwen2.5-7B-Instruct"
output_dir = "C:/Sachit/models/meissa-7b-awq"

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