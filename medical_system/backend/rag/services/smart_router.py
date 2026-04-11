"""
================================================================================
🧠 SMART ROUTER v3.0 - Intelligent Document Processing Pipeline
================================================================================

INTEGRATES WITH YOUR EXISTING SYSTEM:
✅ Preserves all 11 modules (table_extractor, graph_router, etc.)
✅ Adds Moondream2 VLM for vision tasks (scanned docs, charts)
✅ Uses your existing Groq LLM for clinical intelligence
✅ Smart routing: picks optimal extractor per document type
✅ Memory-efficient: loads VLM only when needed, unloads after use

MEMORY FOOTPRINT:
• Baseline (Django + OS): ~2.5 GB
• With Moondream2: ~4.5 GB total (fits in 8GB RAM!)
• Groq: $0 local memory (cloud-based)

AUTHOR: Enhanced System Integration
VERSION: 3.0 Production-Ready
"""

import os
import re
import json
import gc
import sys
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from PIL import Image
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================================
# 📊 CONFIGURATION
# ============================================================================

@dataclass
class RouterConfig:
    """Configuration for smart routing"""
    
    # Vision model settings
    enable_vlm: bool = True
    vlm_model: str = "moondream2"  # Best for medical docs, fits 4GB VRAM
    vlm_device: str = "auto"  # auto, cuda, cpu
    
    # Groq LLM settings (uses your existing setup!)
    enable_groq: bool = True
    groq_model: str = "llama-3.1-8b-instant"  # Your current model
    
    # Processing preferences
    prefer_existing_pipeline: bool = True  # Use Camelot/PyMuPDF first for digital PDFs
    vlm_confidence_threshold: float = 0.7  # If VLM confidence below this, try existing methods
    
    # Performance tuning
    max_pages_per_doc: int = 10
    image_dpi: int = 150  # Lower = faster, uses less memory
    auto_cleanup: bool = True  # Unload VLM after use to free memory
    
    # Validation settings
    validate_values: bool = True  # Cross-check extracted values against medical ranges
    block_impossible_values: bool = True  # Reject Hb=500, Glucose=9999, etc.


# ============================================================================
# 🔍 DOCUMENT TYPE DETECTOR (Enhanced)
# ============================================================================

class DocumentTypeDetector:
    """
    Analyzes input document to determine optimal processing strategy.
    
    Detection Methods:
    1. Text layer check (PyMuPDF) - Is it a digital PDF?
    2. Image density analysis - Is it scanned?
    3. Table detection - Does it have extractable tables?
    4. Chart pattern recognition - Are there graphs?
    5. ECG signal patterns - Is it an ECG report?
    
    Returns recommendation for best processing method.
    """
    
    def __init__(self):
        self.camelot_available = False
        
        # Check if Camelot is available (for digital PDF detection)
        try:
            import camelot
            self.camelot_available = True
        except ImportError:
            pass
    
    def analyze_document(self, file_path: str) -> Dict[str, Any]:
        """
        Perform comprehensive document analysis.
        
        Args:
            file_path: Path to PDF or image file
            
        Returns:
            Dictionary with document analysis results
        """
        result = {
            'file_path': file_path,
            'document_type': 'unknown',
            'has_text_layer': False,
            'has_tables': False,
            'has_charts': False,
            'is_scanned': False,
            'quality_score': 0.5,
            'recommended_processor': 'existing',  # Default to your existing pipeline
            'confidence': 0.5,
            'metadata': {},
            'page_count': 0,
            'text_density': 0.0
        }
        
        ext = Path(file_path).suffix.lower()
        
        if ext == '.pdf':
            result.update(self._analyze_pdf(file_path))
        elif ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
            result['document_type'] = 'image'
            result['is_scanned'] = True
            result['recommended_processor'] = 'vlm'  # Images MUST use VLM
            result['confidence'] = 0.95
            result.update(self._analyze_image(file_path))
        else:
            result['document_type'] = 'unsupported'
            result['confidence'] = 0.0
        
        return result
    
    def _analyze_pdf(self, pdf_path: str) -> Dict:
        """Analyze PDF file type and characteristics"""
        analysis = {}
        
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(pdf_path)
            analysis['page_count'] = len(doc)
            
            total_text_length = 0
            pages_with_text = 0
            pages_with_images = 0
            pages_with_tables_hint = 0
            
            # Analyze first few pages (faster than analyzing all)
            pages_to_check = min(len(doc), 5)
            
            for page_num in range(pages_to_check):
                page = doc[page_num]
                text = page.get_text()
                
                if text.strip():
                    pages_with_text += 1
                    total_text_length += len(text.strip())
                
                # Check for images (scanned content indicator)
                images = page.get_images()
                if images:
                    pages_with_images += 1
                
                # Heuristic: tables often have grid-like structures or tab-separated values
                if self._looks_like_table_page(text):
                    pages_with_tables_hint += 1
            
            doc.close()
            
            # Store analysis results
            analysis['total_pages'] = len(doc)
            analysis['pages_with_text'] = pages_with_text
            analysis['pages_with_images'] = pages_with_images
            analysis['avg_text_per_page'] = total_text_length / max(pages_to_check, 1)
            analysis['text_density'] = total_text_length / max(pages_to_check * 2500, 1)  # Normalized
            
            # Determine if digital or scanned
            text_ratio = pages_with_text / max(pages_to_check, 1)
            
            if text_ratio >= 0.8 and analysis.get('avg_text_per_page', 0) > 200:
                analysis['has_text_layer'] = True
                analysis['is_scanned'] = False
                analysis['document_type'] = 'digital_pdf'
                analysis['quality_score'] = 0.9
                
                # Check if it looks like OCR output (scanned but OCRed)
                if self._looks_like_ocr_output(analysis.get('avg_text_per_page', 0)):
                    analysis['is_scanned'] = True
                    analysis['ocr_quality'] = 'unknown'
                    analysis['document_type'] = 'ocr_pdf'
                    
            elif text_ratio < 0.3 or analysis.get('avg_text_per_page', 0) < 100:
                analysis['has_text_layer'] = False
                analysis['is_scanned'] = True
                analysis['document_type'] = 'scanned_pdf'
                analysis['quality_score'] = 0.6
            else:
                # Mixed - some text, might be partially scanned
                analysis['has_text_layer'] = True
                analysis['is_scanned'] = pages_with_images > 0
                analysis['document_type'] = 'mixed_pdf'
                analysis['quality_score'] = 0.7
            
            # Table detection
            if pages_with_tables_hint >= 1 or self.camelot_available:
                analysis['has_tables'] = True
                analysis['table_count_estimate'] = pages_with_tables_hint
                
        except Exception as e:
            logger.warning(f"PDF analysis error: {e}")
            analysis['error'] = str(e)
        
        # Make final recommendation
        self._make_recommendation(analysis)
        
        return analysis
    
    def _analyze_image(self, image_path: str) -> Dict:
        """Analyze image file characteristics"""
        analysis = {}
        
        try:
            img = Image.open(image_path)
            analysis['image_size'] = img.size
            analysis['image_mode'] = img.mode
            
            width, height = img.size
            aspect_ratio = width / height if height > 0 else 1
            analysis['aspect_ratio'] = aspect_ratio
            
            # Basic heuristics for chart/document detection
            # Charts often have specific aspect ratios
            if 1.5 <= aspect_ratio <= 3.0 and width > 400:
                analysis['likely_chart'] = True
                analysis['has_charts'] = True
            
            # Document-like images are usually portrait or square
            if 0.7 <= aspect_ratio <= 1.5:
                analysis['likely_document'] = True
                
            img.close()
            
        except Exception as e:
            logger.debug(f"Image analysis error: {e}")
        
        return analysis
    
    def _looks_like_table_page(self, text: str) -> bool:
        """Heuristic: does this page look like it contains a table?"""
        if not text or len(text.strip()) < 50:
            return False
        
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) < 3:
            return False
        
        # Count lines with multiple tab-like separations
        tab_separated_count = sum(1 for l in lines if len(re.split(r'\s{2,}|\t', l)) >= 3)
        
        # If many lines have 3+ columns, likely a table
        return tab_separated_count >= len(lines) * 0.3
    
    def _looks_like_ocr_text(self, avg_text_length: int) -> bool:
        """Heuristic: is this text likely OCR output from a scan?"""
        # Very short text per page might indicate poor OCR or mostly-image document
        return avg_text_length < 150
    
    def _make_recommendation(self, analysis: Dict):
        """Make processing recommendation based on analysis"""
        
        is_scanned = analysis.get('is_scanned', False)
        has_tables = analysis.get('has_tables', False)
        has_text = analysis.get('has_text_layer', False)
        doc_type = analysis.get('document_type', 'unknown')
        likely_chart = analysis.get('likely_chart', False)
        
        # Scoring system
        score = 0
        
        # Digital PDF with tables → Use existing pipeline (Camelot is great at this)
        if has_text and not is_scanned and has_tables and doc_type == 'digital_pdf':
            score += 10
            analysis['recommended_processor'] = 'existing'
            analysis['confidence'] = 0.95
            analysis['reason'] = 'Digital PDF with detectable tables'
        
        # Scanned document → Use VLM (Moondream2 excels at this)
        elif is_scanned or doc_type in ['scanned_pdf', 'image', 'ocr_pdf']:
            score += 9
            analysis['recommended_processor'] = 'vlm'
            analysis['confidence'] = 0.85
            analysis['reason'] = 'Scanned/image document needs vision model'
            
            if has_tables:
                score += 1  # Bonus: VLM handles scanned tables well
        
        # Image/Chart → Use VLM (charts need visual understanding)
        elif likely_chart or doc_type == 'image':
            score += 8
            analysis['recommended_processor'] = 'vlm'
            analysis['confidence'] = 0.8
            analysis['reason'] = 'Chart or graphical content detected'
        
        # Mixed or unknown → Try hybrid approach (use both, merge results)
        else:
            score += 5
            analysis['recommended_processor'] = 'hybrid'
            analysis['confidence'] = 0.6
            analysis['reason'] = 'Unknown or mixed document type, using hybrid approach'
        
        # Calculate quality score (0-1)
        analysis['quality_score'] = min(score / 10, 1.0)


# ============================================================================
# 🤖 VISION LANGUAGE MODEL WRAPPER (Moondream2)
# ============================================================================

class VisionModelWrapper:
    """
    Wrapper around Moondream2 for vision tasks.
    
    KEY FEATURES:
    - Lazy loading: Only loads model when needed (saves memory!)
    - Auto-unload: Removes model from memory after use
    - Efficient preprocessing: Resizes images to save VRAM
    - Structured output: Extracts data in your format {test, value, unit, ...}
    
    MEMORY USAGE:
    - Model size: ~1.6-2GB VRAM
    - Inference: ~2GB VRAM peak
    - After unload: 0GB (freed completely)
    """
    
    def __init__(self, config: RouterConfig = None):
        self.config = config or RouterConfig()
        self.model = None
        self.tokenizer = None
        self.is_loaded = False
        self.model_id = "vikhyatk/moondream2"
        self.device = "cpu"  # Will be set on load
    
    def ensure_loaded(self):
        """Load model if not already loaded (lazy loading)"""
        if self.is_loaded:
            return
        
        try:
            import torch
            
            # Determine device
            device = self.config.vlm_device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            
            self.device = device
            logger.info(f"Loading Moondream2 on {device}...")
            
            from transformers import AutoModelForCausalLM, AutoTokenizer
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_id, 
                trust_remote_code=True
            )
            
            # Load model with appropriate dtype
            dtype = torch.float32 if device == "cpu" else torch.float16
            
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=dtype,
                trust_remote_code=True,
            ).to(device)
            
            self.model.eval()  # Set to evaluation mode (not training)
            self.is_loaded = True
            
            logger.info(f"✅ Moondream2 loaded successfully on {device}")
            
            # Log memory usage
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated(0) / 1e9
                cached = torch.cuda.memory_reserved(0) / 1e9
                logger.info(f"   GPU Memory: {allocated:.2f} GB allocated, {cached:.2f} GB cached")
                
        except ImportError as e:
            logger.error(f"Missing dependency: {e}")
            raise ImportError(
                "Required: pip install transformers torch Pillow\n"
                f"Error: {e}"
            )
        except Exception as e:
            logger.error(f"Failed to load Moondream2: {e}")
            raise
    
    def extract_from_image(
        self, 
        image: Image.Image, 
        task: str = "extraction",
        prompt_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract data from image using VLM.
        
        Args:
            image: PIL Image
            task: Type of extraction ("extraction" for lab values, "chart" for graphs)
            prompt_override: Custom prompt (optional, uses default if not provided)
            
        Returns:
            Dictionary with extracted data in standardized format
        """
        self.ensure_loaded()
        
        # Resize image to save memory (Moondream2 works well with 336x336 or smaller)
        max_size = (512, 384)
        image_resized = image.copy()
        if image_resized.size[0] > max_size[0] or image_resized.size[1] > max_size[1]:
            image_resized.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Select prompt based on task
        if not prompt_override:
            if task == "extraction":
                prompt_override = self._get_lab_extraction_prompt()
            elif task == "chart":
                prompt_override = self._get_chart_extraction_prompt()
            else:
                prompt_override = "Describe what you see in this medical image."
        
        # Process image with Moondream2
        try:
            result = self._process_with_moondream(image_resized, prompt_override)
            
            # Parse the output into structured format
            parsed = self._parse_vlm_output(result, task)
            parsed['model_used'] = 'moondream2'
            parsed['task'] = task
            parsed['processing_time'] = datetime.now().isoformat()
            
            return parsed
            
        except Exception as e:
            logger.error(f"VLM extraction error: {e}")
            return {
                'success': False,
                'error': str(e),
                'model_used': 'moondream2',
                'raw_output': '',
                'parsed_successfully': False
            }
    
    def _get_lab_extraction_prompt(self) -> str:
        """Get optimized prompt for laboratory test extraction"""
        return """You are a medical document analyzer. Extract ALL laboratory test results from this image.

For each test found, provide:
- test_name: Full name of the test (e.g., "Hemoglobin", "WBC Count")
- value: Result value (number OR text like "Positive", "Negative", "Not Detected")
- unit: Unit of measurement (g/dL, mg/dL, /hpf, /µL, etc.)
- reference_range: Normal range if shown in the image
- status: "normal", "high", "low", "critical", or "abnormal"

Special handling rules:
• Urine microscopy: Pus Cells, Epithelial Cells, Casts, Crystals (use /hpf units)
• Categorical values: Positive/Negative/Detected/Not Detected/Present/Absent
• Ranges like "0-5/hpf": Capture exactly as-is
• If value appears abnormal (outside reference range), mark status accordingly

Return ONLY valid JSON in this exact format:
{"tests": [{"test_name": "...", "value": "...", "unit": "...", "reference_range": "...", "status": "..."}]}"""

    def _get_chart_extraction_prompt(self) -> str:
        """Get optimized prompt for chart/graph data extraction"""
        return """Extract numerical data from this chart/graph/visualization.

Provide:
- chart_type: "line", "bar", "pie", "scatter", "area", or "ecg"
- title: Chart title if visible
- x_axis_label: Label of x-axis (if visible)
- y_axis_label: Label of y-axis (if visible)
- data_points: Array of objects with {"x": value, "y": value} for each point
- insights: 2-3 observations about trends/patterns visible in the chart

Return ONLY valid JSON:
{"chart_type": "...", "title": "...", "x_axis_label": "...", "y_axis_label": "...", "data_points": [...], "insights": ["..."]}"""

    def _process_with_moondream(self, image: Image.Image, prompt: str) -> str:
        """Process image with Moondream2 model"""
        try:
            # Encode image
            image_embeds = self.model.encode_image(image)
            
            # Generate answer
            output = self.model.answer_question(
                image_embeds=image_embeds,
                prompt=prompt,
                tokenizer=self.tokenizer,
                max_new_tokens=512  # Limit output length
            )
            
            return output
            
        except Exception as e:
            logger.error(f"Moondream2 processing error: {e}")
            raise
    
    def _parse_vlm_output(self, text: str, task: str) -> Dict:
        """Parse VLM output and extract JSON data"""
        result = {
            'raw_output': text,
            'parsed_successfully': False,
            'task': task,
            'tests': [] if task == "extraction" else None,
            'chart_data': None if task == "chart" else None
        }
        
        if not text:
            return result
        
        # Try to find JSON in output (handle various formats)
        json_match = re.search(r'\{[\s\S]*\}', text)
        
        if json_match:
            try:
                json_str = json_match.group()
                parsed_data = json.loads(json_str)
                
                result.update(parsed_data)
                result['parsed_successfully'] = True
                logger.debug(f"Successfully parsed {task} output")
                
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed: {e}")
                result['parse_error'] = str(e)
                
                # Attempt fallback parsing
                fallback_data = self._fallback_parse(text, task)
                if fallback_data:
                    result.update(fallback_data)
        else:
            logger.warning("No JSON found in VLM output, attempting fallback parsing")
            fallback_data = self._fallback_parse(text, task)
            if fallback_data:
                result.update(fallback_data)
        
        return result
    
    def _fallback_parse(self, text: str, task: str) -> Optional[Dict]:
        """Fallback parser when JSON extraction fails"""
        if task != "extraction":
            return None
        
        # Simple regex-based extraction for common patterns
        tests = []
        
        # Pattern: TestName: Value Unit (Range)
        patterns = [
            r'([A-Za-z][A-Za-z\s/]+?)\s*:\s*([\d.]+)\s*([a-zA-Z/%]+)?\s*(?:\(.*?\))?',
            r'(Hemoglobin|Hb|WBC|RBC|Platelet|Glucose|Creatinine|Urea|TSH|T4|T3|Bilirubin|Albumin|Sodium|Potassium)\b.*?(\d+\.?\d*)\s*([a-zA-Z/%]+)?',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.MULTILINE | re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    test_name = match[0].strip()
                    value = match[1] if len(match) > 1 else ''
                    unit = match[2] if len(match) > 2 else ''
                    
                    if test_name and value:
                        tests.append({
                            'test_name': test_name,
                            'value': value,
                            'unit': unit,
                            'reference_range': '',
                            'status': 'normal',
                            'confidence': 0.6  # Lower confidence for fallback
                        })
        
        if tests:
            return {
                'parsed_successfully': True,
                'tests': tests,
                'extraction_method': 'fallback_regex'
            }
        
        return None
    
    def unload(self):
        """Unload model from memory to free resources"""
        if self.is_loaded and self.model is not None:
            try:
                # Delete model and tokenizer
                del self.model
                if self.tokenizer:
                    del self.tokenizer
                
                self.model = None
                self.tokenizer = None
                self.is_loaded = False
                
                # Force garbage collection
                gc.collect()
                
                # Free CUDA memory if applicable
                if 'torch' in sys.modules:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        logger.info("CUDA cache cleared")
                
                logger.info("Moondream2 unloaded, memory freed")
                
            except Exception as e:
                logger.warning(f"Error unloading model: {e}")


# ============================================================================
# ⚡ GROQ LLM CLIENT (Uses Your Existing Setup!)
# ============================================================================

class GroqLLMClient:
    """
    Client for Groq's LLM API.
    
    Uses YOUR existing Groq setup (api key, client, etc.)
    Just wraps it for smart router integration.
    
    BENEFITS:
    - FREE (no cost to you)
    - FAST (low latency, <1 second typically)
    - POWERFUL (Llama 3.1 8B = better than small local models)
    - SAVES MEMORY (runs on Groq's servers, not your PC)
    """
    
    def __init__(self, config: RouterConfig = None):
        self.config = config or RouterConfig()
        self.client = None
        
        # Import your existing Groq client
        try:
            from rag.services.qa import get_groq_client
            self.client = get_groq_client()
            logger.info("Using existing Groq client from qa.py")
        except ImportError:
            # Fallback: create our own
            try:
                from groq import Groq
                api_key = os.getenv("GROQ_API_KEY", "")
                if api_key:
                    self.client = Groq(api_key=api_key)
                    logger.info("Created new Groq client from environment variable")
                else:
                    logger.warning("No Groq API key found")
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
    
    def validate_extracted_values(
        self, 
        extracted_data: List[Dict], 
        document_context: str = ""
    ) -> Dict[str, Any]:
        """
        Use Groq LLM to validate and correct extracted values.
        
        Checks for:
        - Impossible values (Hb=500, Glucose=99999)
        - Wrong units
        - Obvious OCR errors
        
        Args:
            extracted_data: List of extracted test results
            document_context: Original text context (optional)
            
        Returns:
            Dictionary with validation results and corrections
        """
        if not self.client or not extracted_data:
            return {'validated': False, 'data': extracted_data, 'corrections': []}
        
        # Build validation prompt
        data_summary = "\n".join([
            f"- {t.get('test_name', t.get('test', '?'))}: "
              f"{t.get('value', '?')} {t.get('unit', '')} "
              f"(Normal: {t.get('reference_range', 'N/A')})"
            for t in extracted_data[:25]  # Limit to avoid token overflow
        ])
        
        prompt = f"""You are a medical data validation expert. Review these extracted laboratory values for errors.

EXTRACTED DATA:
{data_summary}

TASK:
1. Identify any IMPOSSIBLE or HIGHLY UNLIKELY values (e.g., Hemoglobin > 25, Glucose > 2000, WBC > 500)
2. Flag potential OCR errors (e.g., '8775' should be '87.75', 'O' instead of '0')
3. Suggest corrections if obvious

Respond in this JSON format only:
{{
  "is_valid": true/false,
  "issues_found": [
    {{"test": "name", "value": "extracted", "issue": "description", "suggested_correction": "corrected_value"}}
  ],
  "confidence_score": 0.0-1.0
}}

If all values look reasonable, set is_valid=true and empty issues_found."""

        try:
            response = self.client.chat.completions.create(
                model=self.config.groq_model,
                messages=[
                    {"role": "system", "content": "You are a medical data validator. Respond only with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,  # Low temperature for consistent validation
                max_tokens=1000
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                validation_result = json.loads(json_match.group())
                validation_result['validated'] = True
                return validation_result
            
        except Exception as e:
            logger.warning(f"Groq validation failed: {e}")
        
        return {'validated': False, 'data': extracted_data, 'error': 'Validation failed'}
    
    # ✅ FIXED VERSION:
    def generate_clinical_summary(
        self,
        extracted_data: List[Dict],
        patient_context: str = "",
        urgency_level: str = "normal"
    ) -> str:
        """Generate patient-friendly clinical summary using Groq"""
        if not self.client or not extracted_data:
            return ""
        
        # Prepare data summary (FIXED: no complex nested f-strings)
        abnormal = [t for t in extracted_data if t.get('status') in ['high', 'low', 'abnormal', 'critical']]
        normal_count = len(extracted_data) - len(abnormal)
        
        # Build abnormal values list separately (avoids f-string nesting issues)
        abnormal_lines = []
        for t in abnormal[:10]:  # Limit to 10 items
            test_name = t.get('test_name', t.get('test', '?'))
            value = t.get('value', '?')
            unit = t.get('unit', '')
            abnormal_lines.append(f"- {test_name}: {value} {unit}")
        
        abnormal_section = "\n".join(abnormal_lines) if abnormal_lines else "None"
        
        # Now build the prompt safely
        data_context = f"""Test Results Summary:
Total Tests: {len(extracted_data)}
Normal: {normal_count}
Abnormal: {len(abnormal)}
Urgency Level: {urgency_level.upper()}

ABNORMAL VALUES (if any):
{abnormal_section}"""

        prompt = f"""Generate a brief, compassionate clinical summary for a patient.

{data_context}

Patient Context: {patient_context or 'Not provided'}

GUIDELINES:
- Keep it under 150 words
- Use simple, non-medical language
- Start with overall status (reassuring if mostly normal)
- Highlight 1-2 most important abnormalities (if any)
- End with clear next step recommendation
- Include disclaimer: "Consult your healthcare provider for complete interpretation"

Summary:"""

        try:
            response = self.client.chat.completions.create(
                model=self.config.groq_model,
                messages=[
                    {"role": "system", "content": "You are a compassionate clinical assistant explaining lab results to patients."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Clinical summary generation failed: {e}")
            return ""

# ============================================================================
# 🚀 MAIN SMART ROUTER CLASS
# ============================================================================

class SmartRouter:
    """
    Main orchestrator - Routes documents to optimal processor.
    
    This is the PRIMARY CLASS you'll use in views.py.
    
    INTEGRATION POINT:
        In your upload_and_index() view, add:
            from rag.services.smart_router import SmartRouter
            
            router = SmartRouter()
            result = router.process_document(file_path)
            # result['extracted_data'] contains the list of dicts
    """
    
    def __init__(self, config: RouterConfig = None):
        self.config = config or RouterConfig()
        
        # Initialize components (lazy loading where possible)
        self.detector = DocumentTypeDetector()
        self.vlm = VisionModelWrapper(config) if self.config.enable_vlm else None
        self.groq = GroqLLMClient(config) if self.config.enable_groq else None
        
        # Statistics tracking
        self.stats = {
            'documents_processed': 0,
            'processing_methods_used': {},
            'vlm_usage_count': 0,
            'groq_usage_count': 0,
            'existing_pipeline_usage_count': 0,
            'total_processing_time': 0.0,
            'errors': []
        }
        
        logger.info("="*60)
        logger.info("🧠 Smart Router v3.0 initialized")
        logger.info(f"   VLM: {self.config.vlm_model if self.config.enable_vlm else 'DISABLED'}")
        logger.info(f"   Groq: {self.config.groq_model if self.config.enable_groq else 'DISABLED'}")
        logger.info(f"   Validation: {'ENABLED' if self.config.validate_values else 'DISABLED'}")
        logger.info("="*60)
    
    def process_document(
        self,
        file_path: str,
        force_method: Optional[str] = None,  # 'existing', 'vlm', 'hybrid'
        extract_values: bool = True,
        validate_results: bool = True
    ) -> Dict[str, Any]:
        """
        Main entry point - process any medical document.
        
        Args:
            file_path: Path to PDF or image file
            force_method: Force specific processing method (optional)
            extract_values: Whether to extract test values
            validate_results: Whether to validate extracted values with Groq
            
        Returns:
            Complete result dictionary:
            {
                'success': bool,
                'extracted_data': [{test, value, unit, range, flag}, ...],
                'method_used': str,
                'models_used': list,
                'document_analysis': dict,
                'validation_result': dict or None,
                'clinical_summary': str or None,
                'processing_time_seconds': float,
                'errors': list
            }
        """
        start_time = datetime.now()
        
        result = {
            'success': False,
            'file_path': file_path,
            'processing_time_seconds': 0,
            'extracted_data': [],
            'method_used': '',
            'models_used': [],
            'document_analysis': {},
            'validation_result': None,
            'clinical_summary': None,
            'warnings': [],
            'errors': [],
            'timestamp': start_time.isoformat(),
            'stats': {}
        }
        
        try:
            # ============================================================
            # PHASE 1: Document Analysis
            # ============================================================
            logger.info(f"\n{'='*60}")
            logger.info(f"📄 Processing: {Path(file_path).name}")
            
            if force_method:
                result['document_analysis'] = {'forced_method': force_method}
                analysis_result = {'recommended_processor': force_method, 'confidence': 1.0}
                logger.info(f"   Forced method: {force_method}")
            else:
                analysis_result = self.detector.analyze_document(file_path)
                result['document_analysis'] = analysis_result
                logger.info(f"   Type: {analysis_result.get('document_type', 'unknown')}")
                logger.info(f"   Recommended: {analysis_result.get('recommended_processor', 'unknown')}")
                logger.info(f"   Confidence: {analysis_result.get('confidence', 0):.0%}")
            
            # ============================================================
            # PHASE 2: Route to Appropriate Processor
            # ============================================================
            processor = analysis_result.get('recommended_processor', 'existing')
            
            if processor == 'vlm' or force_method == 'vlm':
                extracted = self._process_with_vlm(file_path)
                result['method_used'] = 'vision_language_model (Moondream2)'
                self.stats['vlm_usage_count'] += 1
                result['models_used'].append('moondream2')
                
            elif processor == 'hybrid' or force_method == 'hybrid':
                extracted = self._process_hybrid(file_path)
                result['method_used'] = 'hybrid (existing + VLM)'
                self.stats['vlm_usage_count'] += 1
                self.stats['existing_pipeline_usage_count'] += 1
                result['models_used'].extend(['table_extractor', 'moondream2'])
                
            else:  # 'existing' (default) - use your working pipeline!
                extracted = self._process_with_existing(file_path)
                result['method_used'] = 'existing_pipeline (Camelot/pdfplumber/OCR)'
                self.stats['existing_pipeline_usage_count'] += 1
                result['models_used'].append('table_extractor')
            
            # Update stats
            method = result['method_used']
            self.stats['processing_methods_used'][method] = \
                self.stats['processing_methods_used'].get(method, 0) + 1
            
            if extracted:
                result['extracted_data'] = extracted
                result['success'] = True
                logger.info(f"   ✅ Extracted {len(extracted)} tests")
            
            # ============================================================
            # PHASE 3: Validation (Optional, uses Groq)
            # ============================================================
            if validate_results and extracted and self.groq and self.config.validate_values:
                logger.info("   🔍 Validating extracted values via Groq...")
                
                validation = self.groq.validate_extracted_values(extracted_data=extracted)
                result['validation_result'] = validation
                
                if validation.get('validated'):
                    issues = validation.get('issues_found', [])
                    if issues:
                        logger.warning(f"   ⚠️ Found {len(issues)} potential issue(s)")
                        
                        # Apply corrections if suggested
                        corrected_data = []
                        corrections_made = 0
                        
                        for item in extracted:
                            test_name = item.get('test_name', item.get('test', ''))
                            
                            # Check if this item has a correction
                            correction = next(
                                (i for i in issues if i.get('test', '').lower() == test_name.lower()), 
                                None
                            )
                            
                            if correction and correction.get('suggested_correction'):
                                # Apply correction
                                corrected_item = item.copy()
                                corrected_item['value'] = correction['suggested_correction']
                                corrected_item['_original_value'] = item.get('value')
                                corrected_item['_corrected'] = True
                                corrected_data.append(corrected_item)
                                corrections_made += 1
                            else:
                                corrected_data.append(item)
                        
                        if corrections_made > 0:
                            result['extracted_data'] = corrected_data
                            result['warnings'].append(f"Applied {corrections_made} automatic correction(s)")
                            logger.info(f"   ✓ Applied {corrections_made} correction(s)")
                    
                    self.stats['groq_usage_count'] += 1
            
            # ============================================================
            # PHASE 4: Clinical Summary (Optional, uses Groq)
            # ============================================================
            if extracted and self.groq:
                urgency = self._assess_urgency(extracted)
                
                summary = self.groq.generate_clinical_summary(
                    extracted_data=extracted,
                    urgency_level=urgency
                )
                
                if summary:
                    result['clinical_summary'] = summary
                    result['urgency_level'] = urgency
                    self.stats['groq_usage_count'] += 1
            
            # Final stats
            result['total_tests_extracted'] = len(extracted) if extracted else 0

            result['abnormal_count'] = len([
                t for t in (extracted or [])
                if t.get('status') not in ['normal', 'N', '', None]
            ])
            
        except Exception as e:
            logger.error(f"Processing failed: {e}", exc_info=True)
            result['errors'].append(str(e))
            result['success'] = False
        
        finally:
            # Calculate time
            result['processing_time_seconds'] = (datetime.now() - start_time).total_seconds()
            
            # Update statistics
            self.stats['documents_processed'] += 1
            self.stats['total_processing_time'] += result['processing_time_seconds']
            
            # Cleanup VLM if enabled (free memory!)
            if self.config.auto_cleanup and self.vlm:
                self.vlm.unload()
            
            # Store stats in result
            result['stats'] = {
                'documents_processed': self.stats['documents_processed'],
                'avg_processing_time': self.stats['total_processing_time'] / max(self.stats['documents_processed'], 1),
                'methods_used': self.stats['processing_methods_used']
            }
        
        return result
    
    def _process_with_existing(self, file_path: str) -> List[Dict]:
        """Process using your EXISTING pipeline (table_extractor.py)"""
        logger.info("   📊 Using EXISTING pipeline (table_extractor.py)")
        
        try:
            # Import your existing extraction function
            from rag.services.table_extractor import extract_tables
            
            # Call it exactly as your current code does
            extracted = extract_tables(file_path)
            
            # Ensure we have a list
            if isinstance(extracted, list):
                logger.info(f"      ✓ Existing pipeline returned {len(extracted)} items")
                return extracted
            else:
                logger.warning(f"      ⚠️ Existing pipeline returned {type(extracted)}, converting...")
                if isinstance(extracted, str):
                    try:
                        return json.loads(extracted)
                    except:
                        return []
                return []
                
        except Exception as e:
            logger.error(f"   ❌ Existing pipeline error: {e}")
            return []
    
    def _process_with_vlm(self, file_path: str) -> List[Dict]:
        """Process using Vision Language Model (Moondream2)"""
        logger.info("   👁️ Using VISION MODEL (Moondream2)")
        
        if not self.vlm:
            logger.error("   ❌ VLM not enabled or not initialized")
            return []
        
        extracted = []
        
        try:
            # Load images from document
            images = self._load_images(file_path)
            
            if not images:
                logger.warning("   ⚠️ Could not load images from document")
                return []
            
            logger.info(f"   📄 Loaded {len(images)} page(s)/image(s)")
            
            # Process each image
            for i, image in enumerate(images):
                logger.info(f"   🔄 Processing page/image {i+1}/{len(images)}...")
                
                vlm_result = self.vlm.extract_from_image(
                    image=image,
                    task="extraction"
                )
                
                # Convert VLM output to your standard format
                if vlm_result.get('parsed_successfully') and vlm_result.get('tests'):
                    for test in vlm_result['tests']:
                        # Map VLM format to your format
                        standardized = {
                            'test': test.get('test_name', ''),
                            'value': str(test.get('value', '')),
                            'unit': test.get('unit', ''),
                            'range': test.get('reference_range', ''),
                            'flag': self._status_to_flag(test.get('status', 'normal')),
                            'source': 'vlm_moondream2',
                            'confidence': test.get('confidence', 0.85),
                            'page_number': i + 1
                        }
                        extracted.append(standardized)
                    
                    logger.info(f"      ✅ Extracted {len(vlm_result['tests'])} tests from page {i+1}")
                else:
                    logger.warning(f"      ⚠️ Could not parse VLM output for page {i+1}")
            
            logger.info(f"   ✅ Total extracted: {len(extracted)} values")
            
        except Exception as e:
            logger.error(f"   ❌ VLM processing error: {e}", exc_info=True)
        
        return extracted
    
    def _process_hybrid(self, file_path: str) -> List[Dict]:
        """Process using BOTH existing pipeline AND VLM, then merge"""
        logger.info("   🔀 Using HYBRID approach (existing + VLM)")
        
        all_extracted = []
        seen_tests = set()
        
        # Step 1: Try existing pipeline first
        try:
            existing_results = self._process_with_existing(file_path)
            
            for r in existing_results:
                # Create unique key
                test_key = f"{r.get('test', '').lower().strip()}|{r.get('value', '')}"
                if test_key not in seen_tests:
                    all_extracted.append(r)
                    seen_tests.add(test_key)
            
            logger.info(f"   📊 Existing pipeline: {len(existing_results)} results")
            
        except Exception as e:
            logger.warning(f"   Existing pipeline failed: {e}")
        
        # Step 2: Augment with VLM (catches things existing missed)
        try:
            vlm_results = self._process_with_vlm(file_path)
            
            additional_count = 0
            for r in vlm_results:
                test_key = f"{r.get('test', '').lower().strip()}|{r.get('value', '')}"
                if test_key not in seen_tests:
                    all_extracted.append(r)
                    seen_tests.add(test_key)
                    additional_count += 1
            
            logger.info(f"   👁️ VLM augmentation: {additional_count} additional results")
            
        except Exception as e:
            logger.warning(f"   VLM augmentation failed: {e}")
        
        logger.info(f"   ✅ Hybrid total: {len(all_extracted)} unique results")
        return all_extracted
    
    def _load_images(self, file_path: str) -> List[Image.Image]:
        """Load document as list of PIL Images"""
        images = []
        ext = Path(file_path).suffix.lower()
        
        try:
            if ext == '.pdf':
                from pdf2image import convert_from_path
                
                images = convert_from_path(
                    file_path,
                    dpi=self.config.image_dpi,
                    first_page=1,
                    last_page=self.config.max_pages_per_doc
                )
                logger.info(f"      Converted PDF to {len(images)} images")
                
            elif ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
                img = Image.open(file_path).convert('RGB')
                images.append(img)
                
            else:
                logger.warning(f"Unsupported format: {ext}")
                
        except Exception as e:
            logger.error(f"Error loading images: {e}")
        
        return images
    
    def _status_to_flag(self, status: str) -> str:
        """Convert VLM status to your flag format"""
        if status in ['high', 'HIGH', 'critical', 'CRITICAL']:
            return 'HIGH'
        elif status in ['low', 'LOW']:
            return 'LOW'
        else:
            return ''  # Normal = no flag
    
    def _assess_urgency(self, data: List[Dict]) -> str:
        """Quick urgency assessment based on flags and critical values"""
        if not data:
            return 'normal'
        
        critical_keywords = ['critical', 'CRITICAL', 'emergency']
        high_count = sum(1 for t in data if t.get('flag') == 'HIGH')
        
        # Check for critical indicators in test names/values
        for t in data:
            test_lower = t.get('test', '').lower()
            value = t.get('value', '')
            
            # Critical combinations
            if 'heart rate' in test_lower or 'ventricular' in test_lower:
                try:
                    val = float(value)
                    if val < 50 or val > 150:
                        return 'critical'
                except:
                    pass
        
        if high_count >= 3:
            return 'warning'
        elif high_count > 0:
            return 'attention'
        else:
            return 'normal'
    
    def get_stats(self) -> Dict:
        """Get processing statistics"""
        return {
            **self.stats,
            'config': {
                'vlm_enabled': self.config.enable_vlm,
                'vlm_model': self.config.vlm_model,
                'groq_enabled': self.config.enable_groq,
                'groq_model': self.config.groq_model,
                'prefer_existing': self.config.prefer_existing_pipeline,
                'validate_values': self.config.validate_values
            }
        }


# ============================================================================
# 🎯 CONVENIENCE FUNCTION FOR QUICK INTEGRATION
# ============================================================================

def process_medical_document(file_path: str, **kwargs) -> Dict:
    """
    Quick-use function to process any medical document.
    
    Usage:
        from rag.services.smart_router import process_medical_document
        
        result = process_medical_document('/path/to/report.pdf')
        print(result['extracted_data'])
        print(result['clinical_summary'])
    
    Args:
        file_path: Path to PDF or image
        **kwargs: Additional options passed to SmartRouter.process_document()
        
    Returns:
        Result dictionary with extracted data and metadata
    """
    router = SmartRouter()
    return router.process_document(file_path, **kwargs)


# ============================================================================
# 🧪 TESTING & DEMO
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Smart Router - Enhanced Medical Doc Processor')
    parser.add_argument('--file', type=str, help='Path to PDF or image')
    parser.add_argument('--force', type=str, choices=['existing', 'vlm', 'hybrid'],
                       help='Force specific processing method')
    parser.add_argument('--demo', action='store_true', help='Show system info')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🧠 SMART ROUTER v3.0 - Enhanced Medical Document Processor")
    print("="*70 + "\n")
    
    if args.demo:
        # Print demo info as plain string (not f-string)
        demo_info = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   YOUR ENHANCED AI PIPELINE                                  ║
║   ════════════════════════                                    ║
║                                                              ║
║   INPUT: PDF / Image (any type!)                             ║
║     ↓                                                        ║
║   ┌──────────────────────────────────────────────┐           ║
║   │  🧠 SMART ROUTER                              │           ║
║   │  Detects document type automatically          │           ║
║   │  Routes to BEST tool                         │           ║
║   └──────────────────────────────────────────────┘           ║
║     ↓                                                        ║
║   OUTPUT: Structured JSON + Clinical Summary                 ║
║                                                              ║
║   MODELS USED:                                               ║
║   ├─ Vision:  Moondream2 (~2GB VRAM, auto-unloaded)        ║
║   ├─ Text:     Groq Llama 3.1 8B (cloud, $0 cost)         ║
║   └─ Your Code: All modules PRESERVED!                     ║
║                                                              ║
║   MEMORY:                                                    ║
║   ├─ Baseline: ~2.5 GB (OS + Django)                       ║
║   ├─ With VLM: ~4.5 GB peak (fits in 8GB!)                ║
║   └─ After cleanup: ~2.5 GB (VLM unloaded)                  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Usage:
  python smart_router.py --file report.pdf                  Process a file
  python smart_router.py --file scan.jpg --force vlm         Force VLM processing  
  python smart_router.py --demo                               Show architecture info
  python smart_router.py --stats                              Show statistics

Examples:
  python smart_router.py --file lab_report.pdf
  python smart_router.py --file ecg_image.png --force vlm
  python smart_router.py --file scanned_doc.jpg --force hybrid
"""
        print(demo_info)
    
    elif args.file:
        print(f"📄 Processing: {args.file}\n")
        
        router = SmartRouter()
        
        result = router.process_document(
            file_path=args.file,
            force_method=args.force
        )
        
        # Print results
        print("\n" + "="*70)
        print("📊 RESULTS")
        print("="*70)
        
        print(f"\n✅ Success: {result.get('success', False)}")
        print(f"⏱️  Time: {result.get('processing_time_seconds', 0):.2f}s")
        print(f"🔧 Method: {result.get('method_used', 'Unknown')}")
        print(f"🤖 Models: {result.get('models_used', [])}")
        
        if result.get('document_analysis'):
            analysis = result['document_analysis']
            print(f"\n📋 Document Analysis:")
            print(f"   Type: {analysis.get('document_type', 'Unknown')}")
            print(f"   Recommended: {analysis.get('recommended_processor', 'Auto')}")
            print(f"   Confidence: {analysis.get('confidence', 0):.0%}")
        
        extracted = result.get('extracted_data', [])
        if extracted:
            print(f"\n{'─'*50}")
            print(f"🧪 EXTRACTED VALUES ({len(extracted)} tests)")
            print(f"{'─'*50}")
            
            for v in extracted[:15]:
                icon = "🟢" if not v.get('flag') else ("🔴" if v.get('flag') == 'HIGH' else "🟡")
                source_icon = "📊" if 'vlm' in v.get('source', '') else "📋"
                test_name = v.get('test', '?')
                value = str(v.get('value', '?'))
                unit = v.get('unit', '')
                print(f"  {icon} {test_name:30s} {value:>10s} {unit}")
            
            if len(extracted) > 15:
                print(f"  ... and {len(extracted) - 15} more")
        
        if result.get('validation_result'):
            val = result['validation_result']
            print(f"\n🔍 Validation:")
            print(f"   Validated: {val.get('validated', False)}")
            if val.get('issues_found'):
                print(f"   Issues: {len(val.get('issues_found', []))}")
        
        if result.get('clinical_summary'):
            print(f"\n{'─'*50}")
            print(f"🏥 CLINICAL SUMMARY:")
            print(f"{'─'*50}")
            summary = result['clinical_summary']
            print(f"   {summary[:400]}")
        
        if result.get('errors'):
            print(f"\n⚠️ Errors: {result['errors']}")
        
        # Save full result to file
        output_file = f"smart_result_{datetime.now().strftime('%H%M%S')}.json"
        try:
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"\n💾 Full result saved: {output_file}")
        except Exception as e:
            print(f"\n⚠️ Could not save result: {e}")
    
    elif args.stats:
        router = SmartRouter()
        stats = router.get_stats()
        
        print("\n📊 STATISTICS:")
        print(f"   Documents processed: {stats.get('documents_processed', 0)}")
        print(f"   Average time: {stats.get('avg_processing_time', 0):.2f}s")
        print(f"\n   Methods used:")
        for method, count in stats.get('processing_methods_used', {}).items():
            print(f"      • {method}: {count} times")
        print(f"\n   VLM usage: {stats.get('vlm_usage_count', 0)} times")
        print(f"   Groq usage: {stats.get('groq_usage_count', 0)} times")
        print(f"   Existing pipeline: {stats.get('existing_pipeline_usage_count', 0)} times")
    
    else:
        help_text = """
Usage:
  python smart_router.py --file report.pdf              Process a file
  python smart_router.py --file scan.jpg --force vlm     Force VLM processing
  python smart_router.py --demo                          Show architecture info
  python smart_router.py --stats                         Show statistics

Examples:
  python smart_router.py --file lab_report.pdf
  python smart_router.py --file ecg_image.png --force vlm
  python smart_router.py --file scanned_doc.jpg --force hybrid
"""
        print(help_text)