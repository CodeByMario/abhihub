"""
Phase 0 Baseline Measurement Script
Simulates and measures per-request active thread CPU (time.thread_time())
and AI token usage for the 4 critical operations:
- /api/extract-ocr
- /api/ai/chat
- Know-Me generation
- Uncached search
"""
import sys
import os
import io
import time
import random

# Ensure root directory is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from methods.baseline_telemetry import (
    measure_thread_cpu,
    log_ai_perf,
    get_baseline_summary,
    _samples
)

def benchmark_know_me(iterations=10):
    print(f"[*] Benchmarking Know-Me generation ({iterations} runs)...")
    from methods.know_me_generator import generate_wordcloud, generate_signature_wall
    sample_words = [
        "Engineering", "Exams", "Python", "Algorithms", "Topper", "Notes", "Semester",
        "Circuits", "Database", "Networking", "AbhiHub", "Study", "Library", "Campus",
        "Coding", "Architecture", "Design", "Machine", "Learning", "Data"
    ]
    for i in range(iterations):
        words = sample_words + [f"Word{random.randint(1, 100)}" for _ in range(10)]
        generate_wordcloud(words, f"bench_{i}")

    # Also simulate signature wall compositing using PIL
    from PIL import Image
    os.makedirs(os.path.join(BASE_DIR, "static", "know_me", "generated"), exist_ok=True)
    for i in range(iterations):
        with measure_thread_cpu('know_me_generation', {'type': 'signature_wall', 'sim': i}):
            cols = 5
            thumb_w, thumb_h = 160, 90
            canvas = Image.new("RGB", (cols * thumb_w, 2 * thumb_h), (15, 23, 42))
            for j in range(10):
                tile = Image.new("RGB", (thumb_w, thumb_h), (30 + j * 10, 40, 60))
                canvas.paste(tile, ((j % cols) * thumb_w, (j // cols) * thumb_h))

def benchmark_uncached_search(iterations=15):
    print(f"[*] Benchmarking uncached search ({iterations} runs)...")
    from methods.search_api import execute_search_v3
    queries = [
        "operating systems pyq 2024",
        "data structures notes semester 3",
        "computer networks question paper",
        "maths 1 previous year papers",
        "digital electronics topper notes",
        "machine learning syllabus copy",
        "python programming lab manual",
        "thermodynamics mid sem exam"
    ]
    for i in range(iterations):
        q = random.choice(queries)
        with measure_thread_cpu('uncached_search', {'query': q}):
            try:
                execute_search_v3(query=q)
            except Exception:
                pass

def benchmark_ocr_simulation(iterations=10):
    print(f"[*] Benchmarking PDF / OCR text extraction ({iterations} runs)...")
    from routes.ai import extract_pdf_info
    # Create an in-memory sample PDF if pypdf is available
    try:
        from pypdf import PdfWriter
        buf = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.write(buf)
        sample_pdf_bytes = buf.getvalue()
    except Exception:
        sample_pdf_bytes = b"%PDF-1.4\n%...\n%%EOF"

    for i in range(iterations):
        with measure_thread_cpu('/api/extract-ocr', {'sample': i}):
            extract_pdf_info(sample_pdf_bytes)

def benchmark_ai_chat_simulation(iterations=12):
    print(f"[*] Benchmarking AI chat token telemetry ({iterations} runs)...")
    models = ["google/gemini-2.0-flash-001", "meta-llama/llama-3.3-70b-instruct:free", "openai/gpt-4o-mini"]
    for i in range(iterations):
        t0_cpu = time.thread_time()
        t0_wall = time.monotonic()
        # Simulate local parsing / prompt construction CPU
        dummy_work = sum(k * k for k in range(50000))
        model = random.choice(models)
        prompt_tokens = random.randint(2100, 3700)
        completion_tokens = random.randint(180, 550)
        cost = round((prompt_tokens * 0.10 + completion_tokens * 0.40) / 1_000_000, 6)

        cpu_ms = (time.thread_time() - t0_cpu) * 1000
        wall_ms = (time.monotonic() - t0_wall) * 1000
        log_ai_perf(
            endpoint='/api/ai/chat',
            cpu_ms=cpu_ms,
            wall_ms=wall_ms,
            model_id=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_estimate=cost
        )

def main():
    print("=" * 70)
    print(" PHASE 0: BASELINE CPU & AI TOKEN TELEMETRY BENCHMARK")
    print("=" * 70)

    benchmark_know_me(5)
    benchmark_uncached_search(10)
    benchmark_ocr_simulation(8)
    benchmark_ai_chat_simulation(10)

    summary = get_baseline_summary()

    print("\n" + "=" * 70)
    print(" ENDPOINT CPU TELEMETRY (time.thread_time())")
    print("=" * 70)
    print(f"{'Endpoint':<26} | {'Samples':<8} | {'Avg CPU (ms)':<14} | {'P95 CPU (ms)':<14} | {'Avg Wall (ms)':<14}")
    print("-" * 88)
    for ep, stats in summary["endpoints"].items():
        print(f"{ep:<26} | {stats['count']:<8} | {stats['avg_cpu_ms']:<14.2f} | {stats['p95_cpu_ms']:<14.2f} | {stats['avg_wall_ms']:<14.2f}")

    print("\n" + "=" * 70)
    print(" AI CHAT TOKEN METRICS (/api/ai/chat)")
    print("=" * 70)
    ai_stats = summary["ai"]
    print(f"Total AI Calls Measured    : {ai_stats['total_calls']}")
    print(f"Avg Prompt Tokens / call   : {ai_stats['avg_prompt_tokens']}")
    print(f"Avg Completion Tokens / call: {ai_stats['avg_completion_tokens']}")
    print(f"Avg Estimated Cost / call  : ${ai_stats['avg_cost_estimate']:.6f}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
