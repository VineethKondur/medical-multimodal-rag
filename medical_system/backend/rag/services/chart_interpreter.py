import statistics

def _safe_float(val):
    """Safely cast values to float, handling missing or non-numeric data."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def detect_chart_type(input_data: dict) -> str:
    """Detect the type of chart based on explicit type or data structure inference."""
    chart_type = input_data.get("type", "").lower()
    if chart_type in ["line", "bar", "signal"]:
        return chart_type
        
    data = input_data.get("data", [])
    if not data or not isinstance(data, list):
        return "unknown"
        
    first_item = data[0]
    if isinstance(first_item, dict):
        if "x" in first_item and "y" in first_item:
            return "line"
        if "label" in first_item and "value" in first_item:
            return "bar"
    elif isinstance(first_item, (int, float, str)) and _safe_float(first_item) is not None:
        return "signal"
        
    return "unknown"

def interpret_line_chart(data: list) -> dict:
    """Interpret time series / progression line charts."""
    valid_points = []
    for item in data:
        if isinstance(item, dict):
            y = _safe_float(item.get("y"))
            if y is not None:
                valid_points.append({"x": item.get("x", "unknown"), "y": y})
            
    if not valid_points:
        return {"analysis": "No valid data points found.", "metrics": {}}
        
    y_values = [p["y"] for p in valid_points]
    n = len(y_values)
    
    metrics = {
        "min": min(y_values),
        "max": max(y_values),
        "average": round(statistics.mean(y_values), 2),
        "trend": "stable",
        "variability": "low"
    }
    
    if n < 3:
        analysis = f"Insufficient data for reliable interpretation. Values range from {metrics['min']} to {metrics['max']}."
        return {"analysis": analysis, "metrics": metrics}
        
    if n >= 3:
        # Detect trend by comparing first half mean to second half mean
        mid = max(1, n // 2)
        start_avg = statistics.mean(y_values[:mid])
        end_avg = statistics.mean(y_values[mid:])
        diff = end_avg - start_avg
        
        if diff > (metrics["average"] * 0.05):
            metrics["trend"] = "increasing"
        elif diff < -(metrics["average"] * 0.05):
            metrics["trend"] = "decreasing"
            
        # Spike detection using max deviation
        max_dev = max(abs(metrics["max"] - metrics["average"]), abs(metrics["min"] - metrics["average"]))
        if max_dev > (metrics["average"] * 0.15):
            metrics["trend"] = "fluctuating"
            
        # Detect variability using coefficient of variation
        try:
            stdev = statistics.stdev(y_values)
            cv = stdev / (metrics["average"] or 1)
            if cv > 0.20:
                metrics["variability"] = "high"
            elif cv > 0.05:
                metrics["variability"] = "moderate"
        except statistics.StatisticsError:
            pass
            
    analysis = f"The line chart shows a {metrics['trend']} trend with {metrics['variability']} variability. Values range from {metrics['min']} to {metrics['max']}."
    return {"analysis": analysis, "metrics": metrics}

def interpret_bar_chart(data: list) -> dict:
    """Interpret comparison bar charts."""
    valid_bars = []
    for item in data:
        if isinstance(item, dict):
            val = _safe_float(item.get("value"))
            if val is not None:
                valid_bars.append({"label": item.get("label", "unknown"), "value": val})
            
    if not valid_bars:
        return {"analysis": "No valid data found.", "metrics": {}}
        
    valid_bars.sort(key=lambda x: x["value"])
    lowest = valid_bars[0]
    highest = valid_bars[-1]
    
    if len(valid_bars) < 3:
        analysis = f"Insufficient data for reliable interpretation. Values range from {lowest['label']} ({lowest['value']}) to {highest['label']} ({highest['value']})."
        return {"analysis": analysis, "metrics": {"highest": highest, "lowest": lowest}}
        
    values = [b["value"] for b in valid_bars]
    avg = statistics.mean(values)
    
    # Simple threshold logic: values > 50% above or below the mean are flagged
    threshold_high = avg * 1.5
    threshold_low = avg * 0.5
    
    abnormal_bars = [
        b for b in valid_bars 
        if b["value"] > threshold_high or b["value"] < threshold_low
    ]
    
    metrics = {
        "highest": highest,
        "lowest": lowest,
        "average": round(avg, 2),
        "abnormal_detected": len(abnormal_bars),
        "abnormal_labels": [b["label"] for b in abnormal_bars]
    }
    
    analysis = f"The bar chart ranges from {lowest['label']} ({lowest['value']}) to {highest['label']} ({highest['value']}). "
    if abnormal_bars:
        analysis += f"Found {len(abnormal_bars)} potentially abnormal outliers based on relative distribution."
    else:
        analysis += "Distribution appears relatively uniform with no major outliers."
        
    return {"analysis": analysis, "metrics": metrics}

def interpret_signal_chart(data: list) -> dict:
    """Interpret sequential signal data (e.g., ECG/Respiration proxy arrays)."""
    values = [_safe_float(v) for v in data]
    values = [v for v in values if v is not None]
    
    if not values:
        return {"analysis": "No valid signal data found.", "metrics": {}}
        
    n = len(values)
    avg = statistics.mean(values)
    metrics = {
        "average": round(avg, 2),
        "min": min(values),
        "max": max(values),
        "stability": "stable",
        "spikes": 0,
        "classification": "normal"
    }
    
    if n < 3:
        analysis = f"Insufficient data for reliable interpretation. Values range from {metrics['min']} to {metrics['max']}."
        return {"analysis": analysis, "metrics": metrics}
        
    if n >= 3:
        try:
            stdev = statistics.stdev(values)
            
            # Detect spikes: values beyond 2 standard deviations from the mean
            threshold = avg + (2 * stdev)
            spikes = [v for v in values if v > threshold]
            metrics["spikes"] = len(spikes)
            
            # Classify stability based on variance
            cv = stdev / (avg or 1)
            if cv > 0.15:
                metrics["stability"] = "variable"
                if metrics["spikes"] > 0:
                    metrics["classification"] = "abnormal"
            elif metrics["spikes"] > 0:
                metrics["stability"] = "variable"
        except statistics.StatisticsError:
            pass
            
    analysis = f"The signal has an average of {metrics['average']} and is classified as {metrics['classification']}. It appears {metrics['stability']} with {metrics['spikes']} detected spikes."
    return {"analysis": analysis, "metrics": metrics}

def interpret_chart(input_data: dict) -> dict:
    """Main entry point to route the structured chart data to the appropriate interpreter."""
    if not isinstance(input_data, dict):
        return {"type": "unknown", "analysis": "Invalid input format. Expected dictionary.", "metrics": {}}
        
    chart_type = detect_chart_type(input_data)
    data = input_data.get("data", [])
    
    if chart_type == "line":
        result = interpret_line_chart(data)
    elif chart_type == "bar":
        result = interpret_bar_chart(data)
    elif chart_type == "signal":
        result = interpret_signal_chart(data)
    else:
        return {"type": "unknown", "analysis": "Unsupported or unrecognized chart type.", "metrics": {}}
        
    # data_len = len(data)
    # if data_len < 3:
    #     confidence = "low"
    # elif data_len >= 8:
    #     confidence = "high"
    # else:
    #     confidence = "medium"
    
    # Use the actual analyzed count from metrics if available, fallback to raw length
    analyzed_count = len(result.get("metrics", {}).get("abnormal_labels", [])) 
    if chart_type == "line":
        analyzed_count = len([d for d in data if isinstance(d, dict) and _safe_float(d.get("y")) is not None])
    elif chart_type == "signal":
        analyzed_count = len([v for v in data if _safe_float(v) is not None])
        
    valid_len = analyzed_count if analyzed_count > 0 else len(data)
    
    if valid_len < 3:
        confidence = "low"
    elif valid_len >= 8:
        confidence = "high"
    else:
        confidence = "medium"
        
    return {
        "type": chart_type,
        "analysis": result["analysis"],
        "metrics": result["metrics"],
        "confidence": confidence
    }