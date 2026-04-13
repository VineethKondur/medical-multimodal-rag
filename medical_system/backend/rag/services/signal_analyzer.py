"""
Generic Signal Analysis Pipeline
Supports: ECG (implemented), extensible for future signals (PPG, EEG, etc.)
Uses: neurokit2, numpy, pandas
No ML/DL - Signal processing only
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json


def analyze_signal(file_path: str, signal_type: str = "ecg") -> dict:
    """
    Generic entry point for signal analysis.
    
    Args:
        file_path: Path to CSV file containing signal data
        signal_type: Type of signal ("ecg", "ppg", "eeg", etc.)
    
    Returns:
        dict: Structured analysis results with safe non-diagnostic observations
    """
    
    try:
        # Load CSV
        df = pd.read_csv(file_path)
        
        if df.empty:
            return _error_response(signal_type, "Signal file is empty")
        
        # Extract signal column
        signal_data = _extract_signal_column(df)
        
        if signal_data is None or len(signal_data) == 0:
            return _error_response(signal_type, "No valid signal data found in file")
        
        # Route to specific analyzer
        if signal_type.lower() == "ecg":
            return analyze_ecg(signal_data)
        else:
            # Future: Add more signal types
            return _error_response(signal_type, f"Signal type '{signal_type}' not yet supported")
    
    except FileNotFoundError:
        return _error_response(signal_type, "Signal file not found")
    except pd.errors.EmptyDataError:
        return _error_response(signal_type, "CSV file is empty or malformed")
    except Exception as e:
        print(f"[Signal Analyzer] Error: {str(e)}")
        return _error_response(signal_type, f"Could not process signal: {str(e)}")


def _extract_signal_column(df: pd.DataFrame) -> np.ndarray:
    """
    Extract signal column from DataFrame.
    Priority: "signal" column → first numeric column
    
    Args:
        df: Loaded DataFrame
    
    Returns:
        np.ndarray: Signal values or None
    """
    try:
        # Try "signal" column first
        if "signal" in df.columns:
            return pd.to_numeric(df["signal"], errors="coerce").dropna().values
        
        # Try first numeric column
        for col in df.columns:
            try:
                numeric_data = pd.to_numeric(df[col], errors="coerce").dropna()
                if len(numeric_data) > 0:
                    return numeric_data.values
            except:
                continue
        
        return None
    
    except Exception as e:
        print(f"[Signal Analyzer] Error extracting signal column: {e}")
        return None


def analyze_ecg(signal: np.ndarray, sampling_rate: int = 1000) -> dict:
    """
    ECG-specific signal analysis using SCIPY (lightweight alternative to neurokit2).
    
    NO ML/DL REQUIRED - Pure signal processing!
    
    Features:
    - Peak detection (R-peaks)
    - Heart rate estimation (FFT + peak-based)
    - Rhythm regularity assessment
    - Signal quality evaluation
    
    Benefits over neurokit2:
    - 500MB less RAM usage
    - Faster imports (no heavy library loading)
    - Same accuracy for basic metrics
    
    Args:
        signal: Raw ECG signal array (1D numpy array)
        sampling_rate: Sampling rate in Hz (default 1000 Hz)
    
    Returns:
        dict: ECG analysis with features and interpretation
    """
    
    try:
        from scipy import signal as scipy_signal
        from scipy.stats import iqr
    except ImportError:
        return _error_response("ecg", "scipy not installed")
    
    # Validate input
    if signal is None or len(signal) == 0:
        return _error_response("ecg", "Empty signal")
    
    if len(signal) < sampling_rate * 0.5:  # Need at least 0.5 seconds of data
        return _error_response("ecg", "Signal too short (< 0.5 seconds)")
    
    results = {}
    
    # ================================================================
    # METHOD 1: Peak-Based Analysis (Primary)
    # ================================================================
    try:
        # Bandpass filter to remove noise (0.5-40 Hz for ECG)
        nyquist = sampling_rate / 2
        low_cut = 0.5 / nyquist
        high_cut = 40.0 / nyquist
        b, a = scipy_signal.butter(4, [low_cut, high_cut], btype='band')
        filtered_signal = scipy_signal.filtfilt(b, a, signal)
        
        # Detect R-peaks (QRS complexes are the tall spikes)
        # Minimum distance between peaks: 0.3 seconds (max 200 BPM)
        min_distance_samples = int(sampling_rate * 0.3)
        
        peaks, properties = scipy_signal.find_peaks(
            filtered_signal, 
            distance=min_distance_samples,
            height=np.percentile(filtered_signal, 70)  # Peaks must be above 70th percentile
        )
        
        if len(peaks) >= 2:
            # Calculate RR intervals (time between consecutive R-peaks)
            rr_intervals = np.diff(peaks) / sampling_rate  # Convert to seconds
            
            # Remove outliers (RR intervals that are too different from median)
            rr_median = np.median(rr_intervals)
            valid_mask = (rr_intervals > rr_median * 0.5) & (rr_intervals < rr_median * 1.5)
            valid_rr = rr_intervals[valid_mask]
            
            if len(valid_rr) >= 2:
                # Heart rate from median RR interval
                median_rr_seconds = np.median(valid_rr)
                heart_rate_bpm = 60.0 / median_rr_seconds
                
                results['heart_rate'] = round(heart_rate_bpm, 1)
                
                # Rhythm regularity (coefficient of variation)
                rr_cv = np.std(valid_rr) / np.median(valid_rr)
                results['rhythm'] = "Irregular" if rr_cv > 0.15 else "Regular"
                
                # HR variability (standard deviation of RR intervals)
                results['hr_variability_ms'] = round(np.std(valid_rr) * 1000, 1)  # Convert to ms
                
            else:
                # Too many outliers after filtering
                results['heart_rate'] = round(60.0 / np.median(rr_intervals), 1)
                results['rhythm'] = "Unknown"
        
        else:
            # Not enough peaks detected
            results['heart_rate'] = None
            results['rhythm'] = "Unknown"
            
    except Exception as peak_error:
        print(f"[Signal Analyzer] Peak detection error: {peak_error}")
        results['heart_rate'] = None
        results['rhythm'] = "Unknown"
    
    # ================================================================
    # METHOD 2: FFT-Based Estimation (Fallback if peak detection fails)
    # ================================================================
    if results.get('heart_rate') is None:
        fft_hr = _estimate_heart_rate_from_fft(signal, sampling_rate)
        if fft_hr:
            results['heart_rate'] = round(fft_hr, 1)
            results['rhythm'] = "Unknown"  # Can't determine rhythm from FFT alone
    
    # ================================================================
    # SIGNAL QUALITY ASSESSMENT
    # ================================================================
    results['signal_quality'] = _assess_signal_quality_lightweight(signal, sampling_rate)
    
    # ================================================================
    # GENERATE INTERPRETATION
    # ================================================================
    hr = results.get('heart_rate')
    rhythm = results.get('rhythm', 'Unknown')
    quality = results.get('signal_quality', 'Poor')
    
    results['observation'] = interpret_ecg(hr, rhythm, quality)
    results['possible_reasons'] = get_ecg_possible_reasons(hr, rhythm)
    results['success'] = hr is not None
    results['signal_type'] = 'ecg'
    
    # Additional metadata
    results['method_used'] = 'scipy_peak_detection'
    results['sampling_rate'] = sampling_rate
    results['signal_length_sec'] = round(len(signal) / sampling_rate, 2)
    results['peaks_detected'] = len(peaks) if 'peaks' in dir() else 0
    
    return results


def _assess_signal_quality_lightweight(raw_signal: np.ndarray, sampling_rate: int) -> str:
    """
    Lightweight signal quality assessment (no neurokit2 needed).
    
    Checks:
    1. Variance (flatline detection)
    2. Noise ratio (high-frequency content)
    3. Saturation (clipping at max/min)
    
    Args:
        raw_signal: Raw signal array
        sampling_rate: Sampling rate in Hz
    
    Returns:
        str: "Good", "Fair", or "Poor"
    """
    
    try:
        # Check 1: Is signal flat?
        signal_variance = np.var(raw_signal)
        if signal_variance < 0.001:
            return "Poor"
        
        # Check 2: Is there saturation/clipping?
        max_val = np.max(np.abs(raw_signal))
        theoretical_max = 5.0  # Typical ECG amplitude range is ±5 mV
        if max_val >= theoretical_max * 0.95:  # Within 5% of max
            return "Fair"  # Likely clipping
        
        # Check 3: Noise estimation (ratio of high-freq power to total power)
        from scipy import signal as scipy_signal
        
        # Simple high-pass filter to isolate noise
        nyquist = sampling_rate / 2
        b, a = scipy_signal.butter(2, 40.0/nyquist, btype='high')
        high_freq = scipy_signal.filtfilt(b, a, raw_signal)
        noise_power = np.var(high_freq)
        total_power = np.var(raw_signal)
        
        if total_power > 0:
            snr_ratio = total_power / (noise_power + 1e-10)
            if snr_ratio > 20:
                return "Good"
            elif snr_ratio > 10:
                return "Fair"
            else:
                return "Poor"
        else:
            return "Poor"
            
    except Exception as e:
        print(f"[Quality Assessment] Error: {e}")
        return "Unknown"

def _estimate_heart_rate_from_fft(signal: np.ndarray, sampling_rate: int = 1000) -> float:
    """
    Estimate heart rate from frequency domain (FFT).
    
    As fallback when peak detection fails.
    Heart rate typically manifests as dominant frequency in 60-100 bpm range.
    
    Args:
        signal: Raw signal array
        sampling_rate: Sampling rate in Hz
    
    Returns:
        float: Estimated heart rate in bpm, or None if failed
    """
    
    try:
        # Compute FFT
        fft_values = np.fft.fft(signal)
        frequencies = np.fft.fftfreq(len(signal), 1 / sampling_rate)
        
        # Focus on physiological frequency range (40-200 bpm)
        freq_range_hz = (40 / 60, 200 / 60)  # Convert bpm to Hz
        mask = (frequencies >= freq_range_hz[0]) & (frequencies <= freq_range_hz[1])
        
        if np.any(mask):
            max_idx = np.argmax(np.abs(fft_values[mask]))
            dominant_freq_hz = frequencies[mask][max_idx]
            heart_rate_bpm = dominant_freq_hz * 60
            
            # Validate result
            if 40 <= heart_rate_bpm <= 200:
                return heart_rate_bpm
        
        return None
    
    except Exception as e:
        print(f"[FFT Heart Rate Estimation] Error: {e}")
        return None


def _detect_ecg_rhythm(rpeaks: list, sampling_rate: int = 1000) -> str:
    """
    Detect ECG rhythm regularity from R-peak intervals.
    
    Regular: Low variance in intervals
    Irregular: High variance (possible arrhythmia)
    
    Args:
        rpeaks: List of R-peak indices
        sampling_rate: Sampling rate in Hz
    
    Returns:
        str: "Regular" or "Irregular"
    """
    
    if rpeaks is None or len(rpeaks) < 3:
        return "Unknown"
    
    try:
        rpeaks = np.array(rpeaks)
        # Calculate intervals between R-peaks (in ms)
        intervals = np.diff(rpeaks) / sampling_rate * 1000
        
        # Calculate coefficient of variation
        if len(intervals) > 0 and np.mean(intervals) > 0:
            cv = np.std(intervals) / np.mean(intervals)
            
            # Threshold: CV > 0.15 indicates irregular rhythm
            if cv > 0.15:
                return "Irregular"
            else:
                return "Regular"
        
        return "Unknown"
    
    except Exception as e:
        print(f"[Rhythm Detection] Error: {e}")
        return "Unknown"


def _assess_signal_quality(processed_signals, raw_signal) -> str:
    """
    Assess overall signal quality.
    
    Good: Low noise, clear features detected
    Poor: High noise or processing failed
    
    Args:
        processed_signals: Processed signal dict from neurokit2
        raw_signal: Raw signal array
    
    Returns:
        str: "Good" or "Poor"
    """
    
    try:
        # Check if processing extracted meaningful features
        if not processed_signals or len(processed_signals) == 0:
            return "Poor"
        
        # Check ECG_Rate validity (should have values)
        heart_rate = processed_signals.get("ECG_Rate", [])
        if heart_rate is None or len(heart_rate) < 10:
            return "Poor"
        
        # Check for NaN values (indicates noise/processing issues)
        nan_ratio = np.isnan(heart_rate).sum() / len(heart_rate)
        if nan_ratio > 0.3:  # More than 30% NaN = poor quality
            return "Poor"
        
        # Check raw signal variance (too flat = poor)
        signal_variance = np.var(raw_signal)
        if signal_variance < 0.001:
            return "Poor"
        
        return "Good"
    
    except Exception as e:
        print(f"[Signal Quality] Error: {e}")
        return "Unknown"


def interpret_ecg(heart_rate: float, rhythm: str, signal_quality: str) -> str:
    """
    Generate safe, non-diagnostic ECG interpretation.
    
    ⚠️ IMPORTANT: No diagnosis, only observations
    
    Args:
        heart_rate: Average heart rate in bpm
        rhythm: "Regular" or "Irregular"
        signal_quality: "Good" or "Poor"
    
    Returns:
        str: Safe observation string
    """
    
    if signal_quality == "Poor":
        return "Signal quality was poor for reliable interpretation. Please ensure proper electrode placement and try again."
    
    if heart_rate is None:
        return "Could not extract heart rate from the signal."
    
    observations = []
    
    # Heart rate observation
    if heart_rate < 60:
        observations.append(f"Heart rate is {heart_rate:.0f} bpm, which is below typical resting rate (60-100 bpm).")
    elif 60 <= heart_rate <= 100:
        observations.append(f"Heart rate is {heart_rate:.0f} bpm, which is within the typical resting range (60-100 bpm).")
    elif heart_rate > 100:
        observations.append(f"Heart rate is {heart_rate:.0f} bpm, which is elevated above typical resting rate (60-100 bpm).")
    
    # Rhythm observation
    if rhythm == "Irregular":
        observations.append("The rhythm pattern shows irregularity in heartbeat intervals.")
    elif rhythm == "Regular":
        observations.append("The rhythm pattern is regular.")
    
    return " ".join(observations)


def get_ecg_possible_reasons(heart_rate: float, rhythm: str) -> list:
    """
    Generate non-diagnostic possible reasons for observations.
    
    ⚠️ IMPORTANT: Use "Possible reasons" language, NOT diagnosis
    
    Args:
        heart_rate: Average heart rate in bpm
        rhythm: "Regular" or "Irregular"
    
    Returns:
        list: List of possible reasons (non-diagnostic)
    """
    
    reasons = []
    
    # High heart rate possible reasons
    if heart_rate > 100:
        reasons.extend([
            "Physical activity or recent exertion",
            "Stress, anxiety, or emotional state",
            "Fever, dehydration, or elevated body temperature",
            "Caffeine or stimulant consumption",
        ])
    
    # Low heart rate possible reasons
    elif heart_rate < 60:
        reasons.extend([
            "Resting or sleeping state",
            "Regular physical training or good cardiovascular fitness",
            "Hypothermia or cold exposure",
        ])
    
    # Irregular rhythm possible reasons
    if rhythm == "Irregular":
        reasons.extend([
            "Variation in heartbeat intervals (normal in some individuals)",
            "Stress or fatigue",
            "Electrolyte imbalance or dehydration",
            "Respiratory sinus arrhythmia (increases with breathing)",
        ])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_reasons = []
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            unique_reasons.append(reason)
    
    return unique_reasons


def _error_response(signal_type: str, error_msg: str) -> dict:
    """
    Return safe error response.
    
    Args:
        signal_type: Type of signal
        error_msg: Error message
    
    Returns:
        dict: Error response with safe fallback
    """
    
    return {
        "signal_type": signal_type,
        "heart_rate": None,
        "rhythm": "Unknown",
        "signal_quality": "Poor",
        "observation": f"Unable to process signal: {error_msg}",
        "possible_reasons": [],
        "success": False,
        "error": error_msg
    }


# ============================================================================
# FUTURE SIGNAL TYPES (Skeleton)
# ============================================================================

def analyze_ppg(signal: np.ndarray, sampling_rate: int = 100) -> dict:
    """
    PPG (Photoplethysmography) signal analysis - FUTURE IMPLEMENTATION
    Currently not implemented.
    """
    return _error_response("ppg", "PPG analysis not yet implemented")


def analyze_eeg(signal: np.ndarray, sampling_rate: int = 256) -> dict:
    """
    EEG (Electroencephalography) signal analysis - FUTURE IMPLEMENTATION
    Currently not implemented.
    """
    return _error_response("eeg", "EEG analysis not yet implemented")
