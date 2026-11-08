"""
Real-Time Infrastructure Cost Metering Engine (AbhiHub Universal Points System)
Computes real-time unit costs for:
1. File Storage & CDN Egress Bandwidth
2. AI Chatbot Compute & LLM Tokens
3. Deep Semantic Search Vector Operations

Applies a mandatory 35% Safety Margin Buffer (SAFETY_BUFFER = 1.35)
to protect platform solvency against cloud provider rate spikes, egress surges,
and connection retries.
"""

import math
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Safety buffer multiplier (+35% margin)
SAFETY_BUFFER = 1.35

# Platform valuation: 1 Credit = ₹0.20 (~$0.0023 USD)
CREDIT_VALUATION_INR = 0.20

# Cloud cost rates (approximate R2 + CDN egress + Database compute)
# Cloudflare R2 / AWS S3 egress: ~$0.09 / GB = ~₹7.83 / GB => ~₹0.0076 / MB
EGRESS_COST_PER_MB_INR = 0.008

# Storage amortized cost per MB/month: ~₹0.0015
STORAGE_COST_PER_MB_INR = 0.002

# LLM Token inference cost (e.g. Gemini 1.5 Flash / OpenRouter):
# ~$0.000375 / 1k tokens = ~₹0.033 / 1k tokens
LLM_COST_PER_1K_TOKENS_INR = 0.035


class InfraCostEngine:
    def __init__(self, safety_buffer: float = SAFETY_BUFFER):
        self.safety_buffer = safety_buffer

    def calculate_file_credits(self, file_size_bytes: int = 0) -> Dict[str, Any]:
        """
        Calculate credits required to view/download a file based on:
        - Actual file size (MB)
        - Storage + Egress bandwidth cost
        - 35% safety buffer
        Minimum floor: 1 credit.
        """
        try:
            bytes_val = float(file_size_bytes or 0)
        except (ValueError, TypeError):
            bytes_val = 0.0

        # Default minimum 1.5 MB if size not yet indexed
        if bytes_val <= 0:
            bytes_val = 1.5 * 1024 * 1024

        size_mb = bytes_val / (1024 * 1024)
        
        # Raw infrastructure cost (egress + hosting slice)
        raw_infra_cost_inr = (size_mb * EGRESS_COST_PER_MB_INR) + (size_mb * STORAGE_COST_PER_MB_INR)
        
        # Base platform servicing cost (API lookup, DB read, auth token verify)
        base_service_cost_inr = 0.08

        total_raw_cost = raw_infra_cost_inr + base_service_cost_inr
        buffered_cost_inr = total_raw_cost * self.safety_buffer

        # Map to credits (minimum floor 1 credit)
        credits_charged = max(1, math.ceil(buffered_cost_inr / CREDIT_VALUATION_INR))

        # Scaled tiers for large files (e.g. 20MB scanned handbooks)
        if size_mb > 25:
            credits_charged = max(credits_charged, 3)
        elif size_mb > 10:
            credits_charged = max(credits_charged, 2)

        return {
            'credits': credits_charged,
            'file_size_mb': round(size_mb, 1),
            'raw_cost_inr': round(total_raw_cost, 4),
            'buffered_cost_inr': round(buffered_cost_inr, 4),
            'safety_buffer_pct': int((self.safety_buffer - 1.0) * 100),
            'label': f"{round(size_mb, 1)} MB • {credits_charged} Credit{'s' if credits_charged > 1 else ''}",
            'breakdown_text': f"{round(size_mb, 1)} MB egress + 35% safety buffer"
        }

    def calculate_ai_credits(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> Dict[str, Any]:
        """
        Calculate credits required for AI Chatbot response based on token length:
        Applies 35% safety buffer for LLM inference compute.
        """
        total_tokens = max(100, int(prompt_tokens or 0) + int(completion_tokens or 0))
        raw_token_cost_inr = (total_tokens / 1000.0) * LLM_COST_PER_1K_TOKENS_INR
        base_ai_overhead = 0.06

        buffered_cost_inr = (raw_token_cost_inr + base_ai_overhead) * self.safety_buffer
        credits_charged = max(1, math.ceil(buffered_cost_inr / CREDIT_VALUATION_INR))

        return {
            'credits': credits_charged,
            'total_tokens': total_tokens,
            'raw_cost_inr': round(raw_token_cost_inr, 4),
            'buffered_cost_inr': round(buffered_cost_inr, 4),
            'safety_buffer_pct': int((self.safety_buffer - 1.0) * 100),
            'breakdown_text': f"{total_tokens} tokens compute + 35% safety buffer"
        }

    def calculate_search_credits(self, is_semantic: bool = False) -> Dict[str, Any]:
        """
        Search costing:
        - Indexed keyword search: 0 Credits (Free)
        - Deep semantic vector AI search: 1 Credit
        """
        if not is_semantic:
            return {
                'credits': 0,
                'is_free': True,
                'label': 'Free (Cached)',
                'safety_buffer_pct': 35
            }
        return {
            'credits': 1,
            'is_free': False,
            'label': '1 Credit (AI Vector Search)',
            'safety_buffer_pct': 35,
            'breakdown_text': 'Vector embeddings compute + 35% safety buffer'
        }


# Global singleton instance
cost_engine = InfraCostEngine()
