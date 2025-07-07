def load_stylesheet(filepath: str) -> str:
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        print(f"Error loading stylesheet from {filepath}: {e}")
        return ""
