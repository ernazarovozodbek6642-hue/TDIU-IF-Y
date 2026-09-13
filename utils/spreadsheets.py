def safe_excel_value(value):
    """Keep user-controlled text from being interpreted as an Excel formula."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
