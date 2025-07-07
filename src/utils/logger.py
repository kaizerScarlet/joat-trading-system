#src/utils/logger.py
#stub for custom logger interface

def log(message: str, level: str = "INFO") -> None:
    #Later: Expand to write to file, console, or Discord webhook
    print(f"[{level}] {message}")