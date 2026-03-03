import re
from typing import Dict, Any, Optional
from enum import Enum

class Decision(str, Enum):
    CPU = "cpu"
    GPU = "gpu"

class DecisionEngine:
    def __init__(self):
        # Heuristic rules - will be enhanced with ML in v2
        self.code_patterns = [
            r"write\s+(a\s+)?(python|javascript|java|go|rust|function|code)",
            r"implement\s+(a\s+)?algorithm",
            r"reverse\s+(a\s+)?linked\s+list",
            r"leetcode",
            r"time\s+complexity",
            r"space\s+complexity",
            r"debug\s+this",
            r"fix\s+this\s+code"
        ]
        
        self.reasoning_patterns = [
            r"explain\s+(concept|how|why|quantum|relativity|black\s+hole)",
            r"compare\s+and\s+contrast",
            r"what'?s\s+the\s+difference",
            r"prove\s+that",
            r"mathematical\s+proof"
        ]
        
        self.creative_patterns = [
            r"write\s+(a\s+)?(poem|story|essay|script)",
            r"create\s+(a\s+)?(recipe|workout|plan)",
            r"design\s+(a\s+)?(logo|ui|website)"
        ]
        
        # Confidence weights
        self.weights = {
            "length": 0.3,
            "keywords": 0.5,
            "complexity": 0.2
        }
    
    def _length_score(self, query: str) -> float:
        """Score based on query length"""
        length = len(query)
        if length < 50:
            return 0.2  # Very short = simple
        elif length < 150:
            return 0.5  # Medium
        elif length < 300:
            return 0.7  # Long
        else:
            return 0.9  # Very long = complex
    
    def _keyword_score(self, query: str) -> float:
        """Score based on keyword presence"""
        query_lower = query.lower()
        
        # Check for code patterns
        for pattern in self.code_patterns:
            if re.search(pattern, query_lower):
                return 0.9
        
        # Check for reasoning patterns
        for pattern in self.reasoning_patterns:
            if re.search(pattern, query_lower):
                return 0.8
        
        # Check for creative patterns
        for pattern in self.creative_patterns:
            if re.search(pattern, query_lower):
                return 0.7
        
        return 0.3
    
    def _query_type_from_keywords(self, query: str) -> str:
        """Classify query type for cache TTL"""
        query_lower = query.lower()
        
        if any(re.search(p, query_lower) for p in self.code_patterns):
            return "code"
        elif any(re.search(p, query_lower) for p in self.creative_patterns):
            return "creative"
        else:
            return "factual"
    
    async def analyze(
        self, 
        query: str, 
        budget_remaining: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Analyze query and return decision with confidence
        
        Returns: {
            "target": "cpu" or "gpu",
            "confidence": float,
            "query_type": str,
            "reason": str,
            "estimated_tokens": int
        }
        """
        length_score = self._length_score(query)
        keyword_score = self._keyword_score(query)
        
        # Combined score (weighted)
        gpu_score = (
            self.weights["length"] * length_score +
            self.weights["keywords"] * keyword_score
        )
        
        # Default to CPU if budget is low
        if budget_remaining is not None and budget_remaining < 0.50:
            return {
                "target": Decision.CPU,
                "confidence": 0.8,
                "query_type": self._query_type_from_keywords(query),
                "reason": "Budget low, conserving GPU usage",
                "estimated_tokens": len(query.split()) * 2
            }
        
        # Decision threshold - can be tuned
        if gpu_score >= 0.65:
            target = Decision.GPU
            confidence = gpu_score
            reason = "Complex query requiring GPU"
        else:
            target = Decision.CPU
            confidence = 1 - gpu_score
            reason = "Simple query, CPU sufficient"
        
        return {
            "target": target,
            "confidence": round(confidence, 2),
            "query_type": self._query_type_from_keywords(query),
            "reason": reason,
            "estimated_tokens": len(query.split()) * 2,
            "length_score": length_score,
            "keyword_score": keyword_score
        }

# Singleton instance
decision_engine = DecisionEngine()

